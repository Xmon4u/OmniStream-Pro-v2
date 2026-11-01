#pragma once

#include "Common.hpp"
#include <string>
#include <map>
#include <mutex>
#include <condition_variable>
#include <optional>

namespace OmniStream {

class StreamResolver {
public:
    static StreamResolver& GetInstance();

    struct ResolvedStream {
        std::string url;
        std::string curl_cmd;
        std::string referer;
        bool success = false;
    };

    ResolvedStream Resolve(
        const std::string& page_url,
        const std::string& item_id,
        const std::string& title,
        LogCallback log_cb = nullptr,
        int timeout_sec = 25
    );

    void NotifyResolvedFromBridge(
        const std::string& item_id,
        const std::string& stream_url,
        const std::string& curl_cmd = "",
        const std::string& referer = ""
    );

    std::optional<std::pair<std::string, std::string>> GetPendingTask();

private:
    StreamResolver() = default;

    std::mutex mutex_;
    std::condition_variable cv_;
    std::map<std::string, ResolvedStream> cache_;
    std::map<std::string, std::string> pending_tasks_; // item_id -> page_url

    std::string FetchHtml(const std::string& url, const std::string& referer = "");
    std::string DirectScan(const std::string& html, const std::string& base_url);
};

} // namespace OmniStream

