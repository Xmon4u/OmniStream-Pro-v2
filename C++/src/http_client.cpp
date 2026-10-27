#include "http_client.hpp"
#include <fstream>

namespace OmniStream {

HttpClient::HttpClient(const std::string& userAgent)
    : m_userAgent(userAgent.empty() ? DEFAULT_USER_AGENT : userAgent) {
    std::wstring wUa = Utf8ToWide(m_userAgent);
    m_hSession = WinHttpOpen(
        wUa.c_str(),
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0
    );

    if (m_hSession) {
        // Enable TLS 1.2 and TLS 1.3
        DWORD protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;
#ifdef WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3
        protocols |= WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_3;
#endif
        WinHttpSetOption(m_hSession, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols));

        // Set timeouts (resolve: 10s, connect: 15s, send: 30s, receive: 30s)
        WinHttpSetTimeouts(m_hSession, 10000, 15000, 30000, 30000);
    }
}

HttpClient::~HttpClient() {
    if (m_hSession) {
        WinHttpCloseHandle(m_hSession);
        m_hSession = nullptr;
    }
}

HttpResponse HttpClient::Get(
    const std::string& url,
    const std::map<std::string, std::string>& headers,
    std::function<void(uint64_t downloaded, uint64_t total)> progress
) {
    HttpResponse response;
    if (!m_hSession || url.empty()) return response;

    std::wstring wUrl = Utf8ToWide(url);
    URL_COMPONENTS urlComp = { 0 };
    urlComp.dwStructSize = sizeof(urlComp);
    urlComp.dwHostNameLength  = (DWORD)-1;
    urlComp.dwUrlPathLength   = (DWORD)-1;
    urlComp.dwExtraInfoLength = (DWORD)-1;

    if (!WinHttpCrackUrl(wUrl.c_str(), (DWORD)wUrl.length(), 0, &urlComp)) {
        return response;
    }

    std::wstring host(urlComp.lpszHostName, urlComp.dwHostNameLength);
    std::wstring path = (urlComp.dwUrlPathLength > 0)
        ? std::wstring(urlComp.lpszUrlPath, urlComp.dwUrlPathLength + urlComp.dwExtraInfoLength)
        : L"/";

    bool isHttps = (urlComp.nScheme == INTERNET_SCHEME_HTTPS);
    INTERNET_PORT port = urlComp.nPort;

    HINTERNET hConnect = WinHttpConnect(m_hSession, host.c_str(), port, 0);
    if (!hConnect) return response;

    DWORD openFlags = isHttps ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"GET",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        openFlags
    );

    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        return response;
    }

    // Build header string
    std::wstring customHeaders;
    for (const auto& [k, v] : headers) {
        customHeaders += Utf8ToWide(k) + L": " + Utf8ToWide(v) + L"\r\n";
    }

    if (!customHeaders.empty()) {
        WinHttpAddRequestHeaders(
            hRequest,
            customHeaders.c_str(),
            (DWORD)customHeaders.length(),
            WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE
        );
    }

    // Automatic redirect following
    DWORD redirectPolicy = WINHTTP_OPTION_REDIRECT_POLICY_ALWAYS;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_REDIRECT_POLICY, &redirectPolicy, sizeof(redirectPolicy));

    BOOL bResults = WinHttpSendRequest(
        hRequest,
        WINHTTP_NO_ADDITIONAL_HEADERS,
        0,
        WINHTTP_NO_REQUEST_DATA,
        0,
        0,
        0
    );

    if (bResults) {
        bResults = WinHttpReceiveResponse(hRequest, nullptr);
    }

    if (bResults) {
        // Status code
        DWORD statusCode = 0;
        DWORD size = sizeof(statusCode);
        WinHttpQueryHeaders(
            hRequest,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX,
            &statusCode,
            &size,
            WINHTTP_NO_HEADER_INDEX
        );
        response.statusCode = (int)statusCode;

        // Content Length
        uint64_t contentLength = 0;
        wchar_t lenBuffer[64] = { 0 };
        DWORD lenBufferSize = sizeof(lenBuffer);
        if (WinHttpQueryHeaders(
            hRequest,
            WINHTTP_QUERY_CONTENT_LENGTH,
            WINHTTP_HEADER_NAME_BY_INDEX,
            lenBuffer,
            &lenBufferSize,
            WINHTTP_NO_HEADER_INDEX
        )) {
            contentLength = _wtoi64(lenBuffer);
        }

        // Read data in 64KB blocks
        DWORD bytesAvailable = 0;
        uint64_t totalDownloaded = 0;
        std::vector<uint8_t> buffer(65536);

        while (WinHttpQueryDataAvailable(hRequest, &bytesAvailable) && bytesAvailable > 0) {
            DWORD bytesRead = 0;
            DWORD toRead = std::min(bytesAvailable, (DWORD)buffer.size());
            if (WinHttpReadData(hRequest, buffer.data(), toRead, &bytesRead) && bytesRead > 0) {
                response.body.insert(response.body.end(), buffer.begin(), buffer.begin() + bytesRead);
                totalDownloaded += bytesRead;
                if (progress) {
                    progress(totalDownloaded, contentLength);
                }
            } else {
                break;
            }
        }
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    return response;
}

