#include "curl_parser.hpp"

namespace OmniStream {

std::string CurlParser::UnescapeCurl(const std::string& input) {
    std::string result;
    result.reserve(input.size());
    for (size_t i = 0; i < input.size(); ++i) {
        if ((input[i] == '\\' || input[i] == '^') && i + 1 < input.size()) {
            char next = input[i + 1];
            if (next == '\n' || next == '\r') {
                i++;
                if (next == '\r' && i + 1 < input.size() && input[i + 1] == '\n') i++;
                result += ' ';
                continue;
            }
            if (next == '"' || next == '\'' || next == '\\' || next == '^') {
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
        // 1. Explicit --url argument: --url "..."
        std::regex explicitUrlRegex(R"(--url\s+["']?([^\s"'\\]+)["']?)", std::regex::icase);
        std::smatch urlMatch;
        if (std::regex_search(cleaned, urlMatch, explicitUrlRegex)) {
            info.url = urlMatch[1].str();
        } else {
            // Positional URL argument after curl (excluding option flags like -s, -H "...")
            std::regex posUrlRegex(R"(curl(?:\.exe)?(?:\s+(?:--?[a-zA-Z0-9_\-]+(?:\s+["'][^"']*["']|\s+[^\s"'\\]+)?))*\s+["']?([^\s"'\\]+)["']?)", std::regex::icase);
            if (std::regex_search(cleaned, urlMatch, posUrlRegex)) {
                std::string cand = urlMatch[1].str();
                if (!cand.empty() && cand[0] != '-') {
                    info.url = cand;
                }
            }
            // Fallback: match first URL or relative path from command after stripping -H headers
            if (info.url.empty()) {
                std::string noHeaders = std::regex_replace(cleaned, std::regex(R"(-H\s+["'][^"']*["'])", std::regex::icase), "");
                std::regex candRegex(R"(["']?(https?://[^\s"'\\]+|\/[^\s"'\\]+)["']?)");
                if (std::regex_search(noHeaders, urlMatch, candRegex)) {
                    info.url = urlMatch[1].str();
                }
            }
        }

        while (!info.url.empty() && (info.url.front() == '"' || info.url.front() == '\'')) {
            info.url.erase(0, 1);
        }
        while (!info.url.empty() && (info.url.back() == '"' || info.url.back() == '\'')) {
            info.url.pop_back();
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
        // Plain URL passed (supports absolute and relative URLs)
        std::regex urlRegex(R"(https?://[^\s"']+)");
        std::smatch urlMatch;
        if (std::regex_search(rawInput, urlMatch, urlRegex)) {
            info.url = urlMatch[0].str();
        } else {
            std::regex relUrlRegex(R"(\/[^\s"']+)");
            if (std::regex_search(rawInput, urlMatch, relUrlRegex)) {
                info.url = urlMatch[0].str();
            }
        }
    }

    auto refIt = info.headers.find("referer");
    auto origIt = info.headers.find("origin");

    // If info.url is relative, resolve it using referer or origin
    if (!info.url.empty() && (info.url.rfind("/", 0) == 0 || info.url.find("://") == std::string::npos)) {
        std::string baseHost;
        if (origIt != info.headers.end() && !origIt->second.empty()) {
            baseHost = ExtractOrigin(origIt->second);
        }
        if (baseHost.empty() && refIt != info.headers.end() && !refIt->second.empty()) {
            baseHost = ExtractOrigin(refIt->second);
        }
        // Fallback: search for any https?:// in cleaned or rawInput
        if (baseHost.empty()) {
            std::regex hostFinder(R"(https?://[a-zA-Z0-9.\-]+(?::\d+)?)", std::regex::icase);
            std::smatch mH;
            if (std::regex_search(cleaned, mH, hostFinder)) {
                baseHost = mH[0].str();
            }
        }
        if (!baseHost.empty()) {
            info.url = ResolveUrl(baseHost, info.url);
        }
    }

    // Dynamic origin and referer derivation
    std::string originFromUrl = ExtractOrigin(info.url);
    std::string defaultReferer = originFromUrl.empty() ? "" : (originFromUrl + "/");

    info.referer = (refIt != info.headers.end()) ? refIt->second : defaultReferer;
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
