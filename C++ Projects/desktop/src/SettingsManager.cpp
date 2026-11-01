#include "SettingsManager.hpp"
#include "Database.hpp"
#include <windows.h>
#include <shlobj.h>
#include <filesystem>
#include <iostream>

namespace OmniStream {

SettingsManager& SettingsManager::GetInstance() {
    static SettingsManager instance;
    return instance;
}

SettingsManager::SettingsManager() {
    // Resolve default save dir: %USERPROFILE%\Downloads\videos
    PWSTR profile_path = nullptr;
    if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_Downloads, 0, nullptr, &profile_path))) {
        char buf[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, profile_path, -1, buf, sizeof(buf), nullptr, nullptr);
        CoTaskMemFree(profile_path);
        std::filesystem::path dir = std::filesystem::path(buf) / "videos";
        settings_.default_save_dir = dir.string();
    } else {
        settings_.default_save_dir = "C:\\Downloads\\videos";
    }
    Load();
}

void SettingsManager::Load() {
    std::lock_guard<std::mutex> lock(mutex_);
    auto& db = Database::GetInstance();

    std::string s_concurrent = db.GetSetting("max_concurrent");
    if (!s_concurrent.empty()) {
        try { settings_.max_concurrent = std::stoi(s_concurrent); } catch (...) {}
    }

    std::string s_speed = db.GetSetting("speed_limit");
    if (!s_speed.empty()) settings_.speed_limit = s_speed;

    std::string s_dir = db.GetSetting("default_save_dir");
    if (!s_dir.empty()) settings_.default_save_dir = s_dir;

    std::string s_tray = db.GetSetting("minimize_to_tray_on_close");
    if (!s_tray.empty()) settings_.minimize_to_tray_on_close = (s_tray == "1" || s_tray == "true");

    std::string s_dup = db.GetSetting("duplicate_detection");
    if (!s_dup.empty()) settings_.duplicate_detection = (s_dup == "1" || s_dup == "true");

    std::string s_retry = db.GetSetting("auto_retry_enabled");
    if (!s_retry.empty()) settings_.auto_retry_enabled = (s_retry == "1" || s_retry == "true");

    std::string s_auto_start = db.GetSetting("auto_start_downloads");
    if (!s_auto_start.empty()) settings_.auto_start_downloads = (s_auto_start == "1" || s_auto_start == "true");
}

void SettingsManager::Save() {
    std::lock_guard<std::mutex> lock(mutex_);
    auto& db = Database::GetInstance();

    db.SetSetting("max_concurrent", std::to_string(settings_.max_concurrent));
    db.SetSetting("speed_limit", settings_.speed_limit);
    db.SetSetting("default_save_dir", settings_.default_save_dir);
    db.SetSetting("minimize_to_tray_on_close", settings_.minimize_to_tray_on_close ? "1" : "0");
    db.SetSetting("duplicate_detection", settings_.duplicate_detection ? "1" : "0");
    db.SetSetting("auto_retry_enabled", settings_.auto_retry_enabled ? "1" : "0");
    db.SetSetting("auto_start_downloads", settings_.auto_start_downloads ? "1" : "0");
}

void SettingsManager::SetMaxConcurrent(int val) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_.max_concurrent = val;
        Database::GetInstance().SetSetting("max_concurrent", std::to_string(val));
    }
    NotifyListeners("max_concurrent");
}

void SettingsManager::SetSpeedLimit(const std::string& limit) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_.speed_limit = limit;
        Database::GetInstance().SetSetting("speed_limit", limit);
    }
    NotifyListeners("speed_limit");
}

void SettingsManager::SetSaveDir(const std::string& dir) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_.default_save_dir = dir;
        Database::GetInstance().SetSetting("default_save_dir", dir);
    }
    NotifyListeners("default_save_dir");
}

void SettingsManager::SetMinimizeToTray(bool val) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_.minimize_to_tray_on_close = val;
        Database::GetInstance().SetSetting("minimize_to_tray_on_close", val ? "1" : "0");
    }
    NotifyListeners("minimize_to_tray_on_close");
}

void SettingsManager::SetDuplicateDetection(bool val) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        settings_.duplicate_detection = val;
        Database::GetInstance().SetSetting("duplicate_detection", val ? "1" : "0");
    }
    NotifyListeners("duplicate_detection");
}

bool SettingsManager::CheckDiskSpace(const std::string& path, double min_free_gb, double& out_free_gb) const {
    ULARGE_INTEGER free_bytes_available;
    ULARGE_INTEGER total_number_of_bytes;
    ULARGE_INTEGER total_number_of_free_bytes;

    std::wstring wpath(path.begin(), path.end());
    if (GetDiskFreeSpaceExW(wpath.c_str(), &free_bytes_available, &total_number_of_bytes, &total_number_of_free_bytes)) {
        out_free_gb = static_cast<double>(free_bytes_available.QuadPart) / (1024.0 * 1024.0 * 1024.0);
        return out_free_gb >= min_free_gb;
    }
    out_free_gb = 999.0;
    return true;
}

void SettingsManager::AddListener(ChangeListener listener) {
    std::lock_guard<std::mutex> lock(mutex_);
    listeners_.push_back(listener);
}

void SettingsManager::NotifyListeners(const std::string& key) {
    std::vector<ChangeListener> copy;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        copy = listeners_;
    }
    for (auto& cb : copy) {
        if (cb) cb(key);
    }
}

} // namespace OmniStream

