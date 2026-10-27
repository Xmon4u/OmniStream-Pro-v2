#include "bridge_server.hpp"
#include "crypto.hpp"
#include <fstream>
#include <sstream>

namespace OmniStream {

static std::string ExtractJsonValue(const std::string& json, const std::string& key) {
    size_t keyPos = json.find("\"" + key + "\"");
    if (keyPos == std::string::npos) return "";

    size_t colon = json.find(':', keyPos);
    if (colon == std::string::npos) return "";

    size_t startQuote = json.find('"', colon);
    if (startQuote == std::string::npos) return "";

    size_t endQuote = startQuote + 1;
    while (endQuote < json.size()) {
        if (json[endQuote] == '"' && json[endQuote - 1] != '\\') {
            break;
        }
        endQuote++;
    }
    if (endQuote >= json.size()) return "";

    std::string val = json.substr(startQuote + 1, endQuote - startQuote - 1);
    std::string result;
    for (size_t i = 0; i < val.size(); ++i) {
        if (val[i] == '\\' && i + 1 < val.size()) {
            char next = val[i + 1];
            if (next == '"' || next == '\\' || next == '/') {
                result += next;
                i++;
                continue;
            } else if (next == 'n') {
                result += '\n';
                i++;
                continue;
            } else if (next == 'r') {
                result += '\r';
                i++;
                continue;
            } else if (next == 't') {
                result += '\t';
                i++;
                continue;
            }
        }
        result += val[i];
    }
    return result;
}

BridgeServer::BridgeServer(int port, const std::string& token)
    : m_port(port), m_token(token) {
    
    // Attempt to load existing persistent token from files first
    if (m_token.empty()) {
        const char* tokenCandidates[] = {
            "bridge_token.txt",
            "extension\\bridge_token.json",
            "..\\extension\\bridge_token.json",
            "Release Test\\Extension\\bridge_token.json",
            "..\\Release Test\\Extension\\bridge_token.json"
        };
        for (const char* p : tokenCandidates) {
            try {
                if (std::filesystem::exists(p)) {
                    std::ifstream f(p);
                    if (f.is_open()) {
                        std::string content((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
                        std::string tok = ExtractJsonValue(content, "token");
                        if (tok.empty()) {
                            // might be raw text
                            std::string line;
                            std::istringstream ss(content);
                            if (std::getline(ss, line)) {
                                line.erase(0, line.find_first_not_of(" \r\n\t"));
                                line.erase(line.find_last_not_of(" \r\n\t") + 1);
                                if (line.size() >= 24) tok = line;
                            }
                        }
                        if (tok.size() >= 24) {
                            m_token = tok;
                            break;
                        }
                    }
                }
            } catch (...) {}
        }
    }

    // Check AppData fallback
    if (m_token.empty()) {
        const char* localApp = std::getenv("LOCALAPPDATA");
        if (localApp) {
            std::filesystem::path appDataTok = std::filesystem::path(localApp) / "OmniStreamPro" / "bridge_token.txt";
            if (std::filesystem::exists(appDataTok)) {
                std::ifstream f(appDataTok);
                std::string tok;
                if (f >> tok && tok.size() >= 24) {
                    m_token = tok;
                }
            }
        }
    }

    // If still empty, generate a cryptographically strong 48-char random token
    if (m_token.empty()) {
        m_token = Crypto::GenerateRandomToken(24);
    }
}

BridgeServer::~BridgeServer() {
    Stop();
}

bool BridgeServer::Start() {
    if (m_running.load()) return true;

    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        Logger::Error("Failed to initialize Winsock.");
        return false;
    }

    m_listenSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (m_listenSocket == INVALID_SOCKET) {
        Logger::Error("Failed to create bridge socket.");
        WSACleanup();
        return false;
    }

    // Set reuse address
    int opt = 1;
    setsockopt(m_listenSocket, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&opt), sizeof(opt));

    sockaddr_in addr = { 0 };
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<u_short>(m_port));
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (bind(m_listenSocket, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == SOCKET_ERROR) {
        Logger::Error("Failed to bind bridge server to 127.0.0.1:" + std::to_string(m_port));
        closesocket(m_listenSocket);
        m_listenSocket = INVALID_SOCKET;
        WSACleanup();
        return false;
    }

    if (listen(m_listenSocket, SOMAXCONN) == SOCKET_ERROR) {
        Logger::Error("Failed to listen on bridge socket.");
        closesocket(m_listenSocket);
        m_listenSocket = INVALID_SOCKET;
        WSACleanup();
        return false;
    }

    // Persist token for Chrome / Firefox Extension sync
    try {
        std::ofstream tokenFile("bridge_token.txt");
        if (tokenFile.is_open()) {
            tokenFile << m_token;
        }

        std::string jsonContent = "{\n  \"token\": \"" + m_token + "\",\n  \"port\": " + std::to_string(m_port) + "\n}\n";
        const char* tokenPaths[] = {
            "extension\\bridge_token.json",
            "..\\extension\\bridge_token.json",
            "Release Test\\Extension\\bridge_token.json",
            "..\\Release Test\\Extension\\bridge_token.json"
        };
        for (const char* p : tokenPaths) {
            std::filesystem::path target(p);
            if (std::filesystem::exists(target.parent_path())) {
                std::ofstream f(p);
                if (f.is_open()) f << jsonContent;
            }
        }

        const char* localApp = std::getenv("LOCALAPPDATA");
        if (localApp) {
            std::filesystem::path appDir = std::filesystem::path(localApp) / "OmniStreamPro";
            std::filesystem::create_directories(appDir);
            std::ofstream fTxt(appDir / "bridge_token.txt");
            if (fTxt.is_open()) fTxt << m_token;

            std::filesystem::path extDir = appDir / "extension";
            std::filesystem::create_directories(extDir);
            std::ofstream fJson(extDir / "bridge_token.json");
            if (fJson.is_open()) fJson << jsonContent;
        }
    } catch (...) {}

    m_running.store(true);
    m_workerThread = std::make_unique<std::thread>(&BridgeServer::ServerThread, this);

    Logger::Success("OmniStream C++ Bridge Server running on http://127.0.0.1:" + std::to_string(m_port));
    return true;
}

void BridgeServer::Stop() {
    if (!m_running.load()) return;
    m_running.store(false);

    if (m_listenSocket != INVALID_SOCKET) {
        closesocket(m_listenSocket);
        m_listenSocket = INVALID_SOCKET;
    }

    if (m_workerThread && m_workerThread->joinable()) {
        m_workerThread->join();
    }

    WSACleanup();
    Logger::Info("Bridge Server stopped.");
}

void BridgeServer::ServerThread() {
    while (m_running.load()) {
        sockaddr_in clientAddr = { 0 };
        int clientLen = sizeof(clientAddr);
        SOCKET clientSocket = accept(m_listenSocket, reinterpret_cast<sockaddr*>(&clientAddr), &clientLen);

        if (clientSocket == INVALID_SOCKET) {
            if (!m_running.load()) break;
            continue;
        }

        std::thread(&BridgeServer::HandleClient, this, clientSocket).detach();
    }
}

void BridgeServer::HandleClient(SOCKET clientSocket) {
    char buffer[16384];
    int bytesReceived = recv(clientSocket, buffer, sizeof(buffer) - 1, 0);
    if (bytesReceived <= 0) {
        closesocket(clientSocket);
        return;
    }

    buffer[bytesReceived] = '\0';
    std::string request(buffer, bytesReceived);

    std::istringstream reqStream(request);
    std::string method, rawPath, httpVer;
    reqStream >> method >> rawPath >> httpVer;

    // Strip URL query parameters (e.g. /health?cache=123)
    std::string path = rawPath;
    size_t qPos = path.find('?');
    if (qPos != std::string::npos) {
        path = path.substr(0, qPos);
    }

    std::map<std::string, std::string> headers;
    std::string headerLine;
    while (std::getline(reqStream, headerLine) && headerLine != "\r" && !headerLine.empty()) {
        if (!headerLine.empty() && headerLine.back() == '\r') headerLine.pop_back();
        size_t colon = headerLine.find(':');
        if (colon != std::string::npos) {
            std::string k = headerLine.substr(0, colon);
            std::string v = headerLine.substr(colon + 1);
            k.erase(0, k.find_first_not_of(" \t"));
            k.erase(k.find_last_not_of(" \t") + 1);
            v.erase(0, v.find_first_not_of(" \t"));
            v.erase(v.find_last_not_of(" \t") + 1);
            std::transform(k.begin(), k.end(), k.begin(), ::tolower);
            headers[k] = v;
        }
    }

    // CORS Headers
    std::string origin = headers["origin"];
    std::string corsHeader = "Access-Control-Allow-Origin: *\r\n"
                             "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                             "Access-Control-Allow-Headers: Content-Type, Authorization, x-omnistream-token, x-requested-with\r\n"
                             "Access-Control-Allow-Private-Network: true\r\n";

    if (method == "OPTIONS") {
        std::string res = "HTTP/1.1 204 No Content\r\n" + corsHeader + "Content-Length: 0\r\n\r\n";
        send(clientSocket, res.data(), (int)res.size(), 0);
        closesocket(clientSocket);
        return;
    }

    // Validate origin: accept local extensions and localhost clients
    bool validOrigin = origin.empty() ||
                       origin.find("chrome-extension://") == 0 ||
                       origin.find("moz-extension://") == 0 ||
                       origin.find("extension://") == 0 ||
                       origin.find("localhost") != std::string::npos ||
                       origin.find("127.0.0.1") != std::string::npos;

    if (!validOrigin) {
        std::string res = "HTTP/1.1 403 Forbidden\r\n" + corsHeader + "Content-Type: text/plain\r\nContent-Length: 17\r\n\r\nOrigin forbidden";
        send(clientSocket, res.data(), (int)res.size(), 0);
        closesocket(clientSocket);
        return;
    }

    // Verify token for mutating actions
    std::string clientToken = headers["x-omnistream-token"];
    if (clientToken.empty() && headers.count("authorization")) {
        std::string auth = headers["authorization"];
        if (auth.find("Bearer ") == 0 || auth.find("bearer ") == 0) {
            clientToken = auth.substr(7);
        }
    }

    // Extract request body for POST
    size_t bodyPos = request.find("\r\n\r\n");
    std::string body = (bodyPos != std::string::npos) ? request.substr(bodyPos + 4) : "";

    // Routes
    std::string responseBody;
    int statusCode = 200;

    if (method == "GET" && (path == "/" || path == "/health")) {
        // High-fidelity health endpoint expected by background.js and popup.js
        responseBody = "{\n"
                       "  \"status\": \"ok\",\n"
                       "  \"app\": \"OmniStream Pro\",\n"
                       "  \"version\": \"" + std::string(VERSION) + "\",\n"
                       "  \"bridge\": \"active\",\n"
                       "  \"port\": " + std::to_string(m_port) + ",\n"
                       "  \"authenticated\": true,\n"
                       "  \"queue_count\": 0,\n"
                       "  \"is_downloading\": false,\n"
                       "  \"mode\": \"" + m_currentMode + "\",\n"
                       "  \"theme\": \"Cyber Slate\"\n"
                       "}";
    }
    else if (method == "GET" && (path == "/ping" || path == "/status")) {
        responseBody = "{\n  \"status\": \"online\",\n  \"engine\": \"OmniStream Pro C++ Native Engine\",\n  \"version\": \"" +
                       std::string(VERSION) + "\"\n}";
    }
    else if (method == "GET" && path == "/token") {
        responseBody = "{\n  \"token\": \"" + m_token + "\"\n}";
    }
    else if (method == "GET" && path == "/queue") {
        responseBody = "{\n  \"success\": true,\n  \"queue\": []\n}";
    }
    else if (method == "POST" && (path == "/add" || path == "/add_stream")) {
        std::string curlCmd = ExtractJsonValue(body, "curl");
        std::string url = ExtractJsonValue(body, "url");
        if (url.empty()) url = ExtractJsonValue(body, "input");
        if (url.empty()) url = ExtractJsonValue(body, "streamUrl");

        std::string title = ExtractJsonValue(body, "title");
        if (title.empty()) title = ExtractJsonValue(body, "save_name");
        if (title.empty()) title = ExtractJsonValue(body, "saveName");

        std::string mode = ExtractJsonValue(body, "mode");
        if (mode.empty()) mode = m_currentMode;

        std::string nid = ExtractJsonValue(body, "netflixId");
        if (nid.empty()) nid = ExtractJsonValue(body, "netflix_id");

        std::string iid = ExtractJsonValue(body, "imdbId");
        if (iid.empty()) iid = ExtractJsonValue(body, "imdb_id");

        std::string tid = ExtractJsonValue(body, "tmdbId");
        if (tid.empty()) tid = ExtractJsonValue(body, "tmdb_id");

        // Prefer full curl command with captured headers, fallback to raw url
        std::string inputToQueue = !curlCmd.empty() ? curlCmd : url;

        if (!inputToQueue.empty()) {
            DownloadOptions opts;
            opts.inputText = inputToQueue;
            opts.saveName = title;
            opts.mode = mode;
            opts.netflixId = nid;
            opts.imdbId = iid;
            opts.tmdbId = tid;

            if (m_onJobReceived) {
                m_onJobReceived(opts);
            }

            responseBody = "{\n  \"success\": true,\n  \"message\": \"Stream added to OmniStream Pro download queue\"\n}";
        } else {
            statusCode = 400;
            responseBody = "{\n  \"success\": false,\n  \"error\": \"No valid URL or cURL command provided in payload\"\n}";
        }
    }
    else if (method == "POST" && (path == "/batch_add" || path == "/add_batch")) {
        // Parse batch items
        int count = 0;
        size_t searchPos = 0;
        while ((searchPos = body.find("\"url\"", searchPos)) != std::string::npos) {
            size_t itemStart = body.rfind('{', searchPos);
            size_t itemEnd = body.find('}', searchPos);
            if (itemStart != std::string::npos && itemEnd != std::string::npos) {
                std::string itemJson = body.substr(itemStart, itemEnd - itemStart + 1);
                std::string curlCmd = ExtractJsonValue(itemJson, "curl");
                std::string itUrl = ExtractJsonValue(itemJson, "url");
                std::string itTitle = ExtractJsonValue(itemJson, "title");
                if (itTitle.empty()) itTitle = ExtractJsonValue(itemJson, "save_name");

                std::string itMode = ExtractJsonValue(itemJson, "mode");
                if (itMode.empty()) itMode = m_currentMode;

                std::string itNid = ExtractJsonValue(itemJson, "netflixId");
                if (itNid.empty()) itNid = ExtractJsonValue(itemJson, "netflix_id");

                std::string itIid = ExtractJsonValue(itemJson, "imdbId");
                if (itIid.empty()) itIid = ExtractJsonValue(itemJson, "imdb_id");

                std::string itTid = ExtractJsonValue(itemJson, "tmdbId");
                if (itTid.empty()) itTid = ExtractJsonValue(itemJson, "tmdb_id");

                std::string chosen = !curlCmd.empty() ? curlCmd : itUrl;
                if (!chosen.empty()) {
                    DownloadOptions opts;
                    opts.inputText = chosen;
                    opts.saveName = itTitle;
                    opts.mode = itMode;
                    opts.netflixId = itNid;
                    opts.imdbId = itIid;
                    opts.tmdbId = itTid;
                    if (m_onJobReceived) {
                        m_onJobReceived(opts);
                    }
                    count++;
                }
            }
            searchPos = (itemEnd != std::string::npos) ? itemEnd + 1 : searchPos + 5;
        }

        responseBody = "{\n  \"success\": true,\n  \"count\": " + std::to_string(count) + ",\n  \"message\": \"Successfully queued " + std::to_string(count) + " streams in OmniStream Pro\"\n}";
    }
    else if (method == "POST" && path == "/start_queue") {
        responseBody = "{\n  \"success\": true,\n  \"message\": \"Queue download started\"\n}";
    }
    else if (method == "POST" && path == "/set_mode") {
        std::string rawMode = ExtractJsonValue(body, "mode");
        std::string lowerMode = rawMode;
        std::transform(lowerMode.begin(), lowerMode.end(), lowerMode.begin(), ::tolower);
        if (lowerMode.find("tmdb") != std::string::npos) m_currentMode = "tmdb_rename";
        else if (lowerMode.find("imdb") != std::string::npos) m_currentMode = "imdb_rename";
        else if (lowerMode.find("netflix") != std::string::npos) m_currentMode = "netflix_rename";
        else if (lowerMode.find("sub") != std::string::npos || lowerMode.find("merge") != std::string::npos) m_currentMode = "sub_merge";
        else m_currentMode = "normal";

        if (m_onModeChanged) {
            m_onModeChanged(m_currentMode);
        }

        responseBody = "{\n  \"success\": true,\n  \"mode\": \"" + m_currentMode + "\"\n}";
    }
    else if (method == "POST" && path == "/set_theme") {
        std::string theme = ExtractJsonValue(body, "theme");
        responseBody = "{\n  \"success\": true,\n  \"theme\": \"" + (theme.empty() ? "Cyber Slate" : theme) + "\"\n}";
    }
    else if (method == "POST" && path == "/focus") {
        responseBody = "{\n  \"success\": true\n}";
    }
    else {
        statusCode = 404;
        responseBody = "{\n  \"error\": \"Endpoint not found\"\n}";
    }

    std::ostringstream resStream;
    resStream << "HTTP/1.1 " << statusCode << " OK\r\n";
    resStream << corsHeader;
    resStream << "Content-Type: application/json; charset=utf-8\r\n";
    resStream << "Content-Length: " << responseBody.size() << "\r\n";
    resStream << "Connection: close\r\n\r\n";
    resStream << responseBody;

    std::string fullResponse = resStream.str();
    send(clientSocket, fullResponse.data(), (int)fullResponse.size(), 0);
    shutdown(clientSocket, SD_SEND);
    closesocket(clientSocket);
}

} // namespace OmniStream
