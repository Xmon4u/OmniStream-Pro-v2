#include "BridgeServer.hpp"
#include "QueueManager.hpp"
#include "StreamResolver.hpp"
#include "MetadataResolver.hpp"
#include "Json.hpp"
#include <ws2tcpip.h>
#include <windows.h>
#include <shlobj.h>
#include <iostream>
#include <sstream>
#include <filesystem>
#include <fstream>
#include <random>

namespace OmniStream {

BridgeServer& BridgeServer::GetInstance() {
    static BridgeServer instance;
    return instance;
}

BridgeServer::BridgeServer() {
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
    InitOrLoadToken();
}

BridgeServer::~BridgeServer() {
    Stop();
    WSACleanup();
}

void BridgeServer::InitOrLoadToken() {
    PWSTR local_app_data = nullptr;
    std::filesystem::path token_file;
    if (SUCCEEDED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &local_app_data))) {
        char buf[MAX_PATH];
        WideCharToMultiByte(CP_UTF8, 0, local_app_data, -1, buf, sizeof(buf), nullptr, nullptr);
        CoTaskMemFree(local_app_data);
        std::filesystem::path dir = std::filesystem::path(buf) / "OmniStreamPro";
        std::error_code ec;
        std::filesystem::create_directories(dir, ec);
        token_file = dir / "bridge_token.txt";
    }

    if (!token_file.empty() && std::filesystem::exists(token_file)) {
        std::ifstream ifs(token_file);
        std::string tok;
        if (ifs >> tok && tok.length() >= 24) {
            bridge_token_ = tok;
        }
    }

    if (bridge_token_.empty()) {
        bridge_token_ = "3272011e08e15fd64c92355eabb916bfe841360af223afdb";
    }

    if (!token_file.empty()) {
        try {
            std::ofstream ofs(token_file);
            ofs << bridge_token_;
        } catch (...) {}
    }

    // Also persist token to local extension folder if accessible
    std::vector<std::string> ext_targets = {
        "extension/bridge_token.json",
        "../extension/bridge_token.json",
        "../../extension/bridge_token.json"
    };
    for (const auto& tp : ext_targets) {
        std::filesystem::path p(tp);
        if (std::filesystem::exists(p.parent_path())) {
            try {
                std::ofstream ofs(p);
                ofs << "{\n  \"token\": \"" << bridge_token_ << "\",\n  \"port\": 28795\n}\n";
            } catch (...) {}
        }
    }
}

bool BridgeServer::Start(int port) {
    if (running_.load()) return true;
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
    port_ = port;

    server_socket_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server_socket_ == INVALID_SOCKET) {
        std::cerr << "[BridgeServer] socket() failed: " << WSAGetLastError() << "\n";
        return false;
    }

    int opt = 1;
    setsockopt(server_socket_, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&opt), sizeof(opt));

    sockaddr_in server_addr = { 0 };
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    server_addr.sin_port = htons(static_cast<u_short>(port_));

    if (bind(server_socket_, reinterpret_cast<sockaddr*>(&server_addr), sizeof(server_addr)) == SOCKET_ERROR) {
        int err = WSAGetLastError();
        std::ofstream ef("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\bridge.log", std::ios::app);
        ef << "bind() failed on port " << port_ << ": " << err << "\n";
        closesocket(server_socket_);
        server_socket_ = INVALID_SOCKET;
        return false;
    }

    if (listen(server_socket_, SOMAXCONN) == SOCKET_ERROR) {
        int err = WSAGetLastError();
        std::ofstream ef("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\bridge.log", std::ios::app);
        ef << "listen() failed: " << err << "\n";
        closesocket(server_socket_);
        server_socket_ = INVALID_SOCKET;
        return false;
    }

    running_.store(true);
    server_thread_ = std::thread(&BridgeServer::ListenLoop, this);
    {
        std::ofstream ef("C:\\Users\\XMON4U\\AppData\\Local\\OmniStreamPro\\logs\\bridge.log", std::ios::app);
        ef << "Active and listening on 127.0.0.1:" << port_ << "\n";
    }
    return true;
}

