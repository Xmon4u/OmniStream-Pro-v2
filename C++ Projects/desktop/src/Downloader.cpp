#include "Downloader.hpp"
#include "SettingsManager.hpp"
#include "MetadataResolver.hpp"
#include <filesystem>
#include <iostream>
#include <fstream>
#include <sstream>
#include <regex>
#include <vector>
#include <algorithm>
#include <chrono>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

namespace OmniStream {

Downloader::Downloader() {
    // Create Windows Job Object to kill child processes automatically on application exit
    job_object_ = CreateJobObjectW(nullptr, nullptr);
    if (job_object_) {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION jeli = { 0 };
        jeli.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job_object_, JobObjectExtendedLimitInformation, &jeli, sizeof(jeli));
    }
}

Downloader::~Downloader() {
    Abort();
    if (job_object_) {
        CloseHandle(job_object_);
        job_object_ = nullptr;
    }
}

void Downloader::Abort() {
    aborted_.store(true);
    if (child_process_) {
        TerminateProcess(child_process_, 1);
        CloseHandle(child_process_);
        child_process_ = nullptr;
    }
}

std::string Downloader::FindBinary(const std::string& name) const {
    char exe_buf[MAX_PATH];
    GetModuleFileNameA(nullptr, exe_buf, MAX_PATH);
    std::filesystem::path app_dir = std::filesystem::path(exe_buf).parent_path();

    std::vector<std::filesystem::path> search_paths = {
        app_dir / "bin" / (name + ".exe"),
        app_dir / (name + ".exe"),
        std::filesystem::current_path() / "bin" / (name + ".exe"),
        std::filesystem::current_path() / "desktop" / "bin" / (name + ".exe"),
        std::filesystem::path("D:\\05_Projects\\OmniStream-Pro-v2-2.5.0\\desktop\\bin") / (name + ".exe"),
        std::filesystem::path("D:\\05_Projects\\OmniStream-Pro-v2-2.5.0\\C++ Projects\\desktop\\bin") / (name + ".exe")
    };

    for (const auto& p : search_paths) {
        if (std::filesystem::exists(p)) {
            return p.string();
        }
    }
    return name + ".exe";
}

std::string Downloader::StripAnsiCodes(const std::string& text) const {
    static const std::regex ansi_regex(R"(\x1b\[[0-9;]*[a-zA-Z])");
    return std::regex_replace(text, ansi_regex, "");
}

void Downloader::ParseOutputLine(const std::string& line, DownloadProgress& progress) const {
    // 1. Percentage check
    static const std::regex pct_regex(R"(\b(\d+(?:\.\d+)?)%)");
    std::smatch match;
    if (std::regex_search(line, match, pct_regex)) {
        try { progress.percent = std::stod(match[1].str()); } catch (...) {}
    }

    // 2. Speed check
    static const std::regex speed_regex(R"(\b(\d+(?:\.\d+)?\s*(?:MB|KB|GB|B)/s))", std::regex::icase);
    if (std::regex_search(line, match, speed_regex)) {
        progress.speed = match[1].str();
    }

    // 3. Size check
    static const std::regex size_regex(R"(\b(\d+(?:\.\d+)?\s*(?:MB|KB|GB))\b)", std::regex::icase);
    if (std::regex_search(line, match, size_regex)) {
        progress.size = match[1].str();
    }

    // 4. ETA check
    static const std::regex eta_regex(R"(\b(\d+h\d+m\d+s|\d+m\d+s|\d+s)\b)", std::regex::icase);
    if (std::regex_search(line, match, eta_regex)) {
        progress.eta = match[1].str();
    }

    if (!line.empty()) {
        progress.message = line;
    }
}

