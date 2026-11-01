#include "QueueManager.hpp"
#include "Database.hpp"
#include "SettingsManager.hpp"
#include "MetadataResolver.hpp"
#include "StreamResolver.hpp"
#include <fstream>
#include <iostream>

namespace OmniStream {

QueueManager& QueueManager::GetInstance() {
    static QueueManager instance;
    return instance;
}

QueueManager::QueueManager() = default;

QueueManager::~QueueManager() {
    Shutdown();
}

void QueueManager::Initialize() {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    items_ = Database::GetInstance().LoadAllQueueItems();
    DeduplicateQueueInternal();
    running_.store(true);
    dispatcher_thread_ = std::thread(&QueueManager::DispatcherLoop, this);
}

void QueueManager::Shutdown() {
    running_.store(false);
    is_dispatching_.store(false);
    cv_dispatcher_.notify_all();

    CancelAll();

    if (dispatcher_thread_.joinable()) {
        dispatcher_thread_.join();
    }

    // Safely wait for all active download workers to terminate cleanly
    std::unique_lock<std::mutex> lock(workers_mutex_);
    workers_cv_.wait_for(lock, std::chrono::seconds(5), [this]() {
        return active_workers_count_.load() == 0;
    });
}

void QueueManager::Log(const std::string& msg) {
    if (log_cb_) log_cb_(msg);
}

void QueueManager::NotifyQueueChanged() {
    if (on_queue_changed_) on_queue_changed_();
}

void QueueManager::NotifyItemUpdated(const DownloadItem& item) {
    if (on_item_updated_) on_item_updated_(item);
}

bool QueueManager::AddItem(DownloadItem item, bool auto_start) {
    Log("[AddItem] Received item title: '" + item.title + "' input: '" + item.input + "' page_url: '" + item.page_url + "'");
    if (item.input.empty() && item.page_url.empty()) {
        Log("[QueueManager] Rejected item with empty stream URL.");
        return false;
    }

    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);

    // 1. Compute deterministic unique id
    if (item.unique_id.empty()) {
        item.unique_id = MetadataResolver::ComputeMovieUniqueId(
            item.input, item.page_url, item.title, item.year
        );
    }
    if (item.id.empty()) {
        item.id = "q_" + std::to_string(Utils::CurrentTimestampMs()) + "_" + std::to_string(items_.size());
    }

    // 2. Duplicate Detection
    if (SettingsManager::GetInstance().GetSettings().duplicate_detection) {
        std::string cand_title = MetadataResolver::CleanTitleForMatching(item.title);
        std::string cand_url = Utils::ToLower(item.page_url.empty() ? item.input : item.page_url);
        bool is_generic_title = (cand_title == "videostream" || cand_title == "untitled" ||
                                 cand_title == "stream" || cand_title == "omnistreamdownload");

        for (auto& existing : items_) {
            bool id_match = (!item.unique_id.empty() && existing.unique_id == item.unique_id);
            bool url_match = (!cand_url.empty() && Utils::ToLower(existing.page_url) == cand_url);
            bool title_match = (!is_generic_title && !cand_title.empty() && cand_title.length() >= 5 &&
                                MetadataResolver::CleanTitleForMatching(existing.title) == cand_title);

            if (id_match || url_match || title_match) {
                Log("[AddItem] Matched existing '" + existing.title + "' id_match=" + std::to_string(id_match) +
                    " url_match=" + std::to_string(url_match) + " title_match=" + std::to_string(title_match) +
                    " status=" + DownloadStatusToString(existing.status));
                if (existing.status == DownloadStatus::Waiting ||
                    existing.status == DownloadStatus::Downloading ||
                    existing.status == DownloadStatus::Completed) {
                    Log("[Duplicate Filter] '" + existing.title + "' is already in queue — skipped.");
                    return false;
                } else {
                    // Reactivate failed/paused item with fresh link
                    existing.input = item.input;
                    existing.status = auto_start ? DownloadStatus::Waiting : DownloadStatus::Paused;
                    existing.progress_pct = 0.0;
                    existing.progress_text = "Ready in queue";
                    existing.needs_resolution = item.needs_resolution;
                    Database::GetInstance().SaveOrUpdateItem(existing);
                    NotifyItemUpdated(existing);
                    NotifyQueueChanged();
                    cv_dispatcher_.notify_all();
                    return true;
                }
            }
        }
    }

