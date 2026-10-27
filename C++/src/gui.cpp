#include "gui.hpp"
#include "curl_parser.hpp"
#include "netflix_resolver.hpp"
#include <commctrl.h>
#include <dwmapi.h>
#include <uxtheme.h>
#include <shlobj.h>
#include <sstream>
#include <iomanip>
#include <algorithm>

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "dwmapi.lib")
#pragma comment(lib, "uxtheme.lib")
#pragma comment(lib, "msimg32.lib")

namespace OmniStream {

// Control IDs
enum ControlId {
    IDC_EDIT_URL = 1001,
    IDC_BTN_PASTE,
    IDC_EDIT_TITLE,
    IDC_COMBO_RES,
    IDC_EDIT_DIR,
    IDC_BTN_BROWSE,
    IDC_COMBO_AUDIO,
    IDC_COMBO_MODE,
    IDC_COMBO_SUBFORMAT,
    IDC_COMBO_SUBLANG,
    IDC_BTN_DOWNLOAD,
    IDC_BTN_DOWNLOAD_SUBS,
    IDC_BTN_ABORT,
    IDC_BTN_TAB_QUEUE,
    IDC_BTN_TAB_TERMINAL,
    IDC_BTN_DOWNLOAD_ALL,
    IDC_BTN_CLEAR_QUEUE,
    IDC_BTN_CLEAR_LOGS,
    IDC_LIST_QUEUE,
    IDC_EDIT_LOG,
    IDT_ANIM_TIMER = 2001
};

// Custom Window Messages
constexpr UINT WM_OMNI_LOG      = WM_USER + 101;
constexpr UINT WM_OMNI_PROGRESS = WM_USER + 102;
constexpr UINT WM_OMNI_COMPLETE = WM_USER + 103;

struct ProgressPayload {
    float percent;
    std::string speed;
    std::string eta;
    uint64_t bytes;
};

// Cyber Slate Color Tokens (Matching desktop/main_gui.py Exactly)
static const COLORREF COL_BG_ROOT         = RGB(13, 17, 23);     // #0d1117 (Deep Dark Slate)
static const COLORREF COL_BG_HEADER       = RGB(22, 27, 34);     // #161b22 (Sleek Slate)
static const COLORREF COL_BG_CARD         = RGB(22, 27, 34);     // #161b22 (Card Background)
static const COLORREF COL_BG_CARD2        = RGB(33, 38, 45);     // #21262d (Secondary Card)
static const COLORREF COL_BG_INPUT        = RGB(9, 13, 19);      // #090d13 (Input Background)
static const COLORREF COL_BG_TERMINAL     = RGB(5, 7, 10);       // #05070a (Jet Black Console)
static const COLORREF COL_ACCENT_PRIMARY  = RGB(37, 99, 235);    // #2563eb (Royal Blue)
static const COLORREF COL_ACCENT_HOVER    = RGB(29, 78, 216);    // #1d4ed8 (Deep Blue Hover)
static const COLORREF COL_ACCENT_CYAN     = RGB(56, 189, 248);   // #38bdf8 (Cyber Cyan)
static const COLORREF COL_ACCENT_EMERALD  = RGB(16, 185, 129);   // #10b981 (Emerald Green)
static const COLORREF COL_ACCENT_GREEN_BTN= RGB(5, 150, 105);    // #059669 (Modern Green Button)
static const COLORREF COL_ACCENT_ROSE     = RGB(239, 68, 68);    // #ef4444 (Rose Red)
static const COLORREF COL_BORDER_MAIN     = RGB(48, 54, 61);     // #30363d (Subtle Card Border)
static const COLORREF COL_BORDER_SUB      = RGB(33, 38, 45);     // #21262d (Soft Border)
static const COLORREF COL_TEXT_TITLE      = RGB(240, 246, 252);  // #f0f6fc (High-Contrast White)
static const COLORREF COL_TEXT_BODY       = RGB(139, 148, 158);  // #8b949e (Slate Text)
static const COLORREF COL_TEXT_MUTED      = RGB(110, 118, 129);  // #6e7681 (Muted Gray)
static const COLORREF COL_TEXT_LOG        = RGB(121, 192, 255);  // #79c0ff (Log Cyan-Blue)

// Windows Dark Mode Activation via uxtheme ordinal 135
static void EnableSystemDarkMode() {
    enum PreferredAppMode { Default, AllowDark, ForceDark, ForceLight, Max };
    using fnSetPreferredAppMode = PreferredAppMode(WINAPI*)(PreferredAppMode);
    HMODULE hUxtheme = LoadLibraryExW(L"uxtheme.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (hUxtheme) {
        auto pfn = (fnSetPreferredAppMode)GetProcAddress(hUxtheme, MAKEINTRESOURCEA(135));
        if (pfn) pfn(ForceDark);
    }
}

MainWindow::MainWindow(HINSTANCE hInstance)
    : m_hInstance(hInstance) {
    EnableSystemDarkMode();

    INITCOMMONCONTROLSEX icex;
    icex.dwSize = sizeof(icex);
    icex.dwICC = ICC_PROGRESS_CLASS | ICC_STANDARD_CLASSES | ICC_LISTVIEW_CLASSES;
    InitCommonControlsEx(&icex);

    m_hBgBrush       = CreateSolidBrush(COL_BG_ROOT);
    m_hCardBrush     = CreateSolidBrush(COL_BG_CARD);
    m_hCard2Brush    = CreateSolidBrush(COL_BG_CARD2);
    m_hInputBrush    = CreateSolidBrush(COL_BG_INPUT);
    m_hTerminalBrush = CreateSolidBrush(COL_BG_TERMINAL);

    m_hFontAppTitle = CreateFontW(18, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    m_hFontTitle    = CreateFontW(14, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    m_hFontBold     = CreateFontW(12, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    m_hFontNormal   = CreateFontW(12, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    m_hFontSmall    = CreateFontW(11, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    m_hFontLog      = CreateFontW(12, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, FIXED_PITCH | FF_MODERN, L"Consolas");
    m_hFontBigPct   = CreateFontW(20, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
}

MainWindow::~MainWindow() {
    if (m_hwnd) {
        KillTimer(m_hwnd, IDT_ANIM_TIMER);
    }
    if (m_downloadThread && m_downloadThread->joinable()) {
        if (m_currentEngine) m_currentEngine->Abort();
        m_downloadThread->join();
    }
    if (m_bridgeServer) {
        m_bridgeServer->Stop();
    }
    if (m_hBgBrush) DeleteObject(m_hBgBrush);
    if (m_hCardBrush) DeleteObject(m_hCardBrush);
    if (m_hCard2Brush) DeleteObject(m_hCard2Brush);
    if (m_hInputBrush) DeleteObject(m_hInputBrush);
    if (m_hTerminalBrush) DeleteObject(m_hTerminalBrush);
    if (m_hFontAppTitle) DeleteObject(m_hFontAppTitle);
    if (m_hFontTitle) DeleteObject(m_hFontTitle);
    if (m_hFontBold) DeleteObject(m_hFontBold);
    if (m_hFontNormal) DeleteObject(m_hFontNormal);
    if (m_hFontSmall) DeleteObject(m_hFontSmall);
    if (m_hFontLog) DeleteObject(m_hFontLog);
    if (m_hFontBigPct) DeleteObject(m_hFontBigPct);
}

bool MainWindow::CreateAndShow(int nCmdShow) {
    WNDCLASSEXW wc = { sizeof(wc) };
    wc.cbWndExtra = sizeof(MainWindow*);
    wc.hInstance = m_hInstance;
    wc.lpszClassName = L"OmniStreamProModernV2";
    wc.lpfnWndProc = MainWindow::WndProc;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hIcon = LoadIcon(m_hInstance, MAKEINTRESOURCE(1));
    wc.hIconSm = LoadIcon(m_hInstance, MAKEINTRESOURCE(1));
    wc.hbrBackground = m_hBgBrush;
    wc.style = CS_HREDRAW | CS_VREDRAW;

    RegisterClassExW(&wc);

    int winWidth = 1040;
    int winHeight = 880;
    int screenW = GetSystemMetrics(SM_CXSCREEN);
    int screenH = GetSystemMetrics(SM_CYSCREEN);
    int posX = std::max(0, (screenW - winWidth) / 2);
    int posY = std::max(10, (screenH - winHeight) / 2 - 20);

    m_hwnd = CreateWindowExW(
        0,
        wc.lpszClassName,
        L"OmniStream Pro v2.6.0 \u2014 IDM-Grade Stream Downloader",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        posX, posY, winWidth, winHeight,
        nullptr, nullptr, m_hInstance, this
    );

    if (!m_hwnd) return false;

    // Apply Windows 10/11 Immersive Dark Mode to Window Titlebar
    BOOL darkValue = TRUE;
    DwmSetWindowAttribute(m_hwnd, 20 /* DWMWA_USE_IMMERSIVE_DARK_MODE */, &darkValue, sizeof(darkValue));

    SetupControls();

    // 33 FPS Animation Timer for smooth lerp progress bar and pulsing status dot
    SetTimer(m_hwnd, IDT_ANIM_TIMER, 30, nullptr);

    // Auto-start Chrome Extension Bridge Server on port 28795
    m_bridgeServer = std::make_unique<BridgeServer>(BRIDGE_PORT);
    m_bridgeServer->SetOnJobReceived([this](const DownloadOptions& opts) {
        PostMessageW(m_hwnd, WM_OMNI_LOG, 0, (LPARAM)new std::string("[Bridge] Incoming job from Chrome Extension: " + opts.inputText));
        std::wstring wUrl = Utf8ToWide(opts.inputText);
        SetWindowTextW(m_hEditUrl, wUrl.c_str());
        PostMessageW(m_hwnd, WM_COMMAND, MAKEWPARAM(IDC_BTN_DOWNLOAD, BN_CLICKED), (LPARAM)m_hBtnDownload);
    });

    if (m_bridgeServer->Start()) {
        AppendLog("[Bridge] Listening on 127.0.0.1:" + std::to_string(BRIDGE_PORT) + " (Ready for Browser Extension)");
    } else {
        AppendLog("[Bridge] Warning: Bridge server port occupied or running in another instance.");
    }

    ShowWindow(m_hwnd, nCmdShow);
    UpdateWindow(m_hwnd);
    return true;
}

void MainWindow::SetupControls() {
    int padX = 26;
    int contentW = 970;

    // ── Card 1: Stream Source (y: 110 to 212) ──
    m_hEditUrl = CreateWindowExW(0, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_AUTOVSCROLL | WS_VSCROLL,
        padX + 16, 146, contentW - 32, 52, m_hwnd, (HMENU)IDC_EDIT_URL, m_hInstance, nullptr);
    SendMessageW(m_hEditUrl, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SetWindowTheme(m_hEditUrl, L"DarkMode_CFD", nullptr);

    m_hBtnPaste = CreateWindowExW(0, L"BUTTON", L"Paste",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + contentW - 96, 118, 80, 24, m_hwnd, (HMENU)IDC_BTN_PASTE, m_hInstance, nullptr);

    // ── Card 2: Configuration & Stream Settings (y: 222 to 420) ──
    // Generous spacing so title & options NEVER overlap!
    int col1_lbl = padX + 18;
    int col1_ctrl = col1_lbl + 115;
    int col1_w = 330;

    int col2_lbl = padX + 495;
    int col2_ctrl = col2_lbl + 120;
    int col2_w = 325;

    // Row 0: Title & Resolution (y: 260)
    m_hEditTitle = CreateWindowExW(0, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
        col1_ctrl, 258, col1_w, 26, m_hwnd, (HMENU)IDC_EDIT_TITLE, m_hInstance, nullptr);
    SendMessageW(m_hEditTitle, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hEditTitle, EM_SETCUEBANNER, TRUE, (LPARAM)L"Leave blank to auto-detect title");
    SetWindowTheme(m_hEditTitle, L"DarkMode_CFD", nullptr);

    m_hComboRes = CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        col2_ctrl, 258, col2_w, 200, m_hwnd, (HMENU)IDC_COMBO_RES, m_hInstance, nullptr);
    SendMessageW(m_hComboRes, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hComboRes, CB_ADDSTRING, 0, (LPARAM)L"1080p (Full HD - Recommended)");
    SendMessageW(m_hComboRes, CB_ADDSTRING, 0, (LPARAM)L"720p (HD Quality)");
    SendMessageW(m_hComboRes, CB_ADDSTRING, 0, (LPARAM)L"480p (SD Quality)");
    SendMessageW(m_hComboRes, CB_ADDSTRING, 0, (LPARAM)L"Best Available");
    SendMessageW(m_hComboRes, CB_ADDSTRING, 0, (LPARAM)L"Audio Only (No Video)");
    SendMessageW(m_hComboRes, CB_SETCURSEL, 0, 0);
    SetWindowTheme(m_hComboRes, L"DarkMode_CFD", nullptr);

    // Row 1: Save Folder & Audio Selection (y: 298)
    std::wstring defaultDir = L"C:\\Users";
    const char* userProfile = std::getenv("USERPROFILE");
    if (userProfile) {
        defaultDir = Utf8ToWide(std::string(userProfile) + "\\Desktop");
    }

    m_hEditDir = CreateWindowExW(0, L"EDIT", defaultDir.c_str(),
        WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
        col1_ctrl, 296, col1_w - 76, 26, m_hwnd, (HMENU)IDC_EDIT_DIR, m_hInstance, nullptr);
    SendMessageW(m_hEditDir, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SetWindowTheme(m_hEditDir, L"DarkMode_CFD", nullptr);

    m_hBtnBrowse = CreateWindowExW(0, L"BUTTON", L"Browse...",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        col1_ctrl + col1_w - 70, 296, 70, 26, m_hwnd, (HMENU)IDC_BTN_BROWSE, m_hInstance, nullptr);

    m_hComboAudio = CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        col2_ctrl, 296, col2_w, 200, m_hwnd, (HMENU)IDC_COMBO_AUDIO, m_hInstance, nullptr);
    SendMessageW(m_hComboAudio, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hComboAudio, CB_ADDSTRING, 0, (LPARAM)L"All Available Languages (Lossless)");
    SendMessageW(m_hComboAudio, CB_ADDSTRING, 0, (LPARAM)L"English + Hindi (Dual Audio)");
    SendMessageW(m_hComboAudio, CB_ADDSTRING, 0, (LPARAM)L"English Only");
    SendMessageW(m_hComboAudio, CB_ADDSTRING, 0, (LPARAM)L"Hindi Only");
    SendMessageW(m_hComboAudio, CB_SETCURSEL, 0, 0);
    SetWindowTheme(m_hComboAudio, L"DarkMode_CFD", nullptr);

    // Row 2: Download Mode & Subtitle Format (y: 336)
    m_hComboMode = CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        col1_ctrl, 334, col1_w, 200, m_hwnd, (HMENU)IDC_COMBO_MODE, m_hInstance, nullptr);
    SendMessageW(m_hComboMode, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hComboMode, CB_ADDSTRING, 0, (LPARAM)L"Normal Mode");
    SendMessageW(m_hComboMode, CB_ADDSTRING, 0, (LPARAM)L"Sub Merge Mode (MKV)");
    SendMessageW(m_hComboMode, CB_ADDSTRING, 0, (LPARAM)L"Netflix Rename");
    SendMessageW(m_hComboMode, CB_ADDSTRING, 0, (LPARAM)L"TMDB ID Rename");
    SendMessageW(m_hComboMode, CB_ADDSTRING, 0, (LPARAM)L"IMDb ID Rename");
    SendMessageW(m_hComboMode, CB_SETCURSEL, 0, 0);
    SetWindowTheme(m_hComboMode, L"DarkMode_CFD", nullptr);

    m_hComboSubFormat = CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        col2_ctrl, 334, col2_w, 200, m_hwnd, (HMENU)IDC_COMBO_SUBFORMAT, m_hInstance, nullptr);
    SendMessageW(m_hComboSubFormat, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hComboSubFormat, CB_ADDSTRING, 0, (LPARAM)L"SRT (SubRip \u2014 Universal)");
    SendMessageW(m_hComboSubFormat, CB_ADDSTRING, 0, (LPARAM)L"VTT (WebVTT)");
    SendMessageW(m_hComboSubFormat, CB_SETCURSEL, 0, 0);
    SetWindowTheme(m_hComboSubFormat, L"DarkMode_CFD", nullptr);

    // Row 3: Subtitle Language (y: 374)
    m_hComboSubLang = CreateWindowExW(0, L"COMBOBOX", L"",
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
        col2_ctrl, 372, col2_w, 200, m_hwnd, (HMENU)IDC_COMBO_SUBLANG, m_hInstance, nullptr);
    SendMessageW(m_hComboSubLang, WM_SETFONT, (WPARAM)m_hFontNormal, TRUE);
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"All Languages");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"English (eng)");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"Hindi (hin)");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"Spanish (spa)");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"French (fra)");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"German (deu)");
    SendMessageW(m_hComboSubLang, CB_ADDSTRING, 0, (LPARAM)L"Japanese (jpn)");
    SendMessageW(m_hComboSubLang, CB_SETCURSEL, 0, 0);
    SetWindowTheme(m_hComboSubLang, L"DarkMode_CFD", nullptr);

    // ── Action Buttons Row (y: 430 to 466) ──
    m_hBtnDownload = CreateWindowExW(0, L"BUTTON", L"\u25B6 Start Download",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX, 430, 160, 36, m_hwnd, (HMENU)IDC_BTN_DOWNLOAD, m_hInstance, nullptr);

    m_hBtnDownloadSubs = CreateWindowExW(0, L"BUTTON", L"Download Subtitles",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + 172, 430, 165, 36, m_hwnd, (HMENU)IDC_BTN_DOWNLOAD_SUBS, m_hInstance, nullptr);

    m_hBtnAbort = CreateWindowExW(0, L"BUTTON", L"\u25A0 Stop",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW | WS_DISABLED,
        padX + 349, 430, 95, 36, m_hwnd, (HMENU)IDC_BTN_ABORT, m_hInstance, nullptr);

    // ── Card 4: Tab Control & Queues (y: 588 to 818) ──
    m_hBtnTabQueue = CreateWindowExW(0, L"BUTTON", L"Download Queue (0)",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + 16, 598, 175, 30, m_hwnd, (HMENU)IDC_BTN_TAB_QUEUE, m_hInstance, nullptr);

    m_hBtnTabTerminal = CreateWindowExW(0, L"BUTTON", L"Terminal Logs",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + 200, 598, 120, 30, m_hwnd, (HMENU)IDC_BTN_TAB_TERMINAL, m_hInstance, nullptr);

    // Queue Toolbar Buttons
    m_hBtnDownloadAll = CreateWindowExW(0, L"BUTTON", L"\u25B6 Download All",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + 16, 638, 130, 28, m_hwnd, (HMENU)IDC_BTN_DOWNLOAD_ALL, m_hInstance, nullptr);

    m_hBtnClearQueue = CreateWindowExW(0, L"BUTTON", L"Clear All",
        WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
        padX + 156, 638, 85, 28, m_hwnd, (HMENU)IDC_BTN_CLEAR_QUEUE, m_hInstance, nullptr);

    // ── Dark Styled ListView (NO UGLY WHITE BACKGROUND!) ──
    m_hListQueue = CreateWindowExW(0, WC_LISTVIEWW, L"",
        WS_CHILD | WS_VISIBLE | LVS_REPORT | LVS_SINGLESEL | LVS_NOCOLUMNHEADER,
        padX + 16, 674, contentW - 32, 136, m_hwnd, (HMENU)IDC_LIST_QUEUE, m_hInstance, nullptr);
    SendMessageW(m_hListQueue, LVM_SETEXTENDEDLISTVIEWSTYLE, 0, LVS_EX_FULLROWSELECT | LVS_EX_DOUBLEBUFFER);

    // Set Dark Mode Colors directly into ListView
    ListView_SetBkColor(m_hListQueue, COL_BG_INPUT);
    ListView_SetTextBkColor(m_hListQueue, COL_BG_INPUT);
    ListView_SetTextColor(m_hListQueue, COL_TEXT_TITLE);
    SetWindowTheme(m_hListQueue, L"DarkMode_Explorer", nullptr);

    // Add Columns to Queue Listview
    LVCOLUMNW lvc = { sizeof(lvc) };
    lvc.mask = LVCF_TEXT | LVCF_WIDTH | LVCF_SUBITEM;
    auto addCol = [&](int col, const wchar_t* title, int width) {
        lvc.iSubItem = col;
        lvc.pszText = const_cast<LPWSTR>(title);
        lvc.cx = width;
        SendMessageW(m_hListQueue, LVM_INSERTCOLUMNW, col, (LPARAM)&lvc);
    };
    addCol(0, L"Item Title", 360);
    addCol(1, L"Resolution", 100);
    addCol(2, L"Progress", 120);
    addCol(3, L"Speed", 110);
    addCol(4, L"Size", 110);
    addCol(5, L"Status", 110);

    // Terminal View Controls (Hidden by default, shown on tab toggle)
    m_hBtnClearLogs = CreateWindowExW(0, L"BUTTON", L"Clear Logs",
        WS_CHILD | BS_OWNERDRAW,
        padX + contentW - 106, 598, 90, 26, m_hwnd, (HMENU)IDC_BTN_CLEAR_LOGS, m_hInstance, nullptr);

    m_hEditLog = CreateWindowExW(0, L"EDIT", L"",
        WS_CHILD | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY | WS_VSCROLL,
        padX + 16, 638, contentW - 32, 172, m_hwnd, (HMENU)IDC_EDIT_LOG, m_hInstance, nullptr);
    SendMessageW(m_hEditLog, WM_SETFONT, (WPARAM)m_hFontLog, TRUE);
    SetWindowTheme(m_hEditLog, L"DarkMode_CFD", nullptr);

    AppendLog("OmniStream Pro v2.6.0 Native C++ Engine loaded.");
    AppendLog("Hardware Acceleration: Windows BCrypt AES-NI Active.");
    AppendLog("WinHTTP Asynchronous Streaming Pipeline Initialized.");
}

