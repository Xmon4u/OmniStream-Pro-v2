#pragma once

#include "common.hpp"
#include "curl_parser.hpp"

namespace OmniStream {

struct HttpResponse {
    int statusCode = 0;
    std::string contentType;
    std::vector<uint8_t> body;
    std::map<std::string, std::string> headers;

    std::string Text() const {
        return std::string(body.begin(), body.end());
    }

    bool IsSuccess() const {
        return statusCode >= 200 && statusCode < 300;
    }
};

class HttpClient {
public:
    HttpClient(const std::string& userAgent = DEFAULT_USER_AGENT);
    ~HttpClient();

    HttpResponse Get(
        const std::string& url,
        const std::map<std::string, std::string>& headers = {},
        std::function<void(uint64_t downloaded, uint64_t total)> progress = nullptr
    );

    HttpResponse Post(
        const std::string& url,
        const std::string& data,
        const std::string& contentType = "application/json",
        const std::map<std::string, std::string>& headers = {}
    );

    bool DownloadFile(
        const std::string& url,
        const std::string& destFilePath,
        const std::map<std::string, std::string>& headers = {},
        std::function<void(uint64_t downloaded, uint64_t total)> progress = nullptr
    );

private:
    HINTERNET m_hSession = nullptr;
    std::string m_userAgent;
};

} // namespace OmniStream