Downloader::ExecutionResult Downloader::RunProcess(
    const std::wstring& cmd_line,
    const std::string& item_id,
    ProgressCallback progress_cb,
    LogCallback log_cb
) {
    ExecutionResult result;
    aborted_.store(false);

    HANDLE hReadPipe = nullptr;
    HANDLE hWritePipe = nullptr;
    SECURITY_ATTRIBUTES sa = { sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE };

    if (!CreatePipe(&hReadPipe, &hWritePipe, &sa, 0)) {
        result.error_reason = "Failed to create process output pipe";
        return result;
    }
    SetHandleInformation(hReadPipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si = { sizeof(STARTUPINFOW) };
    si.dwFlags = STARTF_USESHOWWINDOW | STARTF_USESTDHANDLES;
    si.wShowWindow = SW_HIDE;
    si.hStdOutput = hWritePipe;
    si.hStdError = hWritePipe;

    PROCESS_INFORMATION pi = { 0 };
    std::wstring cmd_copy = cmd_line;

    BOOL ok = CreateProcessW(
        nullptr,
        cmd_copy.data(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &si,
        &pi
    );

    CloseHandle(hWritePipe); // Close write end in parent

    if (!ok) {
        CloseHandle(hReadPipe);
        result.error_reason = "Failed to start downloader executable";
        return result;
    }

    child_process_ = pi.hProcess;
    if (job_object_) {
        AssignProcessToJobObject(job_object_, pi.hProcess);
    }
    CloseHandle(pi.hThread);

    char buffer[4096];
    DWORD bytes_read = 0;
    std::string line_accum;
    std::vector<std::string> recent_lines;
    DownloadProgress progress;

    while (!aborted_.load() && ReadFile(hReadPipe, buffer, sizeof(buffer) - 1, &bytes_read, nullptr) && bytes_read > 0) {
        buffer[bytes_read] = '\0';
        for (DWORD i = 0; i < bytes_read; ++i) {
            char c = buffer[i];
            if (c == '\r' || c == '\n') {
                if (!line_accum.empty()) {
                    std::string clean = StripAnsiCodes(line_accum);
                    if (!clean.empty()) {
                        ParseOutputLine(clean, progress);
                        recent_lines.push_back(clean);
                        if (recent_lines.size() > 20) recent_lines.erase(recent_lines.begin());

                        if (progress_cb) progress_cb(item_id, progress);
                        if (log_cb && (clean.find("ERROR") != std::string::npos || clean.find("WARN") != std::string::npos || clean.find("Mux") != std::string::npos)) {
                            log_cb("  " + clean);
                        }
                    }
                    line_accum.clear();
                }
            } else {
                line_accum += c;
            }
        }
    }

    CloseHandle(hReadPipe);
    WaitForSingleObject(pi.hProcess, INFINITE);

    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    CloseHandle(pi.hProcess);
    child_process_ = nullptr;

    result.exit_code = static_cast<int>(exit_code);
    result.success = (exit_code == 0 && !aborted_.load());

    if (result.success) {
        for (const auto& l : recent_lines) {
            size_t mux_pos = l.find("Mux to: ");
            if (mux_pos != std::string::npos) {
                result.final_file_path = Utils::Trim(l.substr(mux_pos + 8));
                break;
            }
            size_t out_pos = l.find("Writing output to: ");
            if (out_pos != std::string::npos) {
                result.final_file_path = Utils::Trim(l.substr(out_pos + 19));
                break;
            }
        }
    } else {
        std::string combined;
        for (const auto& l : recent_lines) combined += " " + Utils::ToLower(l);

        // Filter out .NET CLR stack frames: lines starting with "   at ", "--- End of", etc.
        std::vector<std::string> meaningful_error_lines;
        for (const auto& l : recent_lines) {
            std::string tr = Utils::Trim(l);
            if (tr.empty()) continue;
            if (tr.rfind("at ", 0) == 0 || tr.find("at System.") != std::string::npos ||
                tr.find("at N_m3u8DL_RE.") != std::string::npos || tr.rfind("--- End of", 0) == 0 ||
                tr.find("InvocationPipeline") != std::string::npos || tr.find(".MoveNext()") != std::string::npos ||
                tr.find("+ 0x") != std::string::npos) {
                continue; // Skip stack trace frames!
            }
            meaningful_error_lines.push_back(tr);
        }

        if (combined.find("no such host") != std::string::npos || combined.find("socketexception") != std::string::npos ||
            combined.find("could not resolve host") != std::string::npos || combined.find("name_not_resolved") != std::string::npos) {
            result.error_reason = "Host unreachable or DNS lookup failed. The streaming server is offline.";
            result.fix_hint = "The video hosting server could not be reached. Verify your connection or try another source.";
        } else if (combined.find("notsupportedexception") != std::string::npos || combined.find("input not supported") != std::string::npos) {
            result.error_reason = "Input not supported: Stream is a direct media file, not an M3U8/DASH playlist.";
            result.fix_hint = "Switching to Native Direct Download Engine.";
        } else if (combined.find("drm") != std::string::npos || combined.find("widevine") != std::string::npos || combined.find("sample-aes") != std::string::npos) {
            result.error_reason = "This stream is DRM-protected and not supported.";
            result.fix_hint = "OmniStream does not support bypassing DRM encryption.";
        } else if (combined.find("403") != std::string::npos || combined.find("forbidden") != std::string::npos || combined.find("401") != std::string::npos) {
            result.error_reason = "Remote stream token expired (HTTP 401/403 Forbidden).";
            result.fix_hint = "Your stream token has expired. Please re-open the video in Chrome and capture a fresh link.";
        } else if (combined.find("404") != std::string::npos || combined.find("not found") != std::string::npos) {
            result.error_reason = "Stream file not found on server (HTTP 404).";
            result.fix_hint = "The video file was removed from the remote host.";
        } else if (combined.find("failed to execute action after") != std::string::npos) {
            result.error_reason = "Connection failed after multiple retries.";
            result.fix_hint = "The remote host failed to respond in time or closed the connection.";
        } else if (combined.find("cannot find any streams") != std::string::npos) {
            result.error_reason = "No media streams found in manifest.";
            result.fix_hint = "The playlist does not contain compatible audio/video streams.";
        } else if (!meaningful_error_lines.empty()) {
            std::string err = meaningful_error_lines.back();
            // Clean common exception wrappers
            const std::string p1 = "Unhandled exception: System.Exception: ";
            const std::string p2 = "Unhandled exception: System.NotSupportedException: ";
            const std::string p3 = "Unhandled exception: ";
            if (err.find(p1) == 0) err = err.substr(p1.length());
            else if (err.find(p2) == 0) err = err.substr(p2.length());
            else if (err.find(p3) == 0) err = err.substr(p3.length());
            result.error_reason = err;
            result.fix_hint = "Check your network connection and verify the stream URL.";
        } else {
            result.error_reason = "Downloader exited with error";
            result.fix_hint = "Check your network connection and verify the stream URL.";
        }
    }

    return result;
}

Downloader::StreamDetails Downloader::ParseStreamDetails(const DownloadItem& item) {
    StreamDetails details;
    details.user_agent = item.user_agent.empty()
        ? "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        : item.user_agent;
    details.referer = item.referer;
    details.origin = item.origin;
    details.cookie = item.cookie;

    std::string raw = item.input;
    if (raw.find("curl ") != std::string::npos || raw.find("curl.exe ") != std::string::npos) {
        std::regex url_regex(R"((?:--url\s+["']?|curl(?:\.exe)?\s+["']?)(https?://[^\s"'\\]+))", std::regex::icase);
        std::smatch m;
        if (std::regex_search(raw, m, url_regex)) {
            details.url = m[1].str();
        } else {
            std::regex gen_url(R"(https?://[^\s"'\\]+)", std::regex::icase);
            if (std::regex_search(raw, m, gen_url)) {
                details.url = m[0].str();
            }
        }

        std::regex ref_regex(R"(-H\s+["']Referer:\s*([^"']+)["'])", std::regex::icase);
        if (std::regex_search(raw, m, ref_regex)) {
            details.referer = m[1].str();
        }

        std::regex org_regex(R"(-H\s+["']Origin:\s*([^"']+)["'])", std::regex::icase);
        if (std::regex_search(raw, m, org_regex)) {
            details.origin = m[1].str();
        }

        std::regex ua_regex(R"(-H\s+["']User-Agent:\s*([^"']+)["'])", std::regex::icase);
        if (std::regex_search(raw, m, ua_regex)) {
            details.user_agent = m[1].str();
        }

        std::regex ck_regex(R"(-H\s+["']Cookie:\s*([^"']+)["'])", std::regex::icase);
        if (std::regex_search(raw, m, ck_regex)) {
            details.cookie = m[1].str();
        }
    } else {
        std::string trimmed = Utils::Trim(raw);
        if (!trimmed.empty() && (trimmed.front() == '"' || trimmed.front() == '\'')) {
            trimmed = trimmed.substr(1);
        }
        if (!trimmed.empty() && (trimmed.back() == '"' || trimmed.back() == '\'')) {
            trimmed.pop_back();
        }
        details.url = trimmed;
    }

    if (details.referer.empty() && !item.page_url.empty()) {
        details.referer = item.page_url;
    }
    if (details.origin.empty() && !details.referer.empty()) {
        size_t p = details.referer.find("://");
        if (p != std::string::npos) {
            size_t slash = details.referer.find('/', p + 3);
            details.origin = (slash != std::string::npos) ? details.referer.substr(0, slash) : details.referer;
        }
    }

    return details;
}