HttpResponse HttpClient::Post(
    const std::string& url,
    const std::string& data,
    const std::string& contentType,
    const std::map<std::string, std::string>& headers
) {
    HttpResponse response;
    if (!m_hSession || url.empty()) return response;

    std::wstring wUrl = Utf8ToWide(url);
    URL_COMPONENTS urlComp = { 0 };
    urlComp.dwStructSize = sizeof(urlComp);
    urlComp.dwHostNameLength  = (DWORD)-1;
    urlComp.dwUrlPathLength   = (DWORD)-1;
    urlComp.dwExtraInfoLength = (DWORD)-1;

    if (!WinHttpCrackUrl(wUrl.c_str(), (DWORD)wUrl.length(), 0, &urlComp)) {
        return response;
    }

    std::wstring host(urlComp.lpszHostName, urlComp.dwHostNameLength);
    std::wstring path = (urlComp.dwUrlPathLength > 0)
        ? std::wstring(urlComp.lpszUrlPath, urlComp.dwUrlPathLength + urlComp.dwExtraInfoLength)
        : L"/";

    bool isHttps = (urlComp.nScheme == INTERNET_SCHEME_HTTPS);
    INTERNET_PORT port = urlComp.nPort;

    HINTERNET hConnect = WinHttpConnect(m_hSession, host.c_str(), port, 0);
    if (!hConnect) return response;

    DWORD openFlags = isHttps ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"POST",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        openFlags
    );

    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        return response;
    }

    std::wstring customHeaders = L"Content-Type: " + Utf8ToWide(contentType) + L"\r\n";
    for (const auto& [k, v] : headers) {
        customHeaders += Utf8ToWide(k) + L": " + Utf8ToWide(v) + L"\r\n";
    }

    WinHttpAddRequestHeaders(
        hRequest,
        customHeaders.c_str(),
        (DWORD)customHeaders.length(),
        WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE
    );

    DWORD redirectPolicy = WINHTTP_OPTION_REDIRECT_POLICY_ALWAYS;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_REDIRECT_POLICY, &redirectPolicy, sizeof(redirectPolicy));

    BOOL bResults = WinHttpSendRequest(
        hRequest,
        WINHTTP_NO_ADDITIONAL_HEADERS,
        0,
        (LPVOID)data.data(),
        (DWORD)data.size(),
        (DWORD)data.size(),
        0
    );

    if (bResults) {
        bResults = WinHttpReceiveResponse(hRequest, nullptr);
    }

    if (bResults) {
        DWORD statusCode = 0;
        DWORD size = sizeof(statusCode);
        WinHttpQueryHeaders(
            hRequest,
            WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX,
            &statusCode,
            &size,
            WINHTTP_NO_HEADER_INDEX
        );
        response.statusCode = static_cast<int>(statusCode);

        DWORD bytesAvailable = 0;
        std::vector<uint8_t> buffer(65536);
        while (WinHttpQueryDataAvailable(hRequest, &bytesAvailable) && bytesAvailable > 0) {
            DWORD bytesRead = 0;
            DWORD toRead = std::min(bytesAvailable, (DWORD)buffer.size());
            if (WinHttpReadData(hRequest, buffer.data(), toRead, &bytesRead) && bytesRead > 0) {
                response.body.insert(response.body.end(), buffer.begin(), buffer.begin() + bytesRead);
            } else {
                break;
            }
        }
    }

    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    return response;
}

