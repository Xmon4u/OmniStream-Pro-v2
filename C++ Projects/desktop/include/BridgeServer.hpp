#pragma once

#include "Common.hpp"
#include <string>
#include <atomic>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <winsock2.h>

#pragma comment(lib, "ws2_32.lib")

namespace OmniStream {

class BridgeServer {
public:
    static BridgeServer& GetInstance();

    bool Start(int port = 28795);
    void Stop();
    bool IsRunning() const { return running_.load(); }

    std::string GetToken() const { return bridge_token_; }

private:
    BridgeServer();
    ~BridgeServer();

    std::atomic<bool> running_{false};
    SOCKET server_socket_ = INVALID_SOCKET;
    int port_ = 28795;
    std::string bridge_token_;
    std::thread server_thread_;

    std::mutex clients_mutex_;
    std::condition_variable clients_cv_;
    std::atomic<int> active_clients_{0};

    void ListenLoop();
    void HandleClient(SOCKET client_socket);
    void InitOrLoadToken();
};

} // namespace OmniStream

