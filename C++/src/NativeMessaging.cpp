#include "NativeMessaging.hpp"
#include "QueueManager.hpp"
#include "Json.hpp"
#include <iostream>
#include <io.h>
#include <fcntl.h>

namespace OmniStream {

bool NativeMessaging::SendMessageToChrome(const std::string& json_msg) {
    uint32_t len = static_cast<uint32_t>(json_msg.length());
    std::cout.write(reinterpret_cast<const char*>(&len), 4);
    std::cout.write(json_msg.data(), len);
    std::cout.flush();
    return std::cout.good();
}

bool NativeMessaging::ReadMessageFromChrome(std::string& out_msg) {
    uint32_t len = 0;
    std::cin.read(reinterpret_cast<char*>(&len), 4);
    if (!std::cin.good() || len == 0 || len > (10 * 1024 * 1024)) {
        return false;
    }
    out_msg.resize(len);
    std::cin.read(&out_msg[0], len);
    return std::cin.good();
}

void NativeMessaging::RunHostLoop() {
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);

    std::string msg;
    while (ReadMessageFromChrome(msg)) {
        JsonValue req = JsonParser::Parse(msg);
        std::string action = req.Get("action").AsString();

        JsonValue resp = JsonValue::Object();
        resp.Set("action", action);

        if (action == "PING") {
            resp.Set("status", "PONG");
            resp.Set("version", "2.6.0");
        } else if (action == "GET_QUEUE") {
            auto items = QueueManager::GetInstance().GetAllItems();
            JsonValue arr = JsonValue::Array();
            for (const auto& it : items) {
                JsonValue j = JsonValue::Object();
                j.Set("id", it.id);
                j.Set("unique_id", it.unique_id);
                j.Set("title", it.title);
                j.Set("status", DownloadStatusToString(it.status));
                arr.PushBack(j);
            }
            resp.Set("queue", arr);
        } else if (action == "ADD_STREAM") {
            DownloadItem it;
            it.input = req.Get("url").AsString();
            it.title = req.Get("title", "Video Stream").AsString();
            bool ok = QueueManager::GetInstance().AddItem(it, true);
            resp.Set("success", ok);
        }

        SendMessageToChrome(resp.Dump());
    }
}

} // namespace OmniStream