bool Downloader::IsDirectMediaUrl(const std::string& url_or_cmd, const std::string& media_type) {
    std::string s = Utils::ToLower(url_or_cmd);
    std::string mt = Utils::ToLower(media_type);

    // If explicitly marked as HLS or DASH manifest, it is an HLS/DASH stream
    if (s.find(".m3u8") != std::string::npos || s.find(".mpd") != std::string::npos ||
        s.find("/hls/") != std::string::npos || s.find("/dash/") != std::string::npos ||
        s.find("master.m3u8") != std::string::npos || s.find("index.m3u8") != std::string::npos ||
        mt.find("m3u8") != std::string::npos || mt.find("mpd") != std::string::npos ||
        mt.find("hls") != std::string::npos || mt.find("dash") != std::string::npos) {
        return false;
    }

    // Direct video extensions
    static const std::vector<std::string> direct_exts = {
        ".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi", ".flv", ".ts", ".mp3", ".m4a", ".aac", ".wav", ".ogg"
    };
    for (const auto& ext : direct_exts) {
        if (s.find(ext) != std::string::npos) {
            return true;
        }
    }

    if (mt.find("mp4") != std::string::npos || mt.find("video") != std::string::npos ||
        mt.find("audio") != std::string::npos || mt.find("webm") != std::string::npos ||
        mt.find("mkv") != std::string::npos || mt.find("direct") != std::string::npos) {
        return true;
    }

    // Any stream URL that does not have .m3u8 or .mpd is a direct stream (e.g. hashed CDN URLs)
    return true;
}