    item.status = auto_start ? DownloadStatus::Waiting : DownloadStatus::Paused;
    if (auto_start) is_dispatching_.store(true);
    if (item.save_dir.empty()) {
        item.save_dir = SettingsManager::GetInstance().GetSettings().default_save_dir;
    }
    item.created_at = Utils::CurrentTimestampSec();

    items_.push_back(item);
    Database::GetInstance().SaveOrUpdateItem(item);

    NotifyItemUpdated(item);
    NotifyQueueChanged();
    cv_dispatcher_.notify_all();
    return true;
}

int QueueManager::AddBatch(std::vector<DownloadItem> items, bool auto_start) {
    int added = 0;
    for (auto& it : items) {
        if (AddItem(it, auto_start)) {
            ++added;
        }
    }
    return added;
}

bool QueueManager::RemoveItem(const std::string& id) {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    CancelItemInternal(id);

    auto it = std::remove_if(items_.begin(), items_.end(), [&](const DownloadItem& item) {
        return item.id == id;
    });

    if (it != items_.end()) {
        items_.erase(it, items_.end());
        Database::GetInstance().RemoveItem(id);
        NotifyQueueChanged();
        return true;
    }
    return false;
}

void QueueManager::ClearAll() {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    CancelAllInternal();
    items_.clear();
    Database::GetInstance().ReplaceAllQueueItems({});
    NotifyQueueChanged();
}

void QueueManager::StartDownload(const std::string& id) {
    is_dispatching_.store(true);
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    for (auto& it : items_) {
        if (it.id == id && it.status != DownloadStatus::Downloading) {
            it.status = DownloadStatus::Waiting;
            it.progress_text = "Ready in queue";
            Database::GetInstance().UpdateStatus(id, DownloadStatus::Waiting);
            NotifyItemUpdated(it);
            break;
        }
    }
    cv_dispatcher_.notify_all();
}

void QueueManager::StartAll() {
    is_dispatching_.store(true);
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    for (auto& it : items_) {
        if (it.status != DownloadStatus::Completed && it.status != DownloadStatus::Downloading) {
            it.status = DownloadStatus::Waiting;
            it.progress_text = "Ready in queue";
            Database::GetInstance().UpdateStatus(it.id, DownloadStatus::Waiting);
            NotifyItemUpdated(it);
        }
    }
    cv_dispatcher_.notify_all();
}

void QueueManager::PauseItem(const std::string& id) {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    if (active_downloaders_.find(id) != active_downloaders_.end()) {
        active_downloaders_[id]->Abort();
        active_downloaders_.erase(id);
    }
    for (auto& it : items_) {
        if (it.id == id) {
            it.status = DownloadStatus::Paused;
            it.progress_text = "Paused";
            Database::GetInstance().UpdateStatus(id, DownloadStatus::Paused);
            NotifyItemUpdated(it);
            break;
        }
    }
}

void QueueManager::PauseAll() {
    is_dispatching_.store(false);
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    for (auto& [id, dl] : active_downloaders_) {
        dl->Abort();
    }
    active_downloaders_.clear();
    for (auto& it : items_) {
        if (it.status == DownloadStatus::Downloading || it.status == DownloadStatus::Waiting) {
            it.status = DownloadStatus::Paused;
            it.progress_text = "Paused";
            Database::GetInstance().UpdateStatus(it.id, DownloadStatus::Paused);
            NotifyItemUpdated(it);
        }
    }
}

void QueueManager::ResumeItem(const std::string& id) {
    is_dispatching_.store(true);
    StartDownload(id);
}

void QueueManager::ResumeAll() {
    is_dispatching_.store(true);
    StartAll();
}

void QueueManager::CancelItem(const std::string& id) {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    CancelItemInternal(id);
}

void QueueManager::CancelItemInternal(const std::string& id) {
    if (active_downloaders_.find(id) != active_downloaders_.end()) {
        active_downloaders_[id]->Abort();
        active_downloaders_.erase(id);
    }
    for (auto& it : items_) {
        if (it.id == id) {
            it.status = DownloadStatus::Cancelled;
            it.progress_text = "Stopped";
            Database::GetInstance().UpdateStatus(id, DownloadStatus::Cancelled);
            NotifyItemUpdated(it);
            break;
        }
    }
}

