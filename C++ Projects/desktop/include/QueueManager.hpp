#pragma once

#include "Common.hpp"
#include "Downloader.hpp"
#include <vector>
#include <map>
#include <mutex>
#include <thread>
#include <atomic>
#include <functional>
#include <condition_variable>

namespace OmniStream {

class QueueManager {
public:
    static QueueManager& GetInstance();

    void Initialize();
    void Shutdown();

    // Queue Item Manipulation
    bool AddItem(DownloadItem item, bool auto_start = false);
    int AddBatch(std::vector<DownloadItem> items, bool auto_start = false);
    bool RemoveItem(const std::string& id);
    void ClearAll();

    // Download Controls
    void StartDownload(const std::string& id);
    void StartAll();
    void PauseItem(const std::string& id);
    void PauseAll();
    void ResumeItem(const std::string& id);
    void ResumeAll();
    void CancelItem(const std::string& id);
    void CancelAll();

    // Deduplication & Maintenance
    int DeduplicateQueue();
    bool ExportToCsv(const std::string& file_path);

    // Queries
    std::vector<DownloadItem> GetAllItems() const;
    std::optional<DownloadItem> GetItem(const std::string& id) const;
    size_t GetCount() const;
    DownloadMode GetCurrentMode() const { return current_mode_; }
    void SetCurrentMode(DownloadMode mode) {
        current_mode_ = mode;
        if (on_mode_changed_) on_mode_changed_(mode);
    }

    // Event Callbacks
    using ItemCallback = std::function<void(const DownloadItem& item)>;
    using QueueEventCallback = std::function<void()>;
    using ModeCallback = std::function<void(DownloadMode mode)>;

    void SetItemUpdatedCallback(ItemCallback cb) { on_item_updated_ = cb; }
    void SetQueueChangedCallback(QueueEventCallback cb) { on_queue_changed_ = cb; }
    void SetModeChangedCallback(ModeCallback cb) { on_mode_changed_ = cb; }
    void SetLogCallback(LogCallback cb) { log_cb_ = cb; }

private:
    QueueManager();
    ~QueueManager();

    mutable std::recursive_mutex queue_mutex_;
    std::mutex dispatcher_cv_mutex_;
    std::vector<DownloadItem> items_;
    std::map<std::string, std::shared_ptr<Downloader>> active_downloaders_;
    std::atomic<bool> running_{false};
    std::atomic<bool> is_dispatching_{false};
    std::thread dispatcher_thread_;
    std::condition_variable cv_dispatcher_;

    std::mutex workers_mutex_;
    std::condition_variable workers_cv_;
    std::atomic<int> active_workers_count_{0};

    DownloadMode current_mode_ = DownloadMode::Normal;

    ItemCallback on_item_updated_ = nullptr;
    QueueEventCallback on_queue_changed_ = nullptr;
    ModeCallback on_mode_changed_ = nullptr;
    LogCallback log_cb_ = nullptr;

    int DeduplicateQueueInternal();
    void CancelItemInternal(const std::string& id);
    void CancelAllInternal();

    void DispatcherLoop();
    void ExecuteDownloadWorker(DownloadItem item);
    void NotifyQueueChanged();
    void NotifyItemUpdated(const DownloadItem& item);
    void Log(const std::string& msg);
};

} // namespace OmniStream

