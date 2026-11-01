#include "Database.hpp"
#include <filesystem>
#include <iostream>
#include <fstream>
#include <windows.h>
#include <shlobj.h>

#pragma comment(lib, "winsqlite3.lib")

namespace OmniStream {

Database& Database::GetInstance() {
    static Database instance;
    return instance;
}

Database::~Database() {
    Close();
}

void Database::Close() {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (db_) {
        sqlite3_close(db_);
        db_ = nullptr;
    }
}

std::string Database::ResolveDefaultDbPath() {
    PWSTR local_app_data = nullptr;
    if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local_app_data))) {
        char buf[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, local_app_data, -1, buf, sizeof(buf), nullptr, nullptr);
        CoTaskMemFree(local_app_data);
        std::filesystem::path dir = std::filesystem::path(buf) / "OmniStreamPro";
        std::filesystem::create_directories(dir);
        return (dir / "omnistream.db").string();
    }
    return "omnistream.db";
}

bool Database::Initialize(const std::string& custom_path) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    Close();

    db_path_ = custom_path.empty() ? ResolveDefaultDbPath() : custom_path;

    int rc = sqlite3_open(db_path_.c_str(), &db_);
    if (rc != SQLITE_OK) {
        std::cerr << "[Database] Failed to open database at: " << db_path_ << " (" << sqlite3_errmsg(db_) << ")\n";
        return false;
    }

    // Set busy timeout to 15 seconds & enable Write-Ahead Logging (WAL) for high concurrency
    sqlite3_busy_timeout(db_, 15000);
    char* err_msg = nullptr;
    sqlite3_exec(db_, "PRAGMA journal_mode=WAL;", nullptr, nullptr, &err_msg);
    if (err_msg) sqlite3_free(err_msg);

    sqlite3_exec(db_, "PRAGMA synchronous=NORMAL;", nullptr, nullptr, &err_msg);
    if (err_msg) sqlite3_free(err_msg);

    return CreateSchema();
}

bool Database::CreateSchema() {
    const char* schema_sql = R"(
        CREATE TABLE IF NOT EXISTS queue (
            id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            input_raw TEXT,
            save_dir TEXT,
            saved_file TEXT,
            resolution TEXT,
            audio TEXT,
            sub_format TEXT,
            sub_lang TEXT,
            include_subtitles INTEGER,
            mode TEXT,
            netflix_id TEXT,
            status TEXT,
            progress_pct REAL,
            progress_text TEXT,
            file_size TEXT,
            total_size TEXT,
            speed TEXT,
            time_left TEXT,
            temp_dir TEXT,
            error_msg TEXT,
            priority INTEGER,
            created_at REAL,
            completed_at REAL,
            media_type TEXT,
            year TEXT,
            is_multi_audio INTEGER,
            audio_languages TEXT,
            unique_id TEXT,
            referer TEXT,
            origin TEXT,
            user_agent TEXT,
            cookie TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue (status);
        CREATE INDEX IF NOT EXISTS idx_queue_created ON queue (created_at);
        CREATE INDEX IF NOT EXISTS idx_queue_unique_id ON queue (unique_id);
    )";

    char* err_msg = nullptr;
    int rc = sqlite3_exec(db_, schema_sql, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK) {
        std::cerr << "[Database] Schema creation failed: " << (err_msg ? err_msg : "Unknown") << "\n";
        if (err_msg) sqlite3_free(err_msg);
        return false;
    }

    // Schema migration for existing databases: ensure all modern metadata & header columns exist
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN file_size TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN total_size TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN speed TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN time_left TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN temp_dir TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN year TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN is_multi_audio INTEGER DEFAULT 0;", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN audio_languages TEXT DEFAULT '[]';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN unique_id TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN media_type TEXT DEFAULT 'video';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN referer TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN origin TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN user_agent TEXT DEFAULT '';", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "ALTER TABLE queue ADD COLUMN cookie TEXT DEFAULT '';", nullptr, nullptr, nullptr);

    return true;
}

