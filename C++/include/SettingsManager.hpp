#pragma once

#include "Common.hpp"
#include <string>
#include <vector>
#include <functional>
#include <mutex>

namespace OmniStream {

class SettingsManager {
public:
    static SettingsManager& GetInstance();

    void Load();
    void Save();

    AppSettings& GetSettings() { return settings_; }
    const AppSettings& GetSettings() const { return settings_; }

    void SetMaxConcurrent(int val);
    void SetSpeedLimit(const std::string& limit);
    void SetSaveDir(const std::string& dir);
    void SetMinimizeToTray(bool val);
    void SetDuplicateDetection(bool val);

    // Checks available disk space on the drive of the given directory path
    bool CheckDiskSpace(const std::string& path, double min_free_gb, double& out_free_gb) const;

    using ChangeListener = std::function<void(const std::string& key)>;
    void AddListener(ChangeListener listener);

private:
    SettingsManager();
    AppSettings settings_;
    mutable std::mutex mutex_;
    std::vector<ChangeListener> listeners_;
    void NotifyListeners(const std::string& key);
};

} // namespace OmniStream