bool HttpClient::DownloadFile(
    const std::string& url,
    const std::string& destFilePath,
    const std::map<std::string, std::string>& headers,
    std::function<void(uint64_t downloaded, uint64_t total)> progress
) {
    if (!m_hSession || url.empty()) return false;

    std::wstring wUrl = Utf8ToWide(url);
    URL_COMPONENTS urlComp = { 0 };
    urlComp.dwStructSize = sizeof(urlComp);
    urlComp.dwHostNameLength  = (DWORD)-1;
    urlComp.dwUrlPathLength   = (DWORD)-1;
    urlComp.dwExtraInfoLength = (DWORD)-1;

    if (!WinHttpCrackUrl(wUrl.c_str(), (DWORD)wUrl.length(), 0, &urlComp)) {
        return false;
    }

    std::wstring host(urlComp.lpszHostName, urlComp.dwHostNameLength);
    std::wstring path = (urlComp.dwUrlPathLength > 0)
        ? std::wstring(urlComp.lpszUrlPath, urlComp.dwUrlPathLength + urlComp.dwExtraInfoLength)
        : L"/";

    bool isHttps = (urlComp.nScheme == INTERNET_SCHEME_HTTPS);
    INTERNET_PORT port = urlComp.nPort;

    HINTERNET hConnect = WinHttpConnect(m_hSession, host.c_str(), port, 0);
    if (!hConnect) return false;

    DWORD openFlags = isHttps ? WINHTTP_FLAG_SECURE : 0;
    HINTERNET hRequest = WinHttpOpenRequest(
        hConnect,
        L"GET",
        path.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        openFlags
    );

    if (!hRequest) {
        WinHttpCloseHandle(hConnect);
        return false;
    }

    std::wstring customHeaders;
    for (const auto& [k, v] : headers) {
        customHeaders += Utf8ToWide(k) + L": " + Utf8ToWide(v) + L"\r\n";
    }

    if (!customHeaders.empty()) {
        WinHttpAddRequestHeaders(
            hRequest,
            customHeaders.c_str(),
            (DWORD)customHeaders.length(),
            WINHTTP_ADDREQ_FLAG_ADD | WINHTTP_ADDREQ_FLAG_REPLACE
        );
    }

    DWORD redirectPolicy = WINHTTP_OPTION_REDIRECT_POLICY_ALWAYS;
    WinHttpSetOption(hRequest, WINHTTP_OPTION_REDIRECT_POLICY, &redirectPolicy, sizeof(redirectPolicy));

    BOOL bResults = WinHttpSendRequest(
        hRequest,
        WINHTTP_NO_ADDITIONAL_HEADERS,
        0,
        WINHTTP_NO_REQUEST_DATA,
        0,
        0,
        0
    );

    if (bResults) {
        bResults = WinHttpReceiveResponse(hRequest, nullptr);
    }

    if (!bResults) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        return false;
    }

    DWORD statusCode = 0;
    DWORD size = sizeof(statusCode);
    WinHttpQueryHeaders(
        hRequest,
        WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
        WINHTTP_HEADER_NAME_BY_INDEX,
        &statusCode,
        &size,
        WINHTTP_NO_HEADER_INDEX
    );

    if (statusCode < 200 || statusCode >= 300) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        return false;
    }

    uint64_t contentLength = 0;
    wchar_t lenBuffer[64] = { 0 };
    DWORD lenBufferSize = sizeof(lenBuffer);
    if (WinHttpQueryHeaders(
        hRequest,
        WINHTTP_QUERY_CONTENT_LENGTH,
        WINHTTP_HEADER_NAME_BY_INDEX,
        lenBuffer,
        &lenBufferSize,
        WINHTTP_NO_HEADER_INDEX
    )) {
        contentLength = _wtoi64(lenBuffer);
    }

    std::filesystem::path p(destFilePath);
    if (p.has_parent_path()) {
        std::filesystem::create_directories(p.parent_path());
    }

    std::ofstream out(destFilePath, std::ios::binary);
    if (!out.is_open()) {
        WinHttpCloseHandle(hRequest);
        WinHttpCloseHandle(hConnect);
        return false;
    }

    DWORD bytesAvailable = 0;
    uint64_t totalDownloaded = 0;
    std::vector<uint8_t> buffer(65536);

    while (WinHttpQueryDataAvailable(hRequest, &bytesAvailable) && bytesAvailable > 0) {
        DWORD bytesRead = 0;
        DWORD toRead = std::min(bytesAvailable, (DWORD)buffer.size());
        if (WinHttpReadData(hRequest, buffer.data(), toRead, &bytesRead) && bytesRead > 0) {
            out.write(reinterpret_cast<const char*>(buffer.data()), bytesRead);
            totalDownloaded += bytesRead;
            if (progress) {
                progress(totalDownloaded, contentLength);
            }
        } else {
            break;
        }
    }

    out.close();
    WinHttpCloseHandle(hRequest);
    WinHttpCloseHandle(hConnect);
    return totalDownloaded > 0;
}

} // namespace OmniStream
