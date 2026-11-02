#pragma once

#include "Common.hpp"
#include <string>
#include <atomic>
#include <memory>
#include <windows.h>

namespace OmniStream {

class Downloader {
public:
    Downloader();
    ~Downloader();

    struct ExecutionResult {
        bool success = false;
        int exit_code = -1;
        std::string error_reason;
        std::string fix_hint;
        std::string final_file_path;
    };

    ExecutionResult ExecuteDownload(
        const DownloadItem& item,
        ProgressCallback progress_cb = nullptr,
        LogCallback log_cb = nullptr
    );

    ExecutionResult ExecuteSubtitleDownload(
        const DownloadItem& item,
        ProgressCallback progress_cb = nullptr,
        LogCallback log_cb = nullptr
    );

    struct StreamDetails {
        std::string url;
        std::string referer;
        std::string origin;
        std::string user_agent;
        std::string cookie;
    };

    static StreamDetails ParseStreamDetails(const DownloadItem& item);
    static bool IsDirectMediaUrl(const std::string& url, const std::string& media_type = "");
    std::string FindBinary(const std::string& name) const;

    ExecutionResult ExecuteDirectDownload(
        const DownloadItem& item,
        const StreamDetails& details,
        ProgressCallback progress_cb = nullptr,
        LogCallback log_cb = nullptr
    );

    ExecutionResult ExecuteHlsDashDownload(
        const DownloadItem& item,
        const StreamDetails& details,
        ProgressCallback progress_cb = nullptr,
        LogCallback log_cb = nullptr
    );

    void Abort();

    std::string StripAnsiCodes(const std::string& text) const;
    bool ParseOutputLine(const std::string& line, DownloadProgress& progress) const;

private:
    std::atomic<bool> aborted_{false};
    HANDLE job_object_ = nullptr;
    HANDLE child_process_ = nullptr;

    ExecutionResult RunProcess(
        const std::wstring& cmd_line,
        const std::string& item_id,
        ProgressCallback progress_cb,
        LogCallback log_cb
    );
};

} // namespace OmniStream