Downloader::ExecutionResult Downloader::ExecuteDirectDownload(
    const DownloadItem& item,
    const StreamDetails& details,
    ProgressCallback progress_cb,
    LogCallback log_cb
) {
    ExecutionResult result;
    result.success = false;
    result.exit_code = 1;

    if (log_cb) {
        log_cb("[Direct Download Engine] Native HTTP streaming download initiated.");
        log_cb("  Source URL: " + details.url.substr(0, 80) + (details.url.length() > 80 ? "..." : ""));
        log_cb("  Referer: " + (details.referer.empty() ? "(none)" : details.referer));
        log_cb("  Target: " + item.title);
    }

    std::string ext = ".mp4";
    std::string clean_url = details.url;
    size_t q = clean_url.find('?');
    if (q != std::string::npos) clean_url = clean_url.substr(0, q);
    size_t dot = clean_url.rfind('.');
    if (dot != std::string::npos) {
        std::string cand_ext = Utils::ToLower(clean_url.substr(dot));
        if (cand_ext == ".mp4" || cand_ext == ".mkv" || cand_ext == ".webm" ||
            cand_ext == ".ts" || cand_ext == ".m4v" || cand_ext == ".mov" ||
            cand_ext == ".avi" || cand_ext == ".mp3" || cand_ext == ".m4a") {
            ext = cand_ext;
        }
    }

    std::string clean_title = MetadataResolver::SanitizeInputTitle(item.title);
    if (clean_title.empty()) clean_title = "OmniStream_Video";

    std::filesystem::path dir_path(item.save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item.save_dir);
    std::error_code ec;
    std::filesystem::create_directories(dir_path, ec);

    std::filesystem::path target_file = dir_path / (clean_title + ext);
    uint64_t existing_bytes = 0;
    if (std::filesystem::exists(target_file)) {
        existing_bytes = std::filesystem::file_size(target_file, ec);
    }

    std::wstring wurl = Utils::Utf8ToWide(details.url);
    URL_COMPONENTSW wcomp = { sizeof(URL_COMPONENTSW) };
    wchar_t whost[1024] = { 0 };
    wchar_t wpath[4096] = { 0 };
    wcomp.lpszHostName = whost;
    wcomp.dwHostNameLength = 1024;
    wcomp.lpszUrlPath = wpath;
    wcomp.dwUrlPathLength = 4096;

    if (!WinHttpCrackUrl(wurl.c_str(), 0, 0, &wcomp)) {
        result.error_reason = "Invalid or unparseable stream URL: " + details.url;
        result.fix_hint = "Please recapture a fresh direct video link from the extension.";
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    std::wstring ua = details.user_agent.empty()
        ? L"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        : Utils::Utf8ToWide(details.user_agent);

    HINTERNET hSession = WinHttpOpen(
        ua.c_str(),
        WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );
    if (!hSession) {
        result.error_reason = "Failed to initialize WinHTTP session (Error: " + std::to_string(GetLastError()) + ")";
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    HINTERNET hConnect = WinHttpConnect(hSession, whost, wcomp.nPort, 0);
    if (!hConnect) {
        DWORD err = GetLastError();
        WinHttpCloseHandle(hSession);
        std::string host_str = Utils::WideToUtf8(whost);
        result.error_reason = "Failed to connect to host: " + host_str + " (Error: " + std::to_string(err) + ")";
        result.fix_hint = "Host unreachable or DNS lookup failed. Please check your network.";
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    DWORD req_flags = (wcomp.nScheme == INTERNET_SCHEME_HTTPS) ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"GET",
        wpath,
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        req_flags
    );
    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        result.error_reason = "Failed to open WinHTTP request";
        return result;
    }

    DWORD redirectPolicy = WINHTTP_OPTION_REDIRECT_POLICY_ALWAYS;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_REDIRECT_POLICY, &redirectPolicy, sizeof(redirectPolicy));
    WinHttpSetTimeouts(hRequest, 15000, 15000, 30000, 30000);

    std::wstring headers;
    if (!details.referer.empty()) {
        headers += L"Referer: " + Utils::Utf8ToWide(details.referer) + L"\r\n";
    }
    if (!details.origin.empty()) {
        headers += L"Origin: " + Utils::Utf8ToWide(details.origin) + L"\r\n";
    }
    if (!details.cookie.empty()) {
        headers += L"Cookie: " + Utils::Utf8ToWide(details.cookie) + L"\r\n";
    }
    headers += L"Accept: */*\r\n";
    headers += L"Connection: keep-alive\r\n";

    if (existing_bytes > 0) {
        headers += L"Range: bytes=" + std::to_wstring(existing_bytes) + L"-\r\n";
        if (log_cb) log_cb("  [HTTP Range Resume] Requesting remaining bytes from offset " + std::to_string(existing_bytes));
    }

    WinHttpAddRequestHeaders(hRequest, headers.c_str(), static_cast<DWORD>(-1L), WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE);

    if (!WinHttpSendRequest(hRequest, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
        !WinHttpReceiveResponse(hRequest, nullptr)) {
        DWORD err = GetLastError();
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        result.error_reason = "HTTP connection failed (WinHTTP error " + std::to_string(err) + ")";
        result.fix_hint = "The remote server rejected the connection or closed it prematurely.";
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    DWORD statusCode = 0;
    DWORD scSize = sizeof(statusCode);
    WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER, nullptr, &statusCode, &scSize, nullptr);

    bool is_resume_success = (statusCode == 206);
    if (statusCode < 200 || statusCode >= 400) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        result.error_reason = "Remote server returned HTTP " + std::to_string(statusCode);
        if (statusCode == 403) {
            result.fix_hint = "Stream authorization expired (403 Forbidden). Refresh the video page in Chrome.";
        } else if (statusCode == 404) {
            result.fix_hint = "Video file not found on CDN (404 Not Found).";
        }
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    // Check if the response is actually an M3U8 / DASH playlist
    wchar_t ctBuf[128] = { 0 };
    DWORD ctSize = sizeof(ctBuf);
    if (WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_CONTENT_TYPE, nullptr, ctBuf, &ctSize, nullptr)) {
        std::string ct = Utils::ToLower(Utils::WideToUtf8(ctBuf));
        if (ct.find("mpegurl") != std::string::npos || ct.find("dash") != std::string::npos) {
            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            WinHttpCloseHandle(hSession);
            result.error_reason = "Server returned manifest content-type (" + ct + ")";
            return result; // triggers fallback to HLS/DASH engine!
        }
        if (ct.find("video/webm") != std::string::npos) ext = ".webm";
        else if (ct.find("video/x-matroska") != std::string::npos) ext = ".mkv";
        else if (ct.find("video/mp2t") != std::string::npos) ext = ".ts";
    }

    wchar_t clBuf[64] = { 0 };
    DWORD clSize = sizeof(clBuf);
    uint64_t totalBytes = 0;
    uint64_t downloadedBytes = 0;
    if (WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_CONTENT_LENGTH, nullptr, clBuf, &clSize, nullptr)) {
        uint64_t cl = _wtoi64(clBuf);
        if (is_resume_success) {
            downloadedBytes = existing_bytes;
            totalBytes = existing_bytes + cl;
        } else {
            totalBytes = cl;
        }
    }

    std::ios_base::openmode open_mode = std::ios::binary;
    if (is_resume_success) {
        open_mode |= std::ios::app;
        if (log_cb) log_cb("  [Resuming] Appending to existing file from " + std::to_string(existing_bytes / (1024 * 1024)) + " MB");
    } else {
        open_mode |= std::ios::trunc;
        downloadedBytes = 0;
    }

    std::ofstream outfile(target_file, open_mode);
    if (!outfile.is_open()) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        WinHttpCloseHandle(hSession);
        result.error_reason = "Failed to create destination file: " + target_file.string();
        return result;
    }

    if (log_cb) {
        std::string szStr = (totalBytes > 0) ? (std::to_string(totalBytes / (1024 * 1024)) + " MB") : "Chunked / Unknown";
        log_cb("  Total Size: " + szStr);
        log_cb("  Downloading media chunks directly...");
    }

    const DWORD CHUNK_SIZE = 64 * 1024;
    std::vector<char> buffer(CHUNK_SIZE);
    auto startTime = std::chrono::steady_clock::now();
    auto lastProgressTime = startTime;

    DownloadProgress progress;
    progress.percent = 0.0;
    progress.speed = "0.0 MB/s";
    progress.size = (totalBytes > 0) ? ("0 MB / " + std::to_string(totalBytes / (1024 * 1024)) + " MB") : "0 MB";
    progress.eta = "--:--";
    progress.message = "Downloading...";
    if (progress_cb) progress_cb(item.id, progress);

    while (!aborted_.load()) {
        DWORD bytesAvail = 0;
        if (!WinHttpQueryDataAvailable(hRequest, &bytesAvail) || bytesAvail == 0) {
            break;
        }

        DWORD toRead = (std::min)(bytesAvail, CHUNK_SIZE);
        DWORD bytesRead = 0;
        if (!WinHttpReadData(hRequest, buffer.data(), toRead, &bytesRead) || bytesRead == 0) {
            break;
        }

        outfile.write(buffer.data(), bytesRead);
        downloadedBytes += bytesRead;

        auto now = std::chrono::steady_clock::now();
        double elapsedSec = std::chrono::duration<double>(now - startTime).count();
        double sinceLastProgress = std::chrono::duration<double>(now - lastProgressTime).count();

        if (sinceLastProgress >= 0.15) {
            lastProgressTime = now;
            double speedBps = (elapsedSec > 0.001) ? ((downloadedBytes - (is_resume_success ? existing_bytes : 0)) / elapsedSec) : 0.0;
            double speedMBps = speedBps / (1024.0 * 1024.0);

            char spdBuf[32];
            snprintf(spdBuf, sizeof(spdBuf), "%.1f MB/s", speedMBps);
            progress.speed = spdBuf;

            if (totalBytes > 0) {
                progress.percent = std::clamp((double)downloadedBytes * 100.0 / (double)totalBytes, 0.0, 99.9);
                uint64_t remainingBytes = (totalBytes > downloadedBytes) ? (totalBytes - downloadedBytes) : 0;
                double etaSec = (speedBps > 1000) ? (remainingBytes / speedBps) : 0.0;
                int etaM = (int)(etaSec / 60);
                int etaS = (int)(etaSec) % 60;
                char etaBuf[32];
                snprintf(etaBuf, sizeof(etaBuf), "%02d:%02d", etaM, etaS);
                progress.eta = etaBuf;

                char szBuf[64];
                snprintf(szBuf, sizeof(szBuf), "%.1f MB / %.1f MB", (double)downloadedBytes / (1024.0 * 1024.0), (double)totalBytes / (1024.0 * 1024.0));
                progress.size = szBuf;
            } else {
                progress.percent = std::min(95.0, 5.0 + (downloadedBytes / (1024.0 * 1024.0)) * 2.0);
                char szBuf[64];
                snprintf(szBuf, sizeof(szBuf), "%.1f MB", (double)downloadedBytes / (1024.0 * 1024.0));
                progress.size = szBuf;
                progress.eta = "--:--";
            }

            progress.message = "Downloading: " + progress.size + " (" + progress.speed + ")";
            if (progress_cb) progress_cb(item.id, progress);
        }
    }

    outfile.close();
    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    WinHttpCloseHandle(hSession);

    if (aborted_.load()) {
        result.error_reason = "Download paused / stopped by user.";
        if (log_cb) log_cb("  [Paused] " + result.error_reason);
        return result;
    }

    if (downloadedBytes == 0) {
        std::error_code remove_ec;
        std::filesystem::remove(target_file, remove_ec);
        result.error_reason = "Server sent 0 bytes.";
        result.fix_hint = "The download link may be protected or expired.";
        if (log_cb) log_cb("  [Error] " + result.error_reason);
        return result;
    }

    progress.percent = 100.0;
    progress.eta = "00:00";
    progress.message = "Download complete!";
    if (progress_cb) progress_cb(item.id, progress);

    result.success = true;
    result.final_file_path = target_file.string();
    result.exit_code = 0;
    if (log_cb) {
        log_cb("  [SUCCESS] Direct media download completed successfully!");
        log_cb("  Saved File: " + target_file.string());
        log_cb("  Total Size: " + std::to_string(downloadedBytes / (1024 * 1024)) + " MB");
    }
    return result;
}