bool Database::SaveOrUpdateItem(const DownloadItem& item) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    const char* sql = R"(
        INSERT INTO queue (
            id, title, url, input_raw, save_dir, saved_file, resolution, audio,
            sub_format, sub_lang, include_subtitles, mode, netflix_id, status,
            progress_pct, progress_text, file_size, total_size, speed, time_left,
            temp_dir, error_msg, priority, created_at, completed_at, media_type,
            year, is_multi_audio, audio_languages, unique_id,
            referer, origin, user_agent, cookie
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            input_raw = excluded.input_raw,
            save_dir = excluded.save_dir,
            saved_file = CASE WHEN excluded.saved_file != '' THEN excluded.saved_file ELSE queue.saved_file END,
            resolution = excluded.resolution,
            audio = excluded.audio,
            sub_format = excluded.sub_format,
            sub_lang = excluded.sub_lang,
            include_subtitles = excluded.include_subtitles,
            mode = excluded.mode,
            status = excluded.status,
            progress_pct = excluded.progress_pct,
            progress_text = excluded.progress_text,
            error_msg = excluded.error_msg,
            priority = excluded.priority,
            year = excluded.year,
            is_multi_audio = excluded.is_multi_audio,
            audio_languages = excluded.audio_languages,
            unique_id = excluded.unique_id,
            referer = CASE WHEN excluded.referer != '' THEN excluded.referer ELSE queue.referer END,
            origin = CASE WHEN excluded.origin != '' THEN excluded.origin ELSE queue.origin END,
            user_agent = CASE WHEN excluded.user_agent != '' THEN excluded.user_agent ELSE queue.user_agent END,
            cookie = CASE WHEN excluded.cookie != '' THEN excluded.cookie ELSE queue.cookie END;
    )";

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        return false;
    }

    int idx = 1;
    sqlite3_bind_text(stmt, idx++, item.id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.title.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.page_url.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.input.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.save_dir.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.saved_file.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.resolution.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.audio_choice.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.sub_format.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.sub_lang.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, idx++, item.include_subtitles ? 1 : 0);
    sqlite3_bind_text(stmt, idx++, DownloadModeToString(item.mode).c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.netflix_id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, DownloadStatusToString(item.status).c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, idx++, item.progress_pct);
    sqlite3_bind_text(stmt, idx++, item.progress_text.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, "", -1, SQLITE_TRANSIENT); // file_size
    sqlite3_bind_text(stmt, idx++, "", -1, SQLITE_TRANSIENT); // total_size
    sqlite3_bind_text(stmt, idx++, "", -1, SQLITE_TRANSIENT); // speed
    sqlite3_bind_text(stmt, idx++, "", -1, SQLITE_TRANSIENT); // time_left
    sqlite3_bind_text(stmt, idx++, "", -1, SQLITE_TRANSIENT); // temp_dir
    sqlite3_bind_text(stmt, idx++, item.error_msg.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, idx++, item.priority);
    sqlite3_bind_double(stmt, idx++, static_cast<double>(item.created_at ? item.created_at : Utils::CurrentTimestampSec()));
    sqlite3_bind_double(stmt, idx++, static_cast<double>(item.completed_at));
    sqlite3_bind_text(stmt, idx++, item.media_type.empty() ? "video" : item.media_type.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.year.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int(stmt, idx++, item.is_multi_audio ? 1 : 0);

    std::string aud_langs = "[]";
    if (!item.audio_languages.empty()) {
        aud_langs = "[";
        for (size_t i = 0; i < item.audio_languages.size(); ++i) {
            if (i > 0) aud_langs += ", ";
            aud_langs += "\"" + item.audio_languages[i] + "\"";
        }
        aud_langs += "]";
    }
    sqlite3_bind_text(stmt, idx++, aud_langs.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.unique_id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.referer.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.origin.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.user_agent.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, item.cookie.c_str(), -1, SQLITE_TRANSIENT);

    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return (rc == SQLITE_DONE);
}