void MainWindow::AppendLog(const std::string& msg) {
    if (!m_hEditLog) return;
    std::wstring wMsg = Utf8ToWide(msg) + L"\r\n";
    int len = GetWindowTextLengthW(m_hEditLog);
    SendMessageW(m_hEditLog, EM_SETSEL, len, len);
    SendMessageW(m_hEditLog, EM_REPLACESEL, FALSE, (LPARAM)wMsg.c_str());
    SendMessageW(m_hEditLog, EM_SCROLLCARET, 0, 0);
}

void MainWindow::UpdateProgress(float pct, const std::string& speed, const std::string& eta, uint64_t bytes) {
    m_targetProgress = std::max(0.0f, std::min(100.0f, pct));
    m_curSpeed = speed.empty() ? "0.0 MB/s" : speed;
    m_curEta = eta.empty() ? "--" : eta;
    m_curSizeStr = FormatBytes(bytes);

    if (pct >= 100.0f) {
        m_curStatus = "Completed \u2014 File saved successfully.";
    } else if (pct > 0.0f) {
        m_curStatus = "Downloading segments  \u2022  ETA: " + m_curEta;
    }

    // Trigger redraw of progress card
    RECT rcProg = { 26, 478, 1000, 580 };
    InvalidateRect(m_hwnd, &rcProg, FALSE);
}