Downloader::ExecutionResult Downloader::ExecuteDownload(
    const DownloadItem& item,
    ProgressCallback progress_cb,
    LogCallback log_cb
) {
    StreamDetails details = ParseStreamDetails(item);

    // 1. Direct Media Streaming Download (MP4, MKV, WebM, etc.)
    bool is_direct = IsDirectMediaUrl(details.url, item.media_type);

    if (is_direct) {
        auto res = ExecuteDirectDownload(item, details, progress_cb, log_cb);
        if (!res.success && !aborted_.load()) {
            std::string err_lo = Utils::ToLower(res.error_reason);
            if (err_lo.find("manifest") != std::string::npos || err_lo.find("mpegurl") != std::string::npos || err_lo.find("dash") != std::string::npos) {
                if (log_cb) log_cb("  [Auto-Switch] Content is an M3U8/DASH manifest. Switching to HLS/DASH engine...");
                return ExecuteHlsDashDownload(item, details, progress_cb, log_cb);
            }
        }
        return res;
    }

    // 2. HLS / DASH Segment Extractor (N_m3u8DL-RE)
    auto res = ExecuteHlsDashDownload(item, details, progress_cb, log_cb);
    if (!res.success && !aborted_.load()) {
        std::string err_lo = Utils::ToLower(res.error_reason);
        if (err_lo.find("input not supported") != std::string::npos ||
            err_lo.find("notsupportedexception") != std::string::npos ||
            err_lo.find("cannot find any streams") != std::string::npos) {
            if (log_cb) {
                log_cb("  [Auto-Fallback] Stream is not an M3U8/DASH playlist. Switching to Native Direct Downloader...");
            }
            return ExecuteDirectDownload(item, details, progress_cb, log_cb);
        }
    }
    return res;
}