std::vector<DownloadItem> Database::LoadAllQueueItems() {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    std::vector<DownloadItem> items;
    if (!db_) return items;

    const char* sql = R"(
        SELECT id, title, url, input_raw, save_dir, saved_file, resolution, audio,
               sub_format, sub_lang, include_subtitles, mode, netflix_id, status,
               progress_pct, progress_text, error_msg, priority, created_at, completed_at,
               year, is_multi_audio, unique_id, referer, origin, user_agent, cookie, media_type
        FROM queue ORDER BY priority ASC, created_at ASC;
    )";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        return items;
    }

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        DownloadItem it;
        auto get_txt = [&](int col) -> std::string {
            const unsigned char* t = sqlite3_column_text(stmt, col);
            return t ? reinterpret_cast<const char*>(t) : "";
        };

        it.id = get_txt(0);
        it.title = get_txt(1);
        it.page_url = get_txt(2);
        it.input = get_txt(3);
        it.save_dir = get_txt(4);
        it.saved_file = get_txt(5);
        it.resolution = get_txt(6);
        it.audio_choice = get_txt(7);
        it.sub_format = get_txt(8);
        it.sub_lang = get_txt(9);
        it.include_subtitles = (sqlite3_column_int(stmt, 10) != 0);
        it.mode = StringToDownloadMode(get_txt(11));
        it.netflix_id = get_txt(12);
        it.status = StringToDownloadStatus(get_txt(13));
        it.progress_pct = sqlite3_column_double(stmt, 14);
        it.progress_text = get_txt(15);
        it.error_msg = get_txt(16);
        it.priority = sqlite3_column_int(stmt, 17);
        it.created_at = static_cast<int64_t>(sqlite3_column_double(stmt, 18));
        it.completed_at = static_cast<int64_t>(sqlite3_column_double(stmt, 19));
        it.year = get_txt(20);
        it.is_multi_audio = (sqlite3_column_int(stmt, 21) != 0);
        it.unique_id = get_txt(22);
        it.referer = get_txt(23);
        it.origin = get_txt(24);
        it.user_agent = get_txt(25);
        it.cookie = get_txt(26);
        it.media_type = get_txt(27);

        // Adjust transient status on load
        if (it.status == DownloadStatus::Downloading) {
            it.status = DownloadStatus::Paused;
            it.progress_text = "Paused";
        }

        // Web page URL lazy resolution requirement
        std::string lo_in = Utils::ToLower(it.input);
        bool is_stream = (lo_in.find(".m3u8") != std::string::npos ||
                          lo_in.find(".mpd") != std::string::npos ||
                          lo_in.find(".mp4") != std::string::npos ||
                          lo_in.rfind("curl ", 0) == 0);
        if (!is_stream && (lo_in.rfind("http://", 0) == 0 || lo_in.rfind("https://", 0) == 0)) {
            it.is_auto = true;
            it.needs_resolution = (it.status != DownloadStatus::Completed);
        }

        items.push_back(it);
    }
    sqlite3_finalize(stmt);
    return items;
}

std::optional<DownloadItem> Database::GetItem(const std::string& id) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return std::nullopt;

    const char* sql = R"(
        SELECT id, title, url, input_raw, save_dir, saved_file, resolution, audio,
               sub_format, sub_lang, include_subtitles, mode, netflix_id, status,
               progress_pct, progress_text, error_msg, priority, created_at, completed_at,
               year, is_multi_audio, unique_id, referer, origin, user_agent, cookie, media_type
        FROM queue WHERE id = ? LIMIT 1;
    )";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) {
        return std::nullopt;
    }
    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);

    std::optional<DownloadItem> res;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        DownloadItem it;
        auto get_txt = [&](int col) -> std::string {
            const unsigned char* t = sqlite3_column_text(stmt, col);
            return t ? reinterpret_cast<const char*>(t) : "";
        };
        it.id = get_txt(0);
        it.title = get_txt(1);
        it.page_url = get_txt(2);
        it.input = get_txt(3);
        it.save_dir = get_txt(4);
        it.saved_file = get_txt(5);
        it.resolution = get_txt(6);
        it.audio_choice = get_txt(7);
        it.sub_format = get_txt(8);
        it.sub_lang = get_txt(9);
        it.include_subtitles = (sqlite3_column_int(stmt, 10) != 0);
        it.mode = StringToDownloadMode(get_txt(11));
        it.netflix_id = get_txt(12);
        it.status = StringToDownloadStatus(get_txt(13));
        it.progress_pct = sqlite3_column_double(stmt, 14);
        it.progress_text = get_txt(15);
        it.error_msg = get_txt(16);
        it.priority = sqlite3_column_int(stmt, 17);
        it.created_at = static_cast<int64_t>(sqlite3_column_double(stmt, 18));
        it.completed_at = static_cast<int64_t>(sqlite3_column_double(stmt, 19));
        it.year = get_txt(20);
        it.is_multi_audio = (sqlite3_column_int(stmt, 21) != 0);
        it.unique_id = get_txt(22);
        it.referer = get_txt(23);
        it.origin = get_txt(24);
        it.user_agent = get_txt(25);
        it.cookie = get_txt(26);
        it.media_type = get_txt(27);
        res = it;
    }
    sqlite3_finalize(stmt);
    return res;
}