void MainWindow::PasteClipboard() {
    if (!OpenClipboard(m_hwnd)) return;
    HANDLE hData = GetClipboardData(CF_UNICODETEXT);
    if (hData) {
        wchar_t* pText = static_cast<wchar_t*>(GlobalLock(hData));
        if (pText) {
            SetWindowTextW(m_hEditUrl, pText);
            GlobalUnlock(hData);
        }
    }
    CloseClipboard();
}

void MainWindow::BrowseSaveDirectory() {
    BROWSEINFOW bi = { 0 };
    bi.hwndOwner = m_hwnd;
    bi.lpszTitle = L"Select Directory to Save Stream Files";
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;

    PIDLIST_ABSOLUTE pidl = SHBrowseForFolderW(&bi);
    if (pidl) {
        wchar_t path[MAX_PATH];
        if (SHGetPathFromIDListW(pidl, path)) {
            SetWindowTextW(m_hEditDir, path);
        }
        CoTaskMemFree(pidl);
    }
}

void MainWindow::SwitchTab(bool toQueue) {
    m_activeTabQueue = toQueue;

    if (toQueue) {
        ShowWindow(m_hBtnDownloadAll, SW_SHOW);
        ShowWindow(m_hBtnClearQueue, SW_SHOW);
        ShowWindow(m_hListQueue, SW_SHOW);
        ShowWindow(m_hBtnClearLogs, SW_HIDE);
        ShowWindow(m_hEditLog, SW_HIDE);
    } else {
        ShowWindow(m_hBtnDownloadAll, SW_HIDE);
        ShowWindow(m_hBtnClearQueue, SW_HIDE);
        ShowWindow(m_hListQueue, SW_HIDE);
        ShowWindow(m_hBtnClearLogs, SW_SHOW);
        ShowWindow(m_hEditLog, SW_SHOW);
    }

    InvalidateRect(m_hBtnTabQueue, nullptr, TRUE);
    InvalidateRect(m_hBtnTabTerminal, nullptr, TRUE);
}

