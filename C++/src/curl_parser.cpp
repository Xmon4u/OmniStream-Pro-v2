#include "curl_parser.hpp"

namespace OmniStream {

std::string CurlParser::UnescapeCurl(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (size_t i = 0; i < input.size(); ++i) {
        if (input[i] == '\\' && i + 1 < input.size()) {
            char next = input[i + 1];
            if (next == '\n' || next == '\r') {
                i++;
                if (next == '\r' && i + 1 < input.size() && input[i + 1] == '\n') i++;
                result += ' ';
                continue;
            }
            if (next == '"' || next == '\'' || next == '\\') {
                result += next;
                i++;
                continue;
            }
        }
        result += input[i];
    }
    return result;
}

std::string CurlParser::ExtractOrigin(const std::string& url) {
    std::regex regexOrigin(R"(^(https?://[^/?#]+))", std::regex::icase);
    std::smatch match;
    if (std::regex_search(url, match, regexOrigin)) {
        return match[1].str();
    }
    return "";
}

std::string CurlParser::ResolveUrl(const std::string& baseUrl, const std::string& relativeOrAbsoluteUrl) {
    if (relativeOrAbsoluteUrl.rfind("http://", 0) == 0 || relativeOrAbsoluteUrl.rfind("https://", 0) == 0) {
        return relativeOrAbsoluteUrl;
    }

    std::string origin = ExtractOrigin(baseUrl);
    if (relativeOrAbsoluteUrl.rfind("/", 0) == 0) {
        return origin + relativeOrAbsoluteUrl;
    }

    size_t lastSlash = baseUrl.find_last_of('/');
    if (lastSlash != std::string::npos && lastSlash >= 8) { // After https://
        return baseUrl.substr(0, lastSlash + 1) + relativeOrAbsoluteUrl;
    }

    return origin + "/" + relativeOrAbsoluteUrl;
}

StreamInfo CurlParser::Parse(const std::string& rawInput) {
    StreamInfo info;
    info.user_agent = DEFAULT_USER_AGENT;

    std::string cleaned = UnescapeCurl(rawInput);

    // Check if input is a curl command
    bool isCurl = (cleaned.find("curl ") != std::string::npos || cleaned.find("curl.exe") != std::string::npos);

    if (isCurl) {
        // 1. Extract URL: --url "..." or standard curl argument
        std::regex urlRegex(R"((?:--url|-u)?\s*["']?(https?://[^\s"'\\]+)["']?)", std::regex::icase);
        std::smatch urlMatch;
        if (std::regex_search(cleaned, urlMatch, urlRegex)) {
            info.url = urlMatch[1].str();
        }

        // 2. Extract Headers: -H "Key: Value" or -H 'Key: Value'
        std::regex headerRegex(R"(-H\s+["']([^"']+)["'])", std::regex::icase);
        auto headersBegin = std::sregex_iterator(cleaned.begin(), cleaned.end(), headerRegex);
        auto headersEnd = std::sregex_iterator();

        for (auto it = headersBegin; it != headersEnd; ++it) {
            std::string headerStr = (*it)[1].str();
            size_t colon = headerStr.find(':');
            if (colon != std::string::npos) {
                std::string key = headerStr.substr(0, colon);
                std::string val = headerStr.substr(colon + 1);

                // Trim whitespace
                key.erase(0, key.find_first_not_of(" \t\r\n"));
                key.erase(key.find_last_not_of(" \t\r\n") + 1);
                val.erase(0, val.find_first_not_of(" \t\r\n"));
                val.erase(val.find_last_not_of(" \t\r\n") + 1);

                std::transform(key.begin(), key.end(), key.begin(), ::tolower);
                info.headers[key] = val;
            }
        }

        // 3. Extract Cookie: -b "..." or --cookie "..."
        std::regex cookieRegex(R"((?:-b|--cookie)\s+["']([^"']+)["'])", std::regex::icase);
        std::smatch cookieMatch;
        if (std::regex_search(cleaned, cookieMatch, cookieRegex)) {
            if (info.headers.find("cookie") == info.headers.end()) {
                info.headers["cookie"] = cookieMatch[1].str();
            }
        }
    } else {
        // Plain URL passed
        std::regex urlRegex(R"(https?://[^\s"']+)");
        std::smatch urlMatch;
        if (std::regex_search(rawInput, urlMatch, urlRegex)) {
            info.url = urlMatch[0].str();
        }
    }

    // Dynamic origin and referer derivation
    std::string originFromUrl = ExtractOrigin(info.url);
    std::string defaultReferer = originFromUrl.empty() ? "" : (originFromUrl + "/");

    auto refIt = info.headers.find("referer");
    info.referer = (refIt != info.headers.end()) ? refIt->second : defaultReferer;

    auto origIt = info.headers.find("origin");
    info.origin = (origIt != info.headers.end()) ? origIt->second : originFromUrl;

    auto uaIt = info.headers.find("user-agent");
    if (uaIt != info.headers.end()) {
        info.user_agent = uaIt->second;
    }

    auto cookieIt = info.headers.find("cookie");
    if (cookieIt != info.headers.end()) {
        info.cookie = cookieIt->second;
    }

    return info;
}

} // namespace OmniStream