Downloader::ExecutionResult Downloader::ExecuteHlsDashDownload(
    const DownloadItem& item,
    const StreamDetails& details,
    ProgressCallback progress_cb,
    LogCallback log_cb
) {
    std::string bin_path = FindBinary("N_m3u8DL-RE");
    std::string ffmpeg_path = FindBinary("ffmpeg");

    std::string safe_dir = item.save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item.save_dir;
    while (!safe_dir.empty() && (safe_dir.back() == '\\' || safe_dir.back() == '/')) {
        safe_dir.pop_back();
    }
    std::string safe_name = MetadataResolver::SanitizeInputTitle(item.title);
    safe_name = Utils::ReplaceAll(safe_name, "\"", "'");

    std::string url_lo = Utils::ToLower(details.url);
    bool is_audio_only_stream = (url_lo.find("/a/") != std::string::npos ||
                                 url_lo.find("/audio/") != std::string::npos ||
                                 item.resolution == "audio_only");

    std::wostringstream cmd;
    cmd << L"\"" << Utils::Utf8ToWide(bin_path) << L"\" ";
    cmd << L"\"" << Utils::Utf8ToWide(details.url) << L"\" ";
    cmd << L"--auto-select ";
    cmd << L"--save-dir \"" << Utils::Utf8ToWide(safe_dir) << L"\" ";
    cmd << L"--save-name \"" << Utils::Utf8ToWide(safe_name) << L"\" ";
    cmd << L"--ffmpeg-binary-path \"" << Utils::Utf8ToWide(ffmpeg_path) << L"\" ";
    cmd << L"-M format=mkv:muxer=ffmpeg ";
    if (details.url.find('?') == std::string::npos) {
        cmd << L"--append-url-params ";
    }
    cmd << L"--thread-count 16 ";
    cmd << L"--download-retry-count 6 ";
    cmd << L"--http-request-timeout 15 ";
    cmd << L"--disable-update-check ";
    cmd << L"--no-log ";
    cmd << L"--no-ansi-color ";
    cmd << L"-mt ";

    // Video stream selection
    if (is_audio_only_stream) {
        cmd << L"-sv none ";
    } else if (item.resolution == "720p") {
        cmd << L"-sv res=\"720*\":for=best ";
    } else if (item.resolution == "480p") {
        cmd << L"-sv res=\"480*\":for=best ";
    } else {
        cmd << L"-sv for=best ";
    }

    // Audio stream selection
    if (item.audio_choice == "en_hi") {
        cmd << L"-sa lang=eng,hin:for=all ";
    } else if (item.audio_choice == "eng") {
        cmd << L"-sa lang=eng:for=all ";
    } else if (item.audio_choice == "hin") {
        cmd << L"-sa lang=hin:for=all ";
    } else {
        cmd << L"-sa all ";
    }

    // Modern Chrome Headers to prevent 403 Forbidden
    cmd << L"-H \"User-Agent: " << Utils::Utf8ToWide(details.user_agent) << L"\" ";
    if (!details.referer.empty()) {
        cmd << L"-H \"Referer: " << Utils::Utf8ToWide(details.referer) << L"\" ";
    }
    if (!details.origin.empty()) {
        cmd << L"-H \"Origin: " << Utils::Utf8ToWide(details.origin) << L"\" ";
    }
    if (!details.cookie.empty()) {
        cmd << L"-H \"Cookie: " << Utils::Utf8ToWide(details.cookie) << L"\" ";
    }
    cmd << L"-H \"Accept: */*\" ";
    cmd << L"-H \"Accept-Language: en-US,en;q=0.9\" ";
    cmd << L"-H \"Sec-Fetch-Dest: empty\" ";
    cmd << L"-H \"Sec-Fetch-Mode: cors\" ";
    cmd << L"-H \"Sec-Fetch-Site: cross-site\" ";

    std::string speed = item.speed_limit;
    if (speed.empty()) {
        auto s = SettingsManager::GetInstance().GetSettings().speed_limit;
        if (s != "unlimited" && !s.empty()) {
            speed = s;
        }
    }
    if (!speed.empty() && speed != "0" && speed != "unlimited") {
        cmd << L"--max-speed \"" << Utils::Utf8ToWide(speed) << L"\" ";
    }

    if (item.include_subtitles) {
        cmd << L"--sub-format " << Utils::Utf8ToWide(item.sub_format) << L" ";
        cmd << L"--auto-subtitle-fix ";
        if (!item.sub_lang.empty() && item.sub_lang != "all") {
            cmd << L"-ss lang=" << Utils::Utf8ToWide(item.sub_lang) << L" ";
        } else {
            cmd << L"-ss all ";
        }
    }

    if (log_cb) {
        log_cb("[Downloader] Starting HLS/DASH download: " + item.title);
    }

    auto res = RunProcess(cmd.str(), item.id, progress_cb, log_cb);

    // Disk fallback: if final_file_path wasn't captured or doesn't exist, search save_dir
    if (res.success && (res.final_file_path.empty() || !std::filesystem::exists(res.final_file_path))) {
        std::filesystem::path sdir(item.save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item.save_dir);
        std::string sname = MetadataResolver::SanitizeInputTitle(item.title);
        std::vector<std::string> exts = { ".mkv", ".mp4", ".ts" };
        for (const auto& e : exts) {
            std::filesystem::path cand = sdir / (sname + e);
            if (std::filesystem::exists(cand)) {
                res.final_file_path = cand.string();
                break;
            }
        }
    }

    return res;
}