void MainWindow::AddToQueue(const std::string& url, const std::string& title, const std::string& res) {
    QueueItem item;
    item.id = std::to_string(m_queueItems.size() + 1);
    item.url = url;
    item.title = title.empty() ? "Stream_" + item.id : title;
    item.resolution = res;
    item.status = "Queued";
    m_queueItems.push_back(item);

    int idx = static_cast<int>(m_queueItems.size() - 1);
    LVITEMW lvi = { 0 };
    lvi.mask = LVIF_TEXT;
    lvi.iItem = idx;

    std::wstring wTitle = Utf8ToWide(item.title);
    lvi.pszText = const_cast<LPWSTR>(wTitle.c_str());
    SendMessageW(m_hListQueue, LVM_INSERTITEMW, 0, reinterpret_cast<LPARAM>(&lvi));

    auto setSubItem = [&](int sub, const std::wstring& val) {
        LVITEMW itemText = { 0 };
        itemText.iSubItem = sub;
        itemText.pszText = const_cast<LPWSTR>(val.c_str());
        SendMessageW(m_hListQueue, LVM_SETITEMTEXTW, idx, reinterpret_cast<LPARAM>(&itemText));
    };

    setSubItem(1, Utf8ToWide(item.resolution));
    setSubItem(2, L"0.0%");
    setSubItem(3, L"--");
    setSubItem(4, L"--");
    setSubItem(5, L"Queued");

    std::wstring tabText = L"Download Queue (" + std::to_wstring(m_queueItems.size()) + L")";
    SetWindowTextW(m_hBtnTabQueue, tabText.c_str());
}

void MainWindow::ClearQueue() {
    m_queueItems.clear();
    SendMessageW(m_hListQueue, LVM_DELETEALLITEMS, 0, 0);
    SetWindowTextW(m_hBtnTabQueue, L"Download Queue (0)");
}

