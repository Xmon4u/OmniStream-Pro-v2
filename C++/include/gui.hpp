#pragma once

#include "common.hpp"
#include "download_engine.hpp"
#include "bridge_server.hpp"
#include <vector>
#include <string>

namespace OmniStream {

struct QueueItem {
    std::string id;
    std::string title;
    std::string url;
    std::string resolution;
    std::string status;     // "Queued", "Downloading", "Completed", "Failed"
    float progress = 0.0f;
    std::string speed = "--";
    std::string sizeStr = "--";
};

class MainWindow {
public:
    MainWindow(HINSTANCE hInstance);
    ~MainWindow();

    bool CreateAndShow(int nCmdShow);
    int RunMessageLoop();

private:
    static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);
    static LRESULT CALLBACK EditSubclassProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);
    LRESULT HandleMessage(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam);

    void SetupControls();
    void ApplyTheme();
    void AppendLog(const std::string& msg);
    void UpdateProgress(float pct, const std::string& speed, const std::string& eta, uint64_t bytes);
    void StartDownload(bool subtitleOnly = false);
    void AbortDownload();
    void PasteClipboard();
    void BrowseSaveDirectory();
    void SwitchTab(bool toQueue);
    void AddToQueue(const std::string& url, const std::string& title, const std::string& res);
    void StartQueueProcessing();
    void ClearQueue();

    // Custom Drawing
    void DrawHeader(HDC hdc, const RECT& rc);
    void DrawBanner(HDC hdc, const RECT& rc);
    void DrawCard(HDC hdc, const RECT& rc, const std::wstring& title, const std::wstring& subtitle = L"");
    void DrawProgressCard(HDC hdc, const RECT& rc);
    void DrawFooter(HDC hdc, const RECT& rc);
    void DrawCustomButton(LPDRAWITEMSTRUCT dis);

    HINSTANCE m_hInstance;
    HWND m_hwnd = nullptr;

    // Controls
    HWND m_hEditUrl = nullptr;
    HWND m_hBtnPaste = nullptr;
    
    HWND m_hEditTitle = nullptr;
    HWND m_hComboRes = nullptr;
    HWND m_hEditDir = nullptr;
    HWND m_hBtnBrowse = nullptr;
    HWND m_hComboAudio = nullptr;
    HWND m_hComboMode = nullptr;
    HWND m_hComboSubFormat = nullptr;
    HWND m_hComboSubLang = nullptr;
    HWND m_hCheckEmbedSubs = nullptr;

    HWND m_hBtnDownload = nullptr;
    HWND m_hBtnDownloadSubs = nullptr;
    HWND m_hBtnAbort = nullptr;

    // Tabs
    HWND m_hBtnTabQueue = nullptr;
    HWND m_hBtnTabTerminal = nullptr;
    HWND m_hBtnClearLogs = nullptr;
    HWND m_hBtnDownloadAll = nullptr;
    HWND m_hBtnClearQueue = nullptr;
    HWND m_hListQueue = nullptr;
    HWND m_hEditLog = nullptr;

    // GDI Brushes & Fonts
    HBRUSH m_hBgBrush = nullptr;
    HBRUSH m_hCardBrush = nullptr;
    HBRUSH m_hCard2Brush = nullptr;
    HBRUSH m_hInputBrush = nullptr;
    HBRUSH m_hTerminalBrush = nullptr;

    HFONT m_hFontAppTitle = nullptr;
    HFONT m_hFontTitle = nullptr;
    HFONT m_hFontBold = nullptr;
    HFONT m_hFontNormal = nullptr;
    HFONT m_hFontSmall = nullptr;
    HFONT m_hFontLog = nullptr;
    HFONT m_hFontBigPct = nullptr;

    // Animation & Progress State
    float m_displayProgress = 0.0f;
    float m_targetProgress = 0.0f;
    std::string m_curSpeed = "0.0 MB/s";
    std::string m_curEta = "--";
    std::string m_curSizeStr = "-- / --";
    std::string m_curTitle = "Ready to Download";
    std::string m_curStatus = "Ready \u2014 Paste a stream URL above or send links from the Chrome extension.";
    uint32_t m_pulseCounter = 0;
    bool m_activeTabQueue = true; // true = Queue, false = Terminal

    // Queue
    std::vector<QueueItem> m_queueItems;
    bool m_isQueueRunning = false;

    // Engine & Server
    std::unique_ptr<BridgeServer> m_bridgeServer;
    std::unique_ptr<DownloadEngine> m_currentEngine;
    std::unique_ptr<std::thread> m_downloadThread;
    std::atomic<bool> m_isDownloading{ false };
};

} // namespace OmniStream