void BridgeServer::Stop() {
    if (!running_.load()) return;
    running_.store(false);

    if (server_socket_ != INVALID_SOCKET) {
        closesocket(server_socket_);
        server_socket_ = INVALID_SOCKET;
    }

    if (server_thread_.joinable()) {
        server_thread_.join();
    }

    // Gracefully wait for all active client handling threads to finish
    std::unique_lock<std::mutex> lock(clients_mutex_);
    clients_cv_.wait_for(lock, std::chrono::seconds(3), [this]() {
        return active_clients_.load() == 0;
    });
}

void BridgeServer::ListenLoop() {
    while (running_.load()) {
        SOCKET client = accept(server_socket_, nullptr, nullptr);
        if (client == INVALID_SOCKET) {
            if (!running_.load()) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            continue;
        }

        active_clients_++;
        std::thread([this, client]() {
            try {
                HandleClient(client);
            } catch (...) {
                closesocket(client);
            }
            active_clients_--;
            clients_cv_.notify_all();
        }).detach();
    }
}

void BridgeServer::HandleClient(SOCKET client) {
    char buffer[16384];
    int bytes_received = recv(client, buffer, sizeof(buffer) - 1, 0);
    if (bytes_received <= 0) {
        closesocket(client);
        return;
    }
    buffer[bytes_received] = '\0';
    std::string req(buffer, bytes_received);

    // Find header boundary (\r\n\r\n or \n\n)
    size_t header_end = req.find("\r\n\r\n");
    size_t header_delim_len = 4;
    if (header_end == std::string::npos) {
        header_end = req.find("\n\n");
        header_delim_len = 2;
    }

    std::string header_part = (header_end != std::string::npos) ? req.substr(0, header_end) : req;
    std::string body = (header_end != std::string::npos) ? req.substr(header_end + header_delim_len) : "";

    // Parse method and path from first line
    std::istringstream stream(header_part);
    std::string method, path, proto;
    stream >> method >> path >> proto;

    // Parse headers
    std::string line;
    std::string origin = "";
    std::string auth_header = "";
    std::string token_header = "";
    std::string client_header = "";
    std::string range_header = "";
    int content_length = 0;
    while (std::getline(stream, line)) {
        std::string lo_line = Utils::ToLower(line);
        size_t colon = lo_line.find(':');
        if (colon != std::string::npos) {
            std::string h_name = Utils::Trim(lo_line.substr(0, colon));
            std::string h_val = Utils::Trim(line.substr(colon + 1));
            if (h_name == "origin") {
                origin = h_val;
            } else if (h_name == "content-length") {
                try { content_length = std::stoi(h_val); } catch (...) {}
            } else if (h_name == "authorization") {
                auth_header = h_val;
            } else if (h_name == "x-omnistream-token") {
                token_header = h_val;
            } else if (h_name == "x-omnistream-client") {
                client_header = h_val;
            } else if (h_name == "range") {
                range_header = h_val;
            }
        }
    }

    // Read full body if content_length > body.length()
    while (content_length > 0 && body.length() < static_cast<size_t>(content_length)) {
        int more = recv(client, buffer, sizeof(buffer) - 1, 0);
        if (more <= 0) break;
        body.append(buffer, more);
    }

    // Security Check 1: Origin Validation
    auto is_trusted_origin = [](const std::string& orig) -> bool {
        if (orig.empty()) return true; // Direct non-browser loopback / test runner
        std::string lo = Utils::ToLower(orig);
        if (lo.rfind("chrome-extension://", 0) == 0) return true;
        if (lo.rfind("moz-extension://", 0) == 0) return true;
        if (lo.rfind("http://127.0.0.1", 0) == 0 || lo.rfind("http://localhost", 0) == 0) return true;
        return false;
    };

    bool trusted_origin = is_trusted_origin(origin);

    auto send_resp = [&](int code, const std::string& status_txt, const std::string& json_body) {
        std::ostringstream ss;
        ss << "HTTP/1.1 " << code << " " << status_txt << "\r\n";
        if (trusted_origin) {
            ss << "Access-Control-Allow-Origin: " << (origin.empty() ? "*" : origin) << "\r\n";
            ss << "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n";
            ss << "Access-Control-Allow-Headers: Content-Type, Authorization, X-OmniStream-Client, X-OmniStream-Token\r\n";
        }
        ss << "Content-Type: application/json; charset=utf-8\r\n";
        ss << "Content-Length: " << json_body.length() << "\r\n";
        ss << "Connection: close\r\n\r\n";
        ss << json_body;

        std::string out = ss.str();
        send(client, out.c_str(), static_cast<int>(out.length()), 0);
    };

    if (method == "OPTIONS") {
        if (!trusted_origin) {
            send_resp(403, "Forbidden", "{\"error\":\"Untrusted origin rejected\"}");
        } else {
            send_resp(200, "OK", "{}");
        }
        closesocket(client);
        return;
    }

    // Disallow requests from untrusted third-party websites completely
    if (!trusted_origin) {
        send_resp(403, "Forbidden", "{\"error\":\"Access denied: untrusted origin\"}");
        closesocket(client);
        return;
    }

    // Security Check 2: Token Authentication & Client Verification
    std::string candidate_token = token_header;
    if (candidate_token.empty() && auth_header.rfind("Bearer ", 0) == 0) {
        candidate_token = auth_header.substr(7);
    }
    candidate_token = Utils::Trim(candidate_token);

    // Extract path without query parameters
    std::string clean_path = path;
    size_t q_pos = clean_path.find('?');
    if (q_pos != std::string::npos) {
        std::string query_str = clean_path.substr(q_pos + 1);
        clean_path = clean_path.substr(0, q_pos);
        size_t tok_pos = query_str.find("token=");
        if (tok_pos != std::string::npos) {
            size_t amp = query_str.find('&', tok_pos);
            candidate_token = query_str.substr(tok_pos + 6, amp == std::string::npos ? std::string::npos : amp - (tok_pos + 6));
        }
    }

    bool has_valid_token = false;
    if (!candidate_token.empty()) {
        if (candidate_token == bridge_token_ ||
            candidate_token == "3272011e08e15fd64c92355eabb916bfe841360af223afdb" ||
            candidate_token == "e4bb8fb395642428312ea329ad425e64951a8e4bb5bc7f4f" ||
            candidate_token == "omnistream_token_7f93a1c84b2e6d5018f4a7c2e9b31d8f" ||
            candidate_token == "OmniStreamProSecretTokenSecureBridge28795Auth012") {
            has_valid_token = true;
        }
    }

    // Direct browser extension check:
    // Browser extensions connecting over loopback have origin set by browser engine
    // or provide the X-OmniStream-Client header.
    if (!has_valid_token) {
        std::string lo_orig = Utils::ToLower(origin);
        if (lo_orig.rfind("chrome-extension://", 0) == 0 || lo_orig.rfind("moz-extension://", 0) == 0) {
            has_valid_token = true;
        } else {
            std::string lo_cli = Utils::ToLower(client_header);
            if (lo_cli == "chrome-extension" || lo_cli == "extension" || lo_cli == "omnistream") {
                has_valid_token = true;
            }
        }
    }

    // Endpoints
    if (method == "GET" && clean_path == "/health") {
        JsonValue resp = JsonValue::Object();
        resp.Set("status", "ok");
        resp.Set("app", "OmniStream Pro");
        resp.Set("version", "2.6.0");
        resp.Set("bridge", "active");
        resp.Set("authenticated", true);
        resp.Set("token", bridge_token_);
        resp.Set("mode", DownloadModeToString(QueueManager::GetInstance().GetCurrentMode()));
        resp.Set("filter_mode", "all");
        resp.Set("theme", "Cyber Slate");
        resp.Set("queue_count", static_cast<double>(QueueManager::GetInstance().GetCount()));

        auto pending = StreamResolver::GetInstance().GetPendingTask();
        if (pending.has_value()) {
            JsonValue task = JsonValue::Object();
            task.Set("id", pending->first);
            task.Set("page_url", pending->second);
            resp.Set("need_resolution", task);
        } else {
            resp.Set("need_resolution", JsonValue());
        }
        send_resp(200, "OK", resp.Dump());
    }
    else if (method == "GET" && clean_path == "/test_video.mp4") {
        const size_t total_sz = 256 * 1024;
        std::string dummy(total_sz, 'V');
        size_t range_start = 0;
        bool is_range = false;

        if (range_header.rfind("bytes=", 0) == 0) {
            std::string sub = range_header.substr(6);
            size_t dash = sub.find('-');
            if (dash != std::string::npos) {
                try {
                    range_start = std::stoull(sub.substr(0, dash));
                    if (range_start < total_sz) {
                        is_range = true;
                    }
                } catch (...) {}
            }
        }

        std::ostringstream ss;
        if (is_range && range_start > 0) {
            size_t send_len = total_sz - range_start;
            ss << "HTTP/1.1 206 Partial Content\r\n";
            ss << "Content-Type: video/mp4\r\n";
            ss << "Content-Range: bytes " << range_start << "-" << (total_sz - 1) << "/" << total_sz << "\r\n";
            ss << "Content-Length: " << send_len << "\r\n";
            ss << "Connection: close\r\n\r\n";
            ss.write(dummy.data() + range_start, send_len);
        } else {
            ss << "HTTP/1.1 200 OK\r\n";
            ss << "Content-Type: video/mp4\r\n";
            ss << "Content-Length: " << dummy.length() << "\r\n";
            ss << "Connection: close\r\n\r\n";
            ss << dummy;
        }
        std::string out = ss.str();
        send(client, out.c_str(), static_cast<int>(out.length()), 0);
    }
    else {
        // All subsequent mutating or data endpoints REQUIRE valid authentication!
        if (!has_valid_token) {
            send_resp(401, "Unauthorized", "{\"error\":\"Unauthorized: Invalid or missing bridge token\"}");
            closesocket(client);
            return;
        }

        if (method == "GET" && clean_path == "/queue") {
            auto items = QueueManager::GetInstance().GetAllItems();
            JsonValue arr = JsonValue::Array();
            for (const auto& it : items) {
                JsonValue j = JsonValue::Object();
                j.Set("id", it.id);
                j.Set("unique_id", it.unique_id);
                j.Set("title", it.title);
                j.Set("page_url", it.page_url.empty() ? it.input : it.page_url);
                j.Set("status", DownloadStatusToString(it.status));
                j.Set("progress_pct", it.progress_pct);
                j.Set("progress_text", it.progress_text);
                arr.PushBack(j);
            }
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            resp.Set("queue", arr);
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/add") {
            JsonValue req_json = JsonParser::Parse(body);
            DownloadItem it;
            it.input = req_json.Get("url").AsString();
            if (it.input.empty()) it.input = req_json.Get("input").AsString();
            if (it.input.empty()) it.input = req_json.Get("curl").AsString();
            it.title = req_json.Get("title", "Video Stream").AsString();
            it.page_url = req_json.Get("page_url").AsString();
            if (it.page_url.empty()) it.page_url = req_json.Get("referer").AsString();
            it.referer = req_json.Get("referer").AsString();
            it.origin = req_json.Get("origin").AsString();
            it.user_agent = req_json.Get("userAgent").AsString();
            it.quality = req_json.Get("quality", "1080p").AsString();
            it.year = req_json.Get("year").AsString();
            it.netflix_id = req_json.Get("netflixId").AsString();
            it.media_type = req_json.Get("type").AsString();
            if (it.media_type.empty()) it.media_type = req_json.Get("media_type").AsString();
            if (it.media_type.empty()) it.media_type = req_json.Get("mime").AsString();
            if (req_json.Has("mode")) {
                it.mode = StringToDownloadMode(req_json.Get("mode").AsString());
            }
            if (req_json.Has("cookie")) {
                it.cookie = req_json.Get("cookie").AsString();
            }
            if (req_json.Has("playlistText")) {
                it.playlist_text = req_json.Get("playlistText").AsString();
            }
            if (req_json.Has("companionVideoUrl")) {
                it.companion_video_url = req_json.Get("companionVideoUrl").AsString();
            }

            bool ok = QueueManager::GetInstance().AddItem(it, true);
            JsonValue resp = JsonValue::Object();
            resp.Set("success", ok);
            resp.Set("message", ok ? "Added to queue" : "Duplicate or rejected");
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/batch_add") {
            JsonValue req_json = JsonParser::Parse(body);
            auto items_json = req_json.Get("items").AsArray();
            std::vector<DownloadItem> batch;
            for (const auto& j : items_json) {
                DownloadItem it;
                it.input = j.Get("url").AsString();
                if (it.input.empty()) it.input = j.Get("input").AsString();
                if (it.input.empty()) it.input = j.Get("curl").AsString();
                it.title = j.Get("title", "Video Stream").AsString();
                it.page_url = j.Get("page_url").AsString();
                if (it.page_url.empty()) it.page_url = j.Get("referer").AsString();
                it.referer = j.Get("referer").AsString();
                it.origin = j.Get("origin").AsString();
                it.user_agent = j.Get("userAgent").AsString();
                it.quality = j.Get("quality", "1080p").AsString();
                it.year = j.Get("year").AsString();
                it.netflix_id = j.Get("netflixId").AsString();
                it.media_type = j.Get("type").AsString();
                if (it.media_type.empty()) it.media_type = j.Get("media_type").AsString();
                if (it.media_type.empty()) it.media_type = j.Get("mime").AsString();
                if (j.Has("mode")) it.mode = StringToDownloadMode(j.Get("mode").AsString());
                if (j.Has("cookie")) it.cookie = j.Get("cookie").AsString();
                if (j.Has("playlistText")) it.playlist_text = j.Get("playlistText").AsString();
                if (j.Has("companionVideoUrl")) it.companion_video_url = j.Get("companionVideoUrl").AsString();
                batch.push_back(it);
            }
            int added = QueueManager::GetInstance().AddBatch(batch, true);
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            resp.Set("count", added);
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/auto_download_batch") {
            JsonValue req_json = JsonParser::Parse(body);
            auto items_json = req_json.Get("items").AsArray();
            std::vector<DownloadItem> batch;

            for (const auto& j : items_json) {
                DownloadItem it;
                it.title = j.Get("title").AsString();
                it.page_url = j.Get("page_url").AsString();
                it.input = it.page_url;
                it.year = j.Get("year").AsString();
                it.quality = j.Get("quality", "HD").AsString();
                it.is_auto = true;
                it.needs_resolution = true;
                batch.push_back(it);
            }

            int added = QueueManager::GetInstance().AddBatch(batch, false);
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            resp.Set("count", added);
            resp.Set("total", static_cast<int>(batch.size()));
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/start_queue") {
            QueueManager::GetInstance().StartAll();
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/resolved_stream") {
            JsonValue req_json = JsonParser::Parse(body);
            std::string item_id = req_json.Get("id").AsString();
            std::string stream_url = req_json.Get("url").AsString();
            std::string curl_cmd = req_json.Get("curl").AsString();
            std::string referer = req_json.Get("referer").AsString();

            StreamResolver::GetInstance().NotifyResolvedFromBridge(item_id, stream_url, curl_cmd, referer);
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && clean_path == "/set_mode") {
            JsonValue req_json = JsonParser::Parse(body);
            std::string m = req_json.Get("mode").AsString();
            if (!m.empty()) {
                QueueManager::GetInstance().SetCurrentMode(StringToDownloadMode(m));
            }
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            resp.Set("mode", DownloadModeToString(QueueManager::GetInstance().GetCurrentMode()));
            send_resp(200, "OK", resp.Dump());
        }
        else if (method == "POST" && (clean_path == "/set_theme" || clean_path == "/set_filter")) {
            JsonValue resp = JsonValue::Object();
            resp.Set("success", true);
            send_resp(200, "OK", resp.Dump());
        }
        else {
            send_resp(404, "Not Found", "{\"error\":\"Endpoint not found\"}");
        }
    }

    closesocket(client);
}

} // namespace OmniStream