void QueueManager::CancelAll() {
    is_dispatching_.store(false);
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    CancelAllInternal();
}

void QueueManager::CancelAllInternal() {
    is_dispatching_.store(false);
    for (auto& [id, dl] : active_downloaders_) {
        dl->Abort();
    }
    active_downloaders_.clear();
    for (auto& it : items_) {
        if (it.status == DownloadStatus::Downloading || it.status == DownloadStatus::Waiting) {
            it.status = DownloadStatus::Cancelled;
            it.progress_text = "Stopped";
            Database::GetInstance().UpdateStatus(it.id, DownloadStatus::Cancelled);
            NotifyItemUpdated(it);
        }
    }
}

int QueueManager::DeduplicateQueue() {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    return DeduplicateQueueInternal();
}

int QueueManager::DeduplicateQueueInternal() {
    int removed = Database::GetInstance().PurgeDuplicates();
    if (removed > 0) {
        items_ = Database::GetInstance().LoadAllQueueItems();
        NotifyQueueChanged();
    }
    return removed;
}

bool QueueManager::ExportToCsv(const std::string& file_path) {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    std::ofstream out(file_path);
    if (!out.is_open()) return false;

    out << "SL No,Title,Page URL,Mode,Status,Progress,Error\n";
    for (size_t i = 0; i < items_.size(); ++i) {
        const auto& it = items_[i];
        out << (i + 1) << ",\""
            << it.title << "\",\""
            << it.page_url << "\",\""
            << DownloadModeToString(it.mode) << "\",\""
            << DownloadStatusToString(it.status) << "\","
            << it.progress_pct << "%,\""
            << it.error_msg << "\"\n";
    }
    return true;
}

std::vector<DownloadItem> QueueManager::GetAllItems() const {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    return items_;
}

std::optional<DownloadItem> QueueManager::GetItem(const std::string& id) const {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    for (const auto& it : items_) {
        if (it.id == id) return it;
    }
    return std::nullopt;
}

size_t QueueManager::GetCount() const {
    std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
    return items_.size();
}

void QueueManager::DispatcherLoop() {
    while (running_.load()) {
        {
            std::unique_lock<std::mutex> cv_lock(dispatcher_cv_mutex_);
            cv_dispatcher_.wait_for(cv_lock, std::chrono::milliseconds(500), [&]() {
                return !running_.load();
            });
        }

        if (!running_.load()) break;
        if (!is_dispatching_.load()) continue;

        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);

        int max_concur = SettingsManager::GetInstance().GetSettings().max_concurrent;
        if (max_concur <= 0) max_concur = 99; // unlimited

        if (static_cast<int>(active_downloaders_.size()) >= max_concur) {
            continue;
        }

        // Find next Waiting item
        for (auto& item : items_) {
            if (item.status == DownloadStatus::Waiting &&
                active_downloaders_.find(item.id) == active_downloaders_.end()) {

                item.status = DownloadStatus::Downloading;
                item.progress_text = "Starting download...";
                Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Downloading);
                NotifyItemUpdated(item);

                auto dl = std::make_shared<Downloader>();
                active_downloaders_[item.id] = dl;

                // Spawn worker thread for this specific download with lifecycle tracking
                active_workers_count_++;
                std::thread worker([this, item]() {
                    try {
                        ExecuteDownloadWorker(item);
                    } catch (...) {
                    }
                    active_workers_count_--;
                    workers_cv_.notify_all();
                });
                worker.detach();

                if (static_cast<int>(active_downloaders_.size()) >= max_concur) {
                    break;
                }
            }
        }
    }
}

