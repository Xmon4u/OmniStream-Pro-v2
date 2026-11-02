#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#ifndef NOMINMAX
#define NOMINMAX
#endif

#ifndef _WINSOCK_DEPRECATED_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#endif

#include <winsock2.h>
#include <windows.h>

#include <string>
#include <vector>
#include <map>
#include <memory>
#include <functional>
#include <chrono>
#include <cstdint>
#include <algorithm>
#include <cctype>

namespace OmniStream {

enum class DownloadMode {
    Normal,
    Netflix,
    TitleOnly,
    IMDb,
    TMDB,
    TitleAndId,
    SubMerge,
    Auto
};

inline std::string DownloadModeToString(DownloadMode mode) {
    switch (mode) {
        case DownloadMode::Normal: return "normal";
        case DownloadMode::Netflix: return "netflix_rename";
        case DownloadMode::TitleOnly: return "title_only";
        case DownloadMode::IMDb: return "imdb";
        case DownloadMode::TMDB: return "tmdb";
        case DownloadMode::TitleAndId: return "title_id";
        case DownloadMode::SubMerge: return "sub_merge";
        case DownloadMode::Auto: return "auto";
        default: return "normal";
    }
}

inline DownloadMode StringToDownloadMode(const std::string& str) {
    std::string s = str;
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    if (s == "netflix" || s == "netflix_rename") return DownloadMode::Netflix;
    if (s == "title" || s == "title_only") return DownloadMode::TitleOnly;
    if (s == "imdb") return DownloadMode::IMDb;
    if (s == "tmdb") return DownloadMode::TMDB;
    if (s == "title_id" || s == "title+id") return DownloadMode::TitleAndId;
    if (s == "sub_merge" || s == "subs") return DownloadMode::SubMerge;
    if (s == "auto") return DownloadMode::Auto;
    return DownloadMode::Normal;
}

enum class DownloadStatus {
    Waiting,
    Downloading,
    Paused,
    Completed,
    Failed,
    Cancelled
};

inline std::string DownloadStatusToString(DownloadStatus status) {
    switch (status) {
        case DownloadStatus::Waiting: return "Waiting";
        case DownloadStatus::Downloading: return "Downloading";
        case DownloadStatus::Paused: return "Paused";
        case DownloadStatus::Completed: return "Completed";
        case DownloadStatus::Failed: return "Failed";
        case DownloadStatus::Cancelled: return "Cancelled";
        default: return "Waiting";
    }
}

inline DownloadStatus StringToDownloadStatus(const std::string& str) {
    std::string s = str;
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
    if (s == "downloading") return DownloadStatus::Downloading;
    if (s == "paused") return DownloadStatus::Paused;
    if (s == "completed" || s == "done") return DownloadStatus::Completed;
    if (s == "failed" || s == "error") return DownloadStatus::Failed;
    if (s == "cancelled" || s == "stopped") return DownloadStatus::Cancelled;
    return DownloadStatus::Waiting;
}

struct DownloadProgress {
    double percent = 0.0;
    std::string speed = "0.0 MB/s";
    std::string size = "Calculating...";
    std::string eta = "Calculating...";
    std::string message = "Starting...";
};

struct DownloadItem {
    std::string id;
    std::string unique_id;
    std::string title = "OmniStream Download";
    bool user_specified_title = false;
    std::string input;
    std::string page_url;
    std::string referer;
    std::string origin;
    std::string user_agent;
    std::string cookie;
    std::string save_dir;
    std::string saved_file;
    std::string resolution = "1080p";
    std::string audio_choice = "all";
    bool include_subtitles = true;
    std::string sub_format = "SRT";
    std::string sub_lang = "all";
    DownloadStatus status = DownloadStatus::Waiting;
    double progress_pct = 0.0;
    std::string progress_text = "Ready in queue";
    DownloadMode mode = DownloadMode::Normal;
    std::string netflix_id;
    bool is_auto = false;
    bool needs_resolution = false;
    std::string year;
    std::string quality = "HD";
    std::string media_type;
    std::string speed_limit;
    bool is_multi_audio = false;
    std::vector<std::string> audio_languages;
    int audio_count = 1;
    std::string error_msg;
    int priority = 0;
    int64_t created_at = 0;
    int64_t completed_at = 0;
};

struct AppSettings {
    int max_concurrent = 3;
    std::string speed_limit = "unlimited";
    double custom_speed_limit_mbps = 5.0;
    std::string default_save_dir;
    bool smart_organization = false;
    std::string queue_completion_action = "none";
    bool minimize_to_tray_on_close = true;
    bool auto_retry_enabled = true;
    int max_retries = 3;
    std::vector<int> retry_backoff = {5, 15, 30};
    bool notification_sound = true;
    bool duplicate_detection = true;
    bool auto_start_downloads = true;
    double min_disk_space_gb = 2.0;
};

using LogCallback = std::function<void(const std::string& message)>;
using ProgressCallback = std::function<void(const std::string& item_id, const DownloadProgress& progress)>;
using StatusCallback = std::function<void(const std::string& item_id, DownloadStatus status, const std::string& detail)>;

// Fast utility functions
namespace Utils {
    inline std::string Trim(const std::string& s) {
        auto wsfront = std::find_if_not(s.begin(), s.end(), [](int c){ return std::isspace(c); });
        auto wsback = std::find_if_not(s.rbegin(), s.rend(), [](int c){ return std::isspace(c); }).base();
        return (wsback <= wsfront ? std::string() : std::string(wsfront, wsback));
    }

    inline std::string ToLower(const std::string& s) {
        std::string res = s;
        std::transform(res.begin(), res.end(), res.begin(), [](unsigned char c){ return static_cast<char>(std::tolower(c)); });
        return res;
    }

    inline std::string ReplaceAll(const std::string& str, const std::string& from, const std::string& to) {
        if (from.empty()) return str;
        std::string res = str;
        size_t start_pos = 0;
        while ((start_pos = res.find(from, start_pos)) != std::string::npos) {
            res.replace(start_pos, from.length(), to);
            start_pos += to.length();
        }
        return res;
    }

    inline std::wstring Utf8ToWide(const std::string& str) {
        if (str.empty()) return L"";
        int len = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.length()), nullptr, 0);
        if (len <= 0) return std::wstring(str.begin(), str.end());
        std::wstring wstr(len, 0);
        MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.length()), &wstr[0], len);
        return wstr;
    }

    inline std::string WideToUtf8(const std::wstring& wstr) {
        if (wstr.empty()) return "";
        int len = WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.length()), nullptr, 0, nullptr, nullptr);
        if (len <= 0) return "";
        std::string str(len, 0);
        WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.length()), &str[0], len, nullptr, nullptr);
        return str;
    }

    inline int64_t CurrentTimestampSec() {
        return std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
    }

    inline int64_t CurrentTimestampMs() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
    }
}

} // namespace OmniStream
