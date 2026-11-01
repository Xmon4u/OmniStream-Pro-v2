#pragma once

#include "Common.hpp"
#include <string>
#include <vector>
#include <map>
#include <mutex>
#include <optional>
#include <winsqlite/winsqlite3.h>

namespace OmniStream {

class Database {
public:
    static Database& GetInstance();

    bool Initialize(const std::string& custom_path = "");
    void Close();

    // Queue Item CRUD
    bool SaveOrUpdateItem(const DownloadItem& item);
    std::vector<DownloadItem> LoadAllQueueItems();
    std::optional<DownloadItem> GetItem(const std::string& id);
    bool UpdateStatus(const std::string& id, DownloadStatus status, const std::string& error_msg = "", const std::string& final_path = "");
    bool UpdateProgress(const std::string& id, double pct, const std::string& text, const std::string& speed = "", const std::string& size = "");
    bool RemoveItem(const std::string& id);
    bool ReplaceAllQueueItems(const std::vector<DownloadItem>& items);
    int PurgeDuplicates();

    // Settings CRUD
    std::string GetSetting(const std::string& key, const std::string& default_val = "");
    bool SetSetting(const std::string& key, const std::string& val);
    std::map<std::string, std::string> GetAllSettings();

    std::string GetDatabasePath() const { return db_path_; }

private:
    Database() = default;
    ~Database();
    Database(const Database&) = delete;
    Database& operator=(const Database&) = delete;

    sqlite3* db_ = nullptr;
    std::string db_path_;
    std::recursive_mutex db_mutex_;

    bool CreateSchema();
    std::string ResolveDefaultDbPath();
};

} // namespace OmniStream