void QueueManager::ExecuteDownloadWorker(DownloadItem item) {
    if (item.input.empty() && item.page_url.empty()) {
        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
        active_downloaders_.erase(item.id);
        item.status = DownloadStatus::Failed;
        item.error_msg = "Stream URL is empty";
        item.progress_text = "Failed: Missing stream URL";
        Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Failed, item.error_msg);
        NotifyItemUpdated(item);
        return;
    }

    // 1. Disk space check
    double free_gb = 0.0;
    if (!SettingsManager::GetInstance().CheckDiskSpace(item.save_dir, 2.0, free_gb)) {
        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
        active_downloaders_.erase(item.id);
        item.status = DownloadStatus::Failed;
        item.error_msg = "Low disk space (<2 GB free)";
        item.progress_text = "Failed: Low disk space";
        Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Failed, item.error_msg);
        NotifyItemUpdated(item);
        return;
    }

    // 2. Lazy Stream Resolution
    bool is_web_page = false;
    std::string s_in = Utils::ToLower(item.input);
    if (s_in.rfind("http://", 0) == 0 || s_in.rfind("https://", 0) == 0) {
        bool has_media_ext = (s_in.find(".m3u8") != std::string::npos || s_in.find(".mpd") != std::string::npos ||
                              s_in.find(".mp4") != std::string::npos || s_in.find(".mkv") != std::string::npos ||
                              s_in.find(".webm") != std::string::npos || s_in.find(".ts") != std::string::npos ||
                              s_in.find(".m4v") != std::string::npos);
        if (!has_media_ext && s_in.rfind("curl ", 0) != 0) {
            is_web_page = true;
        }
    }

    if (item.needs_resolution || item.is_auto || is_web_page) {
        Log("[Stream Resolver] Resolving media stream for: '" + item.title + "'...");
        auto res = StreamResolver::GetInstance().Resolve(
            item.page_url.empty() ? item.input : item.page_url,
            item.id,
            item.title,
            log_cb_,
            25
        );
        if (res.success && !res.url.empty()) {
            item.input = !res.curl_cmd.empty() ? res.curl_cmd : res.url;
            if (!res.referer.empty()) item.referer = res.referer;
            item.needs_resolution = false;
        } else {
            std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
            active_downloaders_.erase(item.id);
            item.status = DownloadStatus::Failed;
            item.error_msg = "Stream resolution timed out or blocked by Cloudflare. Please play video in Chrome and click 'Send to Desktop'.";
            item.progress_text = "Failed: Stream resolution error";
            Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Failed, item.error_msg);
            NotifyItemUpdated(item);
            return;
        }
    }

    // 3. Metadata Filename Resolution
    item.title = MetadataResolver::ResolveTargetFilename(item.input, item.title, item.mode, item.year);

    std::shared_ptr<Downloader> dl;
    {
        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
        if (active_downloaders_.find(item.id) != active_downloaders_.end()) {
            dl = active_downloaders_[item.id];
        }
    }

    if (!dl) return;

    auto progress_cb = [this, item_id = item.id](const std::string&, const DownloadProgress& p) {
        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
        for (auto& it : items_) {
            if (it.id == item_id) {
                it.progress_pct = p.percent;
                it.progress_text = p.percent > 0.0 ? std::to_string(static_cast<int>(p.percent)) + "% (" + p.speed + ")" : p.message;
                NotifyItemUpdated(it);
                break;
            }
        }
    };

    Downloader::ExecutionResult res;
    if (item.mode == DownloadMode::SubMerge && item.input.find("--sub-only") != std::string::npos) {
        res = dl->ExecuteSubtitleDownload(item, progress_cb, log_cb_);
    } else {
        res = dl->ExecuteDownload(item, progress_cb, log_cb_);
    }

    {
        std::lock_guard<std::recursive_mutex> lock(queue_mutex_);
        active_downloaders_.erase(item.id);

        if (!running_.load()) {
            return; // Application is shutting down, avoid calling dead UI or closing DB
        }

        for (auto& it : items_) {
            if (it.id == item.id) {
                if (res.success) {
                    it.status = DownloadStatus::Completed;
                    it.progress_pct = 100.0;
                    it.progress_text = "100% done · Finished";
                    if (!res.final_file_path.empty()) {
                        it.saved_file = res.final_file_path;
                    }
                    Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Completed, "", res.final_file_path);
                    Log("[Success] Download completed: " + it.title);
                } else {
                    it.status = DownloadStatus::Failed;
                    it.error_msg = res.error_reason;
                    it.progress_text = "Failed: " + res.error_reason;
                    Database::GetInstance().UpdateStatus(item.id, DownloadStatus::Failed, res.error_reason);
                    Log("[Error] Download failed: " + it.title + " (" + res.error_reason + ")");
                }
                NotifyItemUpdated(it);
                break;
            }
        }
    }

    cv_dispatcher_.notify_all();
}

} // namespace OmniStream

