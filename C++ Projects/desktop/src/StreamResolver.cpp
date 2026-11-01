#include "StreamResolver.hpp"
#include <windows.h>
#include <winhttp.h>
#include <regex>
#include <iostream>

#pragma comment(lib, "winhttp.lib")

namespace OmniStream {

StreamResolver& StreamResolver::GetInstance() {
    static StreamResolver instance;
    return instance;
}

std::string StreamResolver::FetchHtml(const std::string& url, const std::string& referer) {
    if (url.empty()) return "";

    HINTERNET hSession = WinHttpOpen(
        L"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );
    if (!hSession) return "";

    std::wstring wurl(url.begin(), url.end());
    URL_COMPONENTSW wcomp = { sizeof(URL_COMPONENTSW) };
    wchar_t whost[256] = { 0 };
    wchar_t wpath[2048] = { 0 };
    wcomp.lpszHostName = whost;
    wcomp.dwHostNameLength = 256;
    wcomp.lpszUrlPath = wpath;
    wcomp.dwUrlPathLength = 2048;

    if (!WinHttpCrackUrl(wurl.c_str(), 0, 0, &wcomp)) {
        WinHttpCloseHandle(hSession);
        return "";
    }

    HINTERNET hConnect = WinHttpConnect(hSession, whost, wcomp.nPort, 0);
    if (!hConnect) {
        WinHttpCloseHandle(hSession);
        return "";
    }

    DWORD flags = (wcomp.nScheme == INTERNET_SCHEME_HTTPS) ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(hConnect, L"GET", wpath, nullptr, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        return "";
    }

    // Set timeouts: 5s connect, 8s send, 8s receive
    WinHttpSetTimeouts(hRequest, 5000, 5000, 8000, 8000);

    if (!referer.empty()) {
        std::wstring wref = L"Referer: " + std::wstring(referer.begin(), referer.end());
        WinHttpAddRequestHeaders(hRequest, wref.c_str(), -1, WINHTTP_ADDREQ_FLAG_ADD);
    }

    std::string html_content;
    if (WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) &&
        WinHttpReceiveResponse(hRequest, nullptr)) {
        DWORD bytes_avail = 0;
        while (WinHttpQueryDataAvailable(hRequest, &bytes_avail) && bytes_avail > 0) {
            std::vector<char> buf(bytes_avail);
            DWORD bytes_read = 0;
            if (WinHttpReadData(hRequest, buf.data(), bytes_avail, &bytes_read) && bytes_read > 0) {
                html_content.append(buf.data(), bytes_read);
            }
        }
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);

    return html_content;
}

std::string StreamResolver::DirectScan(const std::string& html, const std::string& base_url) {
    if (html.empty()) return "";

    // 1. Check for stream extensions
    static const std::regex stream_regex(R"(https?://[^\s"'<>\\]+?\.(?:m3u8|mp4|mpd)[^\s"'<>\\]*)", std::regex::icase);
    std::smatch match;
    auto words_begin = std::sregex_iterator(html.begin(), html.end(), stream_regex);
    auto words_end = std::sregex_iterator();

    for (std::sregex_iterator i = words_begin; i != words_end; ++i) {
        std::string cand = (*i).str();
        std::string lo = Utils::ToLower(cand);
        if (lo.find("preview") == std::string::npos && lo.find("sample") == std::string::npos && lo.find("trailer") == std::string::npos) {
            return cand;
        }
    }

    // 2. Check for iframe embeds
    static const std::regex iframe_regex(R"(<iframe[^>]+?src=["'](https?://[^"']+)["'])", std::regex::icase);
    auto ifr_begin = std::sregex_iterator(html.begin(), html.end(), iframe_regex);
    for (std::sregex_iterator i = ifr_begin; i != words_end; ++i) {
        std::string ifr_url = (*i)[1].str();
        std::string lo = Utils::ToLower(ifr_url);
        if (lo.find("google") != std::string::npos || lo.find("facebook") != std::string::npos || lo.find("disqus") != std::string::npos) {
            continue;
        }
        std::string ifr_html = FetchHtml(ifr_url, base_url);
        if (!ifr_html.empty()) {
            std::string nested = DirectScan(ifr_html, ifr_url);
            if (!nested.empty()) return nested;
        }
    }

    return "";
}

StreamResolver::ResolvedStream StreamResolver::Resolve(
    const std::string& page_url,
    const std::string& item_id,
    const std::string& title,
    LogCallback log_cb,
    int timeout_sec
) {
    ResolvedStream res;
    if (page_url.empty()) return res;

    // Check if page_url is already a direct media stream
    std::string lo = Utils::ToLower(page_url);
    size_t q_pos = lo.find('?');
    std::string clean_lo = (q_pos != std::string::npos) ? lo.substr(0, q_pos) : lo;

    if (clean_lo.ends_with(".m3u8") || clean_lo.ends_with(".mpd") || clean_lo.ends_with(".mp4") || clean_lo.ends_with(".mkv")) {
        res.url = page_url;
        res.success = true;
        return res;
    }

    if (log_cb) {
        log_cb("  [Resolver] Resolving stream for: " + (title.empty() ? page_url : title));
    }

    // Direct HTML/iframe crawl
    std::string direct_stream = DirectScan(FetchHtml(page_url), page_url);
    if (!direct_stream.empty()) {
        if (log_cb) log_cb("  [Resolver] Direct extraction succeeded: " + direct_stream.substr(0, 70) + "...");
        res.url = direct_stream;
        res.success = true;
        return res;
    }

    // Delegate to Chrome Extension background sniffing
    if (log_cb) {
        log_cb("  [Resolver] Protected page; delegating to Chrome Extension background sniffer...");
    }

    std::unique_lock<std::mutex> lock(mutex_);
    pending_tasks_[item_id] = page_url;

    bool signaled = cv_.wait_for(lock, std::chrono::seconds(timeout_sec), [&]() {
        return cache_.find(item_id) != cache_.end();
    });

    pending_tasks_.erase(item_id);

    if (signaled && cache_.find(item_id) != cache_.end()) {
        res = cache_[item_id];
        cache_.erase(item_id);
        if (log_cb) log_cb("  [Resolver] Chrome Extension captured stream: " + res.url.substr(0, 70) + "...");
    } else {
        if (log_cb) log_cb("  [Resolver] Resolution timed out or blocked.");
    }

    return res;
}

void StreamResolver::NotifyResolvedFromBridge(
    const std::string& item_id,
    const std::string& stream_url,
    const std::string& curl_cmd,
    const std::string& referer
) {
    std::lock_guard<std::mutex> lock(mutex_);
    ResolvedStream stream;
    stream.url = stream_url;
    stream.curl_cmd = curl_cmd;
    stream.referer = referer;
    stream.success = !stream_url.empty();

    cache_[item_id] = stream;
    cv_.notify_all();
}

std::optional<std::pair<std::string, std::string>> StreamResolver::GetPendingTask() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!pending_tasks_.empty()) {
        auto it = pending_tasks_.begin();
        return std::make_pair(it->first, it->second);
    }
    return std::nullopt;
}

} // namespace OmniStream
