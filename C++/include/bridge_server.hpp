#pragma once

#include "common.hpp"
#include "download_engine.hpp"

namespace OmniStream {

class BridgeServer {
public:
    BridgeServer(int port = BRIDGE_PORT, const std::string& token = "");
    ~BridgeServer();

    bool Start();
    void Stop();
    bool IsRunning() const { return m_running.load(); }

    std::string GetToken() const { return m_token; }

    void SetCurrentMode(const std::string& mode) { m_currentMode = mode; }
    std::string GetCurrentMode() const { return m_currentMode; }

    void SetOnJobReceived(std::function<void(const DownloadOptions& opts)> callback) {
        m_onJobReceived = callback;
    }

    void SetOnModeChanged(std::function<void(const std::string& mode)> callback) {
        m_onModeChanged = callback;
    }

    void SetOnStartQueue(std::function<void()> callback) {
        m_onStartQueue = callback;
    }

    void SetOnFocus(std::function<void()> callback) {
        m_onFocus = callback;
    }

private:
    void ServerThread();
    void HandleClient(SOCKET clientSocket);

    int m_port;
    std::string m_token;
    std::atomic<bool> m_running{ false };
    SOCKET m_listenSocket = INVALID_SOCKET;
    std::unique_ptr<std::thread> m_workerThread;
    std::function<void(const DownloadOptions& opts)> m_onJobReceived;
    std::function<void(const std::string& mode)> m_onModeChanged;
    std::function<void()> m_onStartQueue;
    std::function<void()> m_onFocus;
    std::string m_currentMode = "normal";
};

} // namespace OmniStream