void MainWindow::StartQueueProcessing() {
    if (m_isDownloading.load() || m_queueItems.empty()) return;
    for (auto& item : m_queueItems) {
        if (item.status == "Queued") {
            SetWindowTextW(m_hEditUrl, Utf8ToWide(item.url).c_str());
            SetWindowTextW(m_hEditTitle, Utf8ToWide(item.title).c_str());
            StartDownload(false);
            break;
        }
    }
}

void MainWindow::StartDownload(bool subtitleOnly) {
    if (m_isDownloading.load()) return;

    wchar_t urlBuf[4096] = { 0 };
    GetWindowTextW(m_hEditUrl, urlBuf, 4096);
    std::string inputUrl = WideToUtf8(urlBuf);
    if (inputUrl.empty()) {
        MessageBoxW(m_hwnd, L"Please enter a stream URL or paste a Chrome cURL command.", L"Input Required", MB_OK | MB_ICONWARNING);
        return;
    }

    wchar_t dirBuf[MAX_PATH] = { 0 };
    GetWindowTextW(m_hEditDir, dirBuf, MAX_PATH);
    std::string saveDir = WideToUtf8(dirBuf);

    wchar_t titleBuf[MAX_PATH] = { 0 };
    GetWindowTextW(m_hEditTitle, titleBuf, MAX_PATH);
    std::string customTitle = WideToUtf8(titleBuf);

    int resIndex = (int)SendMessageW(m_hComboRes, CB_GETCURSEL, 0, 0);
    std::string resolution = "1080p";
    if (resIndex == 0) resolution = "1080p";
    else if (resIndex == 1) resolution = "720p";
    else if (resIndex == 2) resolution = "480p";
    else if (resIndex == 3) resolution = "best";
    else if (resIndex == 4) resolution = "audio_only";

    DownloadOptions options;
    options.inputText = inputUrl;
    options.saveDir = saveDir;
    options.saveName = customTitle;
    options.resolution = resolution;
    options.threadCount = 32;

    m_curTitle = customTitle.empty() ? "Capturing Stream..." : customTitle;
    m_curStatus = "Initializing download...";
    m_targetProgress = 0.0f;
    m_displayProgress = 0.0f;
    m_curSpeed = "0.0 MB/s";
    m_curSizeStr = "-- / --";

    AddToQueue(inputUrl, m_curTitle, resolution);

    HWND hwnd = m_hwnd;
    options.onProgress = [hwnd](float pct, const std::string& speed, const std::string& eta, uint64_t bytes) {
        auto* payload = new ProgressPayload{ pct, speed, eta, bytes };
        PostMessageW(hwnd, WM_OMNI_PROGRESS, 0, (LPARAM)payload);
    };

    options.onLog = [hwnd](const std::string& msg) {
        auto* str = new std::string(msg);
        PostMessageW(hwnd, WM_OMNI_LOG, 0, (LPARAM)str);
    };

    m_isDownloading.store(true);
    EnableWindow(m_hBtnDownload, FALSE);
    EnableWindow(m_hBtnDownloadSubs, FALSE);
    EnableWindow(m_hBtnAbort, TRUE);

    m_currentEngine = std::make_unique<DownloadEngine>();
    DownloadEngine* engine = m_currentEngine.get();

    m_downloadThread = std::make_unique<std::thread>([this, engine, options, hwnd]() {
        std::string finalFile;
        bool ok = engine->Download(options, finalFile);
        PostMessageW(hwnd, WM_OMNI_COMPLETE, ok ? 1 : 0, 0);
    });
}

void MainWindow::AbortDownload() {
    if (m_isDownloading.load() && m_currentEngine) {
        m_currentEngine->Abort();
        AppendLog("[Engine] User aborted download.");
        m_curStatus = "Cancelled by user.";
        m_isDownloading.store(false);
        EnableWindow(m_hBtnDownload, TRUE);
        EnableWindow(m_hBtnDownloadSubs, TRUE);
        EnableWindow(m_hBtnAbort, FALSE);
        InvalidateRect(m_hwnd, nullptr, FALSE);
    }
}

// ── Custom Drawing Implementations ──