Downloader::ExecutionResult Downloader::ExecuteSubtitleDownload(
    const DownloadItem& item,
    ProgressCallback progress_cb,
    LogCallback log_cb
) {
    StreamDetails details = ParseStreamDetails(item);
    std::string bin_path = FindBinary("N_m3u8DL-RE");
    std::string ffmpeg_path = FindBinary("ffmpeg");

    std::string safe_dir = item.save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item.save_dir;
    while (!safe_dir.empty() && (safe_dir.back() == '\\' || safe_dir.back() == '/')) {
        safe_dir.pop_back();
    }
    std::string safe_name = MetadataResolver::SanitizeInputTitle(item.title);
    safe_name = Utils::ReplaceAll(safe_name, "\"", "'");

    std::wostringstream cmd;
    cmd << L"\"" << Utils::Utf8ToWide(bin_path) << L"\" ";
    cmd << L"\"" << Utils::Utf8ToWide(details.url) << L"\" ";
    cmd << L"--save-dir \"" << Utils::Utf8ToWide(safe_dir) << L"\" ";
    cmd << L"--save-name \"" << Utils::Utf8ToWide(safe_name) << L"\" ";
    cmd << L"--ffmpeg-binary-path \"" << Utils::Utf8ToWide(ffmpeg_path) << L"\" ";
    cmd << L"--sub-only ";
    cmd << L"--sub-format " << Utils::Utf8ToWide(item.sub_format) << L" ";
    cmd << L"--auto-subtitle-fix ";
    if (details.url.find('?') == std::string::npos) {
        cmd << L"--append-url-params ";
    }
    cmd << L"--thread-count 16 ";
    cmd << L"--download-retry-count 6 ";
    cmd << L"--http-request-timeout 15 ";
    cmd << L"--disable-update-check ";
    cmd << L"--no-log ";
    cmd << L"--no-ansi-color ";
    cmd << L"-H \"User-Agent: " << Utils::Utf8ToWide(details.user_agent) << L"\" ";
    if (!details.referer.empty()) {
        cmd << L"-H \"Referer: " << Utils::Utf8ToWide(details.referer) << L"\" ";
    }
    if (!details.origin.empty()) {
        cmd << L"-H \"Origin: " << Utils::Utf8ToWide(details.origin) << L"\" ";
    }
    if (!details.cookie.empty()) {
        cmd << L"-H \"Cookie: " << Utils::Utf8ToWide(details.cookie) << L"\" ";
    }
    cmd << L"-H \"Accept: */*\" ";
    cmd << L"-H \"Accept-Language: en-US,en;q=0.9\" ";
    cmd << L"-H \"Sec-Fetch-Dest: empty\" ";
    cmd << L"-H \"Sec-Fetch-Mode: cors\" ";
    cmd << L"-H \"Sec-Fetch-Site: cross-site\" ";

    if (!item.sub_lang.empty() && item.sub_lang != "all") {
        cmd << L"-ss lang=" << Utils::Utf8ToWide(item.sub_lang) << L" ";
    } else {
        cmd << L"-ss all ";
    }

    if (log_cb) {
        log_cb("[Downloader] Starting subtitle-only extraction: " + item.title);
    }

    auto res = RunProcess(cmd.str(), item.id, progress_cb, log_cb);

    // Disk fallback for subtitles
    if (res.success && (res.final_file_path.empty() || !std::filesystem::exists(res.final_file_path))) {
        std::filesystem::path sdir(item.save_dir.empty() ? SettingsManager::GetInstance().GetSettings().default_save_dir : item.save_dir);
        std::string sname = MetadataResolver::SanitizeInputTitle(item.title);
        std::vector<std::string> sub_exts = { ".srt", ".vtt" };
        for (const auto& e : sub_exts) {
            std::filesystem::path cand = sdir / (sname + e);
            if (std::filesystem::exists(cand)) {
                res.final_file_path = cand.string();
                break;
            }
        }
    }

    return res;
}

} // namespace OmniStream

