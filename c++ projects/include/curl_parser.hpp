#pragma once

#include "common.hpp"

namespace OmniStream {

struct StreamInfo {
    std::string url;
    std::string referer;
    std::string origin;
    std::string user_agent;
    std::string cookie;
    std::map<std::string, std::string> headers;

    std::string GetHeader(const std::string& key) const {
        std::string lowerKey = key;
        std::transform(lowerKey.begin(), lowerKey.end(), lowerKey.begin(), ::tolower);
        auto it = headers.find(lowerKey);
        if (it != headers.end()) return it->second;
        return "";
    }
};

class CurlParser {
public:
    static StreamInfo Parse(const std::string& rawInput);
    static std::string ExtractOrigin(const std::string& url);
    static std::string ResolveUrl(const std::string& baseUrl, const std::string& relativeOrAbsoluteUrl);
    static std::string UnescapeCurl(const std::string& input);
};

} // namespace OmniStream