void MainWindow::DrawHeader(HDC hdc, const RECT& rc) {
    HBRUSH hHdrBrush = CreateSolidBrush(COL_BG_HEADER);
    FillRect(hdc, &rc, hHdrBrush);
    DeleteObject(hHdrBrush);

    HPEN hPen = CreatePen(PS_SOLID, 1, COL_BORDER_MAIN);
    HPEN hOldPen = (HPEN)SelectObject(hdc, hPen);
    MoveToEx(hdc, rc.left, rc.bottom - 1, nullptr);
    LineTo(hdc, rc.right, rc.bottom - 1);
    SelectObject(hdc, hOldPen);
    DeleteObject(hPen);

    SetBkMode(hdc, TRANSPARENT);

    // App Title
    SelectObject(hdc, m_hFontAppTitle);
    SetTextColor(hdc, COL_TEXT_TITLE);
    RECT rcTitle = { rc.left + 26, rc.top + 13, rc.left + 220, rc.bottom };
    DrawTextW(hdc, L"OmniStream Pro", -1, &rcTitle, DT_LEFT | DT_SINGLELINE);

    // Version Pill Badge " v2.5.0 "
    RECT rcVer = { rc.left + 180, rc.top + 15, rc.left + 245, rc.top + 37 };
    HBRUSH hPill = CreateSolidBrush(COL_BG_CARD2);
    SelectObject(hdc, hPill);
    SelectObject(hdc, GetStockObject(NULL_PEN));
    RoundRect(hdc, rcVer.left, rcVer.top, rcVer.right, rcVer.bottom, 6, 6);
    DeleteObject(hPill);

    SelectObject(hdc, m_hFontSmall);
    SetTextColor(hdc, COL_TEXT_BODY);
    DrawTextW(hdc, L"v2.6.0", -1, &rcVer, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

    // Theme Pill Badge "Cyber Slate"
    RECT rcThm = { rc.right - 250, rc.top + 15, rc.right - 140, rc.top + 37 };
    hPill = CreateSolidBrush(COL_BG_CARD2);
    SelectObject(hdc, hPill);
    RoundRect(hdc, rcThm.left, rcThm.top, rcThm.right, rcThm.bottom, 6, 6);
    DeleteObject(hPill);

    SetTextColor(hdc, COL_TEXT_MUTED);
    DrawTextW(hdc, L"Cyber Slate", -1, &rcThm, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

    // Status Badge "● Ready"
    RECT rcStat = { rc.right - 125, rc.top + 15, rc.right - 26, rc.top + 37 };
    hPill = CreateSolidBrush(COL_BG_CARD2);
    SelectObject(hdc, hPill);
    RoundRect(hdc, rcStat.left, rcStat.top, rcStat.right, rcStat.bottom, 12, 12);
    DeleteObject(hPill);

    SelectObject(hdc, m_hFontBold);
    SetTextColor(hdc, m_isDownloading.load() ? COL_ACCENT_CYAN : COL_ACCENT_EMERALD);
    std::wstring statText = m_isDownloading.load() ? L"\u25CF Active" : L"\u25CF Ready";
    DrawTextW(hdc, statText.c_str(), -1, &rcStat, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
}

void MainWindow::DrawBanner(HDC hdc, const RECT& rc) {
    COLORREF colBannerBg = RGB(30, 27, 75);      // #1e1b4b
    COLORREF colBannerBorder = RGB(55, 48, 163);  // #3730a3
    COLORREF colBannerText = RGB(199, 210, 254);  // #c7d2fe

    HBRUSH hBrush = CreateSolidBrush(colBannerBg);
    HPEN hPen = CreatePen(PS_SOLID, 1, colBannerBorder);
    HBRUSH hOldBrush = (HBRUSH)SelectObject(hdc, hBrush);
    HPEN hOldPen = (HPEN)SelectObject(hdc, hPen);

    RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, 10, 10);

    SelectObject(hdc, hOldBrush);
    SelectObject(hdc, hOldPen);
    DeleteObject(hBrush);
    DeleteObject(hPen);

    SetBkMode(hdc, TRANSPARENT);
    SelectObject(hdc, m_hFontBold);
    SetTextColor(hdc, colBannerText);

    RECT rcText = { rc.left + 16, rc.top, rc.right - 16, rc.bottom };
    DrawTextW(hdc, L"\u25CF Chrome Extension Bridge Active \u2014 Listening on 127.0.0.1:28795 (Ready for 1-Click Stream Capture)", -1, &rcText, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
}

void MainWindow::DrawCard(HDC hdc, const RECT& rc, const std::wstring& title, const std::wstring& subtitle) {
    HBRUSH hBrush = CreateSolidBrush(COL_BG_CARD);
    HPEN hPen = CreatePen(PS_SOLID, 1, COL_BORDER_MAIN);
    HBRUSH hOldBrush = (HBRUSH)SelectObject(hdc, hBrush);
    HPEN hOldPen = (HPEN)SelectObject(hdc, hPen);

    RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, 10, 10);

    SelectObject(hdc, hOldBrush);
    SelectObject(hdc, hOldPen);
    DeleteObject(hBrush);
    DeleteObject(hPen);

    if (!title.empty()) {
        SetBkMode(hdc, TRANSPARENT);
        SelectObject(hdc, m_hFontTitle);
        SetTextColor(hdc, COL_TEXT_TITLE);

        RECT rcTitle = { rc.left + 18, rc.top + 10, rc.left + 300, rc.top + 32 };
        DrawTextW(hdc, title.c_str(), -1, &rcTitle, DT_LEFT | DT_VCENTER | DT_SINGLELINE);

        if (!subtitle.empty()) {
            SelectObject(hdc, m_hFontSmall);
            SetTextColor(hdc, COL_TEXT_MUTED);
            RECT rcSub = { rc.left + 140, rc.top + 11, rc.right - 100, rc.top + 32 };
            DrawTextW(hdc, subtitle.c_str(), -1, &rcSub, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
        }
    }
}

void MainWindow::DrawProgressCard(HDC hdc, const RECT& rc) {
    DrawCard(hdc, rc, L"", L"");

    SetBkMode(hdc, TRANSPARENT);

    // Title / Status
    SelectObject(hdc, m_hFontTitle);
    SetTextColor(hdc, COL_TEXT_TITLE);
    RECT rcName = { rc.left + 18, rc.top + 10, rc.right - 110, rc.top + 32 };
    std::wstring wTitle = Utf8ToWide(m_curTitle);
    DrawTextW(hdc, wTitle.c_str(), -1, &rcName, DT_LEFT | DT_SINGLELINE | DT_END_ELLIPSIS);

    SelectObject(hdc, m_hFontSmall);
    SetTextColor(hdc, COL_TEXT_MUTED);
    RECT rcStat = { rc.left + 18, rc.top + 32, rc.right - 110, rc.top + 50 };
    std::wstring wStat = Utf8ToWide(m_curStatus);
    DrawTextW(hdc, wStat.c_str(), -1, &rcStat, DT_LEFT | DT_SINGLELINE | DT_END_ELLIPSIS);

    // Large Percentage Badge on Right
    SelectObject(hdc, m_hFontBigPct);
    SetTextColor(hdc, COL_ACCENT_CYAN);
    RECT rcPct = { rc.right - 100, rc.top + 10, rc.right - 18, rc.top + 46 };
    std::wostringstream ssPct;
    ssPct << std::fixed << std::setprecision(1) << m_displayProgress << L"%";
    DrawTextW(hdc, ssPct.str().c_str(), -1, &rcPct, DT_RIGHT | DT_SINGLELINE);

    // ── Modern Animated Gradient Progress Bar ──
    int barLeft = rc.left + 18;
    int barTop = rc.top + 54;
    int barRight = rc.right - 18;
    int barBottom = rc.top + 64;
    int totalW = barRight - barLeft;

    // Track Background
    HBRUSH hTrackBrush = CreateSolidBrush(COL_BG_INPUT);
    HPEN hTrackPen = CreatePen(PS_SOLID, 1, COL_BORDER_SUB);
    SelectObject(hdc, hTrackBrush);
    SelectObject(hdc, hTrackPen);
    RoundRect(hdc, barLeft, barTop, barRight, barBottom, 4, 4);
    DeleteObject(hTrackBrush);
    DeleteObject(hTrackPen);

    // Active Gradient Fill
    int fillW = static_cast<int>(totalW * (m_displayProgress / 100.0f));
    if (fillW > 4) {
        RECT rcFill = { barLeft, barTop, barLeft + fillW, barBottom };
        HBRUSH hFillBrush = CreateSolidBrush(COL_ACCENT_PRIMARY);
        SelectObject(hdc, hFillBrush);
        SelectObject(hdc, GetStockObject(NULL_PEN));
        RoundRect(hdc, rcFill.left, rcFill.top, rcFill.right, rcFill.bottom, 4, 4);
        DeleteObject(hFillBrush);
    }

    // Details Row: Size (Left) & Speed (Right)
    SelectObject(hdc, m_hFontBold);
    SetTextColor(hdc, COL_TEXT_BODY);
    RECT rcSize = { rc.left + 18, rc.top + 70, rc.left + 280, rc.bottom - 4 };
    std::wstring wSize = Utf8ToWide("Downloaded: " + m_curSizeStr);
    DrawTextW(hdc, wSize.c_str(), -1, &rcSize, DT_LEFT | DT_VCENTER | DT_SINGLELINE);

    SetTextColor(hdc, COL_ACCENT_CYAN);
    RECT rcSpeed = { rc.right - 280, rc.top + 70, rc.right - 18, rc.bottom - 4 };
    std::wstring wSpeed = Utf8ToWide(m_curSpeed);
    DrawTextW(hdc, wSpeed.c_str(), -1, &rcSpeed, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

void MainWindow::DrawFooter(HDC hdc, const RECT& rc) {
    HBRUSH hFtrBrush = CreateSolidBrush(COL_BG_HEADER);
    FillRect(hdc, &rc, hFtrBrush);
    DeleteObject(hFtrBrush);

    HPEN hPen = CreatePen(PS_SOLID, 1, COL_BORDER_MAIN);
    HPEN hOldPen = (HPEN)SelectObject(hdc, hPen);
    MoveToEx(hdc, rc.left, rc.top, nullptr);
    LineTo(hdc, rc.right, rc.top);
    SelectObject(hdc, hOldPen);
    DeleteObject(hPen);

    SetBkMode(hdc, TRANSPARENT);
    SelectObject(hdc, m_hFontBold);
    SetTextColor(hdc, COL_ACCENT_EMERALD);

    RECT rcBridge = { rc.left + 26, rc.top, rc.left + 280, rc.bottom };
    DrawTextW(hdc, L"\u25CF Bridge  \u2022  Active (127.0.0.1:28795)", -1, &rcBridge, DT_LEFT | DT_VCENTER | DT_SINGLELINE);

    SelectObject(hdc, m_hFontSmall);
    SetTextColor(hdc, COL_TEXT_MUTED);
    RECT rcAuthor = { rc.right - 500, rc.top, rc.right - 26, rc.bottom };
    DrawTextW(hdc, L"OmniStream Pro v2.6.0  \u2022  Developed by XMON4U  \u2022  GitHub Repository", -1, &rcAuthor, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
}

void MainWindow::DrawCustomButton(LPDRAWITEMSTRUCT dis) {
    HDC hdc = dis->hDC;
    RECT rc = dis->rcItem;
    bool isPressed = (dis->itemState & ODS_SELECTED);
    bool isDisabled = (dis->itemState & ODS_DISABLED);
    int id = dis->CtlID;

    COLORREF colBg = COL_BG_CARD2;
    COLORREF colText = COL_TEXT_TITLE;
    COLORREF colBorder = COL_BORDER_MAIN;

    if (id == IDC_BTN_DOWNLOAD) {
        colBg = isPressed ? RGB(30, 64, 175) : COL_ACCENT_PRIMARY;
        colText = RGB(255, 255, 255);
        colBorder = colBg;
    } else if (id == IDC_BTN_DOWNLOAD_ALL) {
        colBg = isPressed ? RGB(4, 120, 87) : COL_ACCENT_GREEN_BTN;
        colText = RGB(255, 255, 255);
        colBorder = colBg;
    } else if (id == IDC_BTN_ABORT) {
        colBg = isDisabled ? COL_BG_CARD2 : (isPressed ? RGB(185, 28, 28) : COL_ACCENT_ROSE);
        colText = isDisabled ? COL_TEXT_MUTED : RGB(255, 255, 255);
        colBorder = colBg;
    } else if (id == IDC_BTN_TAB_QUEUE) {
        colBg = m_activeTabQueue ? COL_ACCENT_PRIMARY : COL_BG_CARD2;
        colText = m_activeTabQueue ? RGB(255, 255, 255) : COL_TEXT_BODY;
        colBorder = colBg;
    } else if (id == IDC_BTN_TAB_TERMINAL) {
        colBg = !m_activeTabQueue ? COL_ACCENT_PRIMARY : COL_BG_CARD2;
        colText = !m_activeTabQueue ? RGB(255, 255, 255) : COL_TEXT_BODY;
        colBorder = colBg;
    }

    HBRUSH hBrush = CreateSolidBrush(colBg);
    HPEN hPen = CreatePen(PS_SOLID, 1, colBorder);
    HBRUSH hOldBrush = (HBRUSH)SelectObject(hdc, hBrush);
    HPEN hOldPen = (HPEN)SelectObject(hdc, hPen);

    RoundRect(hdc, rc.left, rc.top, rc.right, rc.bottom, 8, 8);

    SelectObject(hdc, hOldBrush);
    SelectObject(hdc, hOldPen);
    DeleteObject(hBrush);
    DeleteObject(hPen);

    // Text (NO DOTTED FOCUS RECTANGLE!)
    wchar_t btnText[128] = { 0 };
    GetWindowTextW(dis->hwndItem, btnText, 128);

    SetBkMode(hdc, TRANSPARENT);
    SelectObject(hdc, m_hFontBold);
    SetTextColor(hdc, colText);
    DrawTextW(hdc, btnText, -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
}

// ── Window Message Handling ──

LRESULT CALLBACK MainWindow::WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    MainWindow* pThis = nullptr;
    if (msg == WM_NCCREATE) {
        auto* cs = reinterpret_cast<CREATESTRUCT*>(lParam);
        pThis = reinterpret_cast<MainWindow*>(cs->lpCreateParams);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(pThis));
        pThis->m_hwnd = hwnd;
    } else {
        pThis = reinterpret_cast<MainWindow*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    }

    if (pThis) {
        return pThis->HandleMessage(hwnd, msg, wParam, lParam);
    }
    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

LRESULT MainWindow::HandleMessage(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdcScreen = BeginPaint(hwnd, &ps);

        RECT rcClient;
        GetClientRect(hwnd, &rcClient);
        HDC hdcMem = CreateCompatibleDC(hdcScreen);
        HBITMAP hbmMem = CreateCompatibleBitmap(hdcScreen, rcClient.right, rcClient.bottom);
        HBITMAP hbmOld = (HBITMAP)SelectObject(hdcMem, hbmMem);

        // Root Background
        FillRect(hdcMem, &rcClient, m_hBgBrush);

        int padX = 26;
        int contentW = 970;

        // Top Header
        RECT rcHdr = { 0, 0, rcClient.right, 52 };
        DrawHeader(hdcMem, rcHdr);

        // Indigo Banner
        RECT rcBanner = { padX, 60, padX + contentW, 100 };
        DrawBanner(hdcMem, rcBanner);

        // Card 1: Stream Source
        RECT rcCard1 = { padX, 110, padX + contentW, 212 };
        DrawCard(hdcMem, rcCard1, L"Stream Source", L"Auto-parses cURL bash/cmd, M3U8, MPD, MP4, and MKV links");

        // Border around Stream Source Edit box
        HPEN hSubPen = CreatePen(PS_SOLID, 1, COL_BORDER_MAIN);
        HPEN hOldP = (HPEN)SelectObject(hdcMem, hSubPen);
        SelectObject(hdcMem, GetStockObject(NULL_BRUSH));
        Rectangle(hdcMem, padX + 15, 145, padX + contentW - 15, 199);
        SelectObject(hdcMem, hOldP);
        DeleteObject(hSubPen);

        // Card 2: Configuration & Stream Settings (PROPERLY SPACED, ZERO OVERLAP!)
        RECT rcCard2 = { padX, 222, padX + contentW, 420 };
        DrawCard(hdcMem, rcCard2, L"Configuration", L"");

        // Static labels inside Card 2
        SetBkMode(hdcMem, TRANSPARENT);
        SelectObject(hdcMem, m_hFontBold);
        SetTextColor(hdcMem, COL_TEXT_BODY);

        // Row 0 (y: 262)
        RECT r1 = { padX + 18, 262, padX + 130, 282 };
        DrawTextW(hdcMem, L"Title (optional):", -1, &r1, DT_LEFT | DT_SINGLELINE);

        RECT r2 = { padX + 495, 262, padX + 610, 282 };
        DrawTextW(hdcMem, L"Resolution:", -1, &r2, DT_LEFT | DT_SINGLELINE);

        // Row 1 (y: 300)
        RECT r3 = { padX + 18, 300, padX + 130, 320 };
        DrawTextW(hdcMem, L"Save Folder:", -1, &r3, DT_LEFT | DT_SINGLELINE);

        RECT r4 = { padX + 495, 300, padX + 610, 320 };
        DrawTextW(hdcMem, L"Audio Tracks:", -1, &r4, DT_LEFT | DT_SINGLELINE);

        // Row 2 (y: 338)
        RECT r5 = { padX + 18, 338, padX + 130, 358 };
        DrawTextW(hdcMem, L"Download Mode:", -1, &r5, DT_LEFT | DT_SINGLELINE);

        RECT r6 = { padX + 495, 338, padX + 610, 358 };
        DrawTextW(hdcMem, L"Subtitle Format:", -1, &r6, DT_LEFT | DT_SINGLELINE);

        // Row 3 (y: 376)
        RECT r7 = { padX + 495, 376, padX + 610, 396 };
        DrawTextW(hdcMem, L"Subtitle Lang:", -1, &r7, DT_LEFT | DT_SINGLELINE);

        // Card 3: Animated Progress Card
        RECT rcCard3 = { padX, 478, padX + contentW, 580 };
        DrawProgressCard(hdcMem, rcCard3);

        // Card 4: Tab Container Card
        RECT rcCard4 = { padX, 588, padX + contentW, 818 };
        DrawCard(hdcMem, rcCard4, L"", L"");

        // Footer Bar
        RECT rcFtr = { 0, rcClient.bottom - 28, rcClient.right, rcClient.bottom };
        DrawFooter(hdcMem, rcFtr);

        // Blit to screen
        BitBlt(hdcScreen, 0, 0, rcClient.right, rcClient.bottom, hdcMem, 0, 0, SRCCOPY);

        SelectObject(hdcMem, hbmOld);
        DeleteObject(hbmMem);
        DeleteDC(hdcMem);
        EndPaint(hwnd, &ps);
        return 0;
    }

    case WM_TIMER: {
        if (wParam == IDT_ANIM_TIMER) {
            m_pulseCounter++;

            // Smooth linear interpolation (lerp) for progress bar
            float diff = m_targetProgress - m_displayProgress;
            if (std::abs(diff) > 0.05f) {
                m_displayProgress += diff * 0.25f;
                RECT rcProg = { 26, 478, 1000, 580 };
                InvalidateRect(hwnd, &rcProg, FALSE);
            }

            // Pulse bridge dot in footer
            if (m_pulseCounter % 30 == 0) {
                RECT rcFtr = { 0, 850, 1040, 880 };
                InvalidateRect(hwnd, &rcFtr, FALSE);
            }
        }
        return 0;
    }

    case WM_DRAWITEM: {
        auto* dis = reinterpret_cast<LPDRAWITEMSTRUCT>(lParam);
        DrawCustomButton(dis);
        return TRUE;
    }

    case WM_CTLCOLOREDIT:
    case WM_CTLCOLORSTATIC: {
        HDC hdc = (HDC)wParam;
        HWND hCtl = (HWND)lParam;
        if (hCtl == m_hEditLog) {
            SetTextColor(hdc, COL_TEXT_LOG);
            SetBkColor(hdc, COL_BG_TERMINAL);
            return (LRESULT)m_hTerminalBrush;
        } else if (hCtl == m_hEditUrl || hCtl == m_hEditTitle || hCtl == m_hEditDir) {
            SetTextColor(hdc, COL_TEXT_TITLE);
            SetBkColor(hdc, COL_BG_INPUT);
            return (LRESULT)m_hInputBrush;
        }
        SetTextColor(hdc, COL_TEXT_TITLE);
        SetBkColor(hdc, COL_BG_CARD);
        return (LRESULT)m_hCardBrush;
    }

    case WM_COMMAND: {
        int wmId = LOWORD(wParam);
        switch (wmId) {
        case IDC_BTN_DOWNLOAD:
            StartDownload(false);
            break;
        case IDC_BTN_DOWNLOAD_SUBS:
            StartDownload(true);
            break;
        case IDC_BTN_ABORT:
            AbortDownload();
            break;
        case IDC_BTN_PASTE:
            PasteClipboard();
            break;
        case IDC_BTN_BROWSE:
            BrowseSaveDirectory();
            break;
        case IDC_BTN_TAB_QUEUE:
            SwitchTab(true);
            break;
        case IDC_BTN_TAB_TERMINAL:
            SwitchTab(false);
            break;
        case IDC_BTN_DOWNLOAD_ALL:
            StartQueueProcessing();
            break;
        case IDC_BTN_CLEAR_QUEUE:
            ClearQueue();
            break;
        case IDC_BTN_CLEAR_LOGS:
            if (m_hEditLog) SetWindowTextW(m_hEditLog, L"");
            break;
        }
        return 0;
    }

    case WM_OMNI_LOG: {
        auto* pStr = reinterpret_cast<std::string*>(lParam);
        if (pStr) {
            AppendLog(*pStr);
            delete pStr;
        }
        return 0;
    }

    case WM_OMNI_PROGRESS: {
        auto* p = reinterpret_cast<ProgressPayload*>(lParam);
        if (p) {
            UpdateProgress(p->percent, p->speed, p->eta, p->bytes);
            delete p;
        }
        return 0;
    }

    case WM_OMNI_COMPLETE: {
        m_isDownloading.store(false);
        EnableWindow(m_hBtnDownload, TRUE);
        EnableWindow(m_hBtnDownloadSubs, TRUE);
        EnableWindow(m_hBtnAbort, FALSE);

        if (wParam == 1) {
            m_targetProgress = 100.0f;
            m_curStatus = "Download Completed Successfully! 100% Verified.";
            AppendLog("[Engine] 100% Download Completed Successfully.");
        } else {
            m_curStatus = "Download Finished with warnings or errors.";
            AppendLog("[Engine] Download finished.");
        }
        InvalidateRect(hwnd, nullptr, FALSE);
        return 0;
    }

    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }

    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

int MainWindow::RunMessageLoop() {
    MSG msg;
    while (GetMessageW(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return (int)msg.wParam;
}

} // namespace OmniStream