bool Database::UpdateStatus(const std::string& id, DownloadStatus status, const std::string& error_msg, const std::string& final_path) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    std::string sql = "UPDATE queue SET status = ?, error_msg = ?";
    if (!final_path.empty()) sql += ", saved_file = ?";
    if (status == DownloadStatus::Completed) sql += ", completed_at = ?";
    sql += " WHERE id = ?;";

    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK) return false;

    int idx = 1;
    sqlite3_bind_text(stmt, idx++, DownloadStatusToString(status).c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, idx++, error_msg.c_str(), -1, SQLITE_TRANSIENT);
    if (!final_path.empty()) sqlite3_bind_text(stmt, idx++, final_path.c_str(), -1, SQLITE_TRANSIENT);
    if (status == DownloadStatus::Completed) sqlite3_bind_double(stmt, idx++, static_cast<double>(Utils::CurrentTimestampSec()));
    sqlite3_bind_text(stmt, idx++, id.c_str(), -1, SQLITE_TRANSIENT);

    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return (rc == SQLITE_DONE);
}

bool Database::UpdateProgress(const std::string& id, double pct, const std::string& text, const std::string& speed, const std::string& size) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    const char* sql = "UPDATE queue SET progress_pct = ?, progress_text = ?, speed = ?, file_size = ? WHERE id = ?;";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) return false;

    sqlite3_bind_double(stmt, 1, pct);
    sqlite3_bind_text(stmt, 2, text.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, speed.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, size.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 5, id.c_str(), -1, SQLITE_TRANSIENT);

    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return (rc == SQLITE_DONE);
}

bool Database::RemoveItem(const std::string& id) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    const char* sql = "DELETE FROM queue WHERE id = ?;";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) return false;

    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);
    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return (rc == SQLITE_DONE);
}

bool Database::ReplaceAllQueueItems(const std::vector<DownloadItem>& items) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    sqlite3_exec(db_, "BEGIN TRANSACTION;", nullptr, nullptr, nullptr);
    sqlite3_exec(db_, "DELETE FROM queue;", nullptr, nullptr, nullptr);
    for (const auto& it : items) {
        SaveOrUpdateItem(it);
    }
    sqlite3_exec(db_, "COMMIT;", nullptr, nullptr, nullptr);
    return true;
}

int Database::PurgeDuplicates() {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return 0;

    auto all_items = LoadAllQueueItems();
    std::vector<std::string> to_delete;
    std::map<std::string, DownloadItem> seen_uids;

    auto prio = [](DownloadStatus st) {
        switch (st) {
            case DownloadStatus::Downloading: return 5;
            case DownloadStatus::Completed: return 4;
            case DownloadStatus::Waiting: return 3;
            case DownloadStatus::Paused: return 2;
            case DownloadStatus::Failed: return 1;
            default: return 0;
        }
    };

    for (const auto& it : all_items) {
        std::string key = it.unique_id.empty() ? it.title : it.unique_id;
        if (key.empty()) continue;

        if (seen_uids.find(key) != seen_uids.end()) {
            auto& existing = seen_uids[key];
            if (prio(it.status) > prio(existing.status)) {
                to_delete.push_back(existing.id);
                existing = it;
            } else {
                to_delete.push_back(it.id);
            }
        } else {
            seen_uids[key] = it;
        }
    }

    for (const auto& id : to_delete) {
        RemoveItem(id);
    }
    return static_cast<int>(to_delete.size());
}

std::string Database::GetSetting(const std::string& key, const std::string& default_val) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return default_val;

    const char* sql = "SELECT value FROM settings WHERE key = ? LIMIT 1;";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) return default_val;

    sqlite3_bind_text(stmt, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    std::string res = default_val;
    if (sqlite3_step(stmt) == SQLITE_ROW) {
        const unsigned char* val = sqlite3_column_text(stmt, 0);
        if (val) res = reinterpret_cast<const char*>(val);
    }
    sqlite3_finalize(stmt);
    return res;
}

bool Database::SetSetting(const std::string& key, const std::string& val) {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    if (!db_) return false;

    const char* sql = "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) return false;

    sqlite3_bind_text(stmt, 1, key.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, val.c_str(), -1, SQLITE_TRANSIENT);

    int rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);
    return (rc == SQLITE_DONE);
}

std::map<std::string, std::string> Database::GetAllSettings() {
    std::lock_guard<std::recursive_mutex> lock(db_mutex_);
    std::map<std::string, std::string> res;
    if (!db_) return res;

    const char* sql = "SELECT key, value FROM settings;";
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db_, sql, -1, &stmt, nullptr) != SQLITE_OK) return res;

    while (sqlite3_step(stmt) == SQLITE_ROW) {
        const unsigned char* k = sqlite3_column_text(stmt, 0);
        const unsigned char* v = sqlite3_column_text(stmt, 1);
        if (k && v) {
            res[reinterpret_cast<const char*>(k)] = reinterpret_cast<const char*>(v);
        }
    }
    sqlite3_finalize(stmt);
    return res;
}

} // namespace OmniStream

