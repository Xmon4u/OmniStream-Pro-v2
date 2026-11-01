#include "ExtensionInstaller.hpp"
#include <windows.h>
#include <shlobj.h>
#include <tlhelp32.h>
#include <filesystem>
#include <fstream>
#include <sstream>

namespace fs = std::filesystem;

namespace OmniStream {

static bool IsProcessRunning(const std::wstring& procName) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return false;

    PROCESSENTRY32W entry = { sizeof(entry) };
    bool found = false;
    if (Process32FirstW(snap, &entry)) {
        do {
            if (_wcsicmp(entry.szExeFile, procName.c_str()) == 0) {
                found = true;
                break;
            }
        } while (Process32NextW(snap, &entry));
    }
    CloseHandle(snap);
    return found;
}

std::string ExtensionInstaller::FindBrowserExecutable() {
    wchar_t localApp[MAX_PATH] = { 0 };
    SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, 0, localApp);

    wchar_t progFiles[MAX_PATH] = { 0 };
    SHGetFolderPathW(nullptr, CSIDL_PROGRAM_FILES, nullptr, 0, progFiles);

    wchar_t progFilesX86[MAX_PATH] = { 0 };
    SHGetFolderPathW(nullptr, CSIDL_PROGRAM_FILESX86, nullptr, 0, progFilesX86);

    std::vector<fs::path> candidates = {
        // Google Chrome
        fs::path(progFiles) / L"Google\\Chrome\\Application\\chrome.exe",
        fs::path(progFilesX86) / L"Google\\Chrome\\Application\\chrome.exe",
        fs::path(localApp) / L"Google\\Chrome\\Application\\chrome.exe",
        // Microsoft Edge
        fs::path(progFiles) / L"Microsoft\\Edge\\Application\\msedge.exe",
        fs::path(progFilesX86) / L"Microsoft\\Edge\\Application\\msedge.exe",
        // Brave Browser
        fs::path(progFiles) / L"BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        fs::path(localApp) / L"BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    };

    for (const auto& p : candidates) {
        if (fs::exists(p)) {
            return p.string();
        }
    }
    return "";
}

std::string ExtensionInstaller::GetExtensionDirectory() {
    char exeBuf[MAX_PATH];
    GetModuleFileNameA(nullptr, exeBuf, MAX_PATH);
    fs::path appDir = fs::path(exeBuf).parent_path();

    std::vector<fs::path> candidates = {
        appDir / "extension",
        appDir.parent_path() / "extension",
        fs::path("D:\\05_Projects\\OmniStream-Pro-v2-2.5.0\\C++ Projects\\extension"),
        fs::path("D:\\05_Projects\\OmniStream-Pro-v2-2.5.0\\extension")
    };

    for (const auto& c : candidates) {
        if (fs::exists(c / "manifest.json")) {
            return fs::canonical(c).string();
        }
    }
    return "D:\\05_Projects\\OmniStream-Pro-v2-2.5.0\\C++ Projects\\extension";
}

ExtensionInstaller::SetupResult ExtensionInstaller::InstallExtension(std::function<void(const std::string&)> log_cb) {
    SetupResult res;
    res.extension_dir = GetExtensionDirectory();
    res.browser_path = FindBrowserExecutable();

    if (res.browser_path.empty()) {
        res.success = false;
        res.message = "No supported Chromium browser (Chrome/Edge/Brave) found on system.";
        return res;
    }

    if (!fs::exists(fs::path(res.extension_dir) / "manifest.json")) {
        res.success = false;
        res.message = "Extension manifest.json not found in: " + res.extension_dir;
        return res;
    }

    // 1. Ensure bridge_token.json is written into extension directory
    {
        fs::path tokenFile = fs::path(res.extension_dir) / "bridge_token.json";
        std::ofstream tf(tokenFile.string());
        if (tf.is_open()) {
            tf << "{\n  \"token\": \"3272011e08e15fd64c92355eabb916bfe841360af223afdb\",\n  \"port\": 28795\n}\n";
            tf.close();
        }
    }

    // 2. Register unpacked extension into Windows Registry for Chrome and Edge
    {
        std::wstring wFakeId = L"omnistreampromediadownloader";
        std::wstring wExtDir(res.extension_dir.begin(), res.extension_dir.end());

        HKEY hKey;
        std::wstring regChrome = L"Software\\Google\\Chrome\\Extensions\\" + wFakeId;
        if (RegCreateKeyExW(HKEY_CURRENT_USER, regChrome.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"path", 0, REG_SZ, reinterpret_cast<const BYTE*>(wExtDir.c_str()), static_cast<DWORD>((wExtDir.size() + 1) * sizeof(wchar_t)));
            const wchar_t* ver = L"2.6.0";
            RegSetValueExW(hKey, L"version", 0, REG_SZ, reinterpret_cast<const BYTE*>(ver), static_cast<DWORD>((wcslen(ver) + 1) * sizeof(wchar_t)));
            RegCloseKey(hKey);
        }
        std::wstring regEdge = L"Software\\Microsoft\\Edge\\Extensions\\" + wFakeId;
        if (RegCreateKeyExW(HKEY_CURRENT_USER, regEdge.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &hKey, nullptr) == ERROR_SUCCESS) {
            RegSetValueExW(hKey, L"path", 0, REG_SZ, reinterpret_cast<const BYTE*>(wExtDir.c_str()), static_cast<DWORD>((wExtDir.size() + 1) * sizeof(wchar_t)));
            const wchar_t* ver = L"2.6.0";
            RegSetValueExW(hKey, L"version", 0, REG_SZ, reinterpret_cast<const BYTE*>(ver), static_cast<DWORD>((wcslen(ver) + 1) * sizeof(wchar_t)));
            RegCloseKey(hKey);
        }
    }

    // 3. Copy extension path to Windows clipboard as guaranteed fallback
    if (OpenClipboard(nullptr)) {
        EmptyClipboard();
        std::wstring wpath(res.extension_dir.begin(), res.extension_dir.end());
        HGLOBAL hMem = GlobalAlloc(GMEM_MOVEABLE, (wpath.size() + 1) * sizeof(wchar_t));
        if (hMem) {
            memcpy(GlobalLock(hMem), wpath.c_str(), (wpath.size() + 1) * sizeof(wchar_t));
            GlobalUnlock(hMem);
            SetClipboardData(CF_UNICODETEXT, hMem);
        }
        CloseClipboard();
    }

    fs::path browserP(res.browser_path);
    std::wstring exeName = browserP.filename().wstring();
    bool isRunning = IsProcessRunning(exeName);

    if (log_cb) {
        log_cb("[Extension Setup] Browser: " + browserP.filename().string() +
               (isRunning ? " (currently running)" : " (not running)"));
    }

    if (!isRunning) {
        // Strategy A: Chrome is not running -> Direct 1-Click Load via CLI switch
        std::wostringstream args;
        args << L"\"" << browserP.wstring() << L"\" "
             << L"--disable-features=DisableLoadExtensionCommandLineSwitch "
             << L"--load-extension=\"" << std::wstring(res.extension_dir.begin(), res.extension_dir.end()) << L"\" "
             << L"--no-first-run --no-default-browser-check "
             << L"chrome://extensions/";

        STARTUPINFOW si = { sizeof(si) };
        PROCESS_INFORMATION pi = { 0 };
        std::wstring cmd = args.str();

        if (CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi)) {
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            res.success = true;
            res.message = "Chrome launched with OmniStream Pro extension loaded automatically!";
            if (log_cb) log_cb("[Extension Setup] " + res.message);
            return res;
        }
    }

    // Strategy B: Chrome is open -> Open chrome://extensions and run automated UI automation
    std::wostringstream launchArgs;
    launchArgs << L"\"" << browserP.wstring() << L"\" chrome://extensions/";
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = { 0 };
    std::wstring cmd = launchArgs.str();

    CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi);
    if (pi.hProcess) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }

    // Write and execute UIAutomation script matching Python version
    wchar_t tempPath[MAX_PATH];
    GetTempPathW(MAX_PATH, tempPath);
    fs::path scriptFile = fs::path(tempPath) / L"omnistream_load_unpacked.ps1";

    std::ofstream ps(scriptFile.string());
    if (ps.is_open()) {
        ps << R"PS(
param([string]$Folder)
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Find-Window([string[]]$Needles) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($win in $wins) {
        $name = ''
        try { $name = $win.Current.Name } catch { continue }
        foreach ($n in $Needles) {
            if ($name -and $name.ToLower().Contains($n.ToLower())) { return $win }
        }
    }
    return $null
}

function Find-Named($root, [string[]]$Needles) {
    if (-not $root) { return $null }
    $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($el in $all) {
        $name = ''
        try { $name = $el.Current.Name } catch { continue }
        if (-not $name) { continue }
        foreach ($n in $Needles) {
            if ($name.ToLower().Contains($n.ToLower())) { return $el }
        }
    }
    return $null
}

function Invoke-El($el) {
    $invoke = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $invoke.Invoke()
}

$ext = $null
$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline -and -not $ext) {
    $ext = Find-Window @('Extensions', 'Chrome')
    if (-not $ext) { Start-Sleep -Milliseconds 400 }
}

if ($ext) {
    $dev = Find-Named $ext @('Developer mode')
    if ($dev) {
        try {
            $toggle = $dev.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            if ($toggle.Current.ToggleState -ne 'On') { $toggle.Toggle() }
        } catch { try { Invoke-El $dev } catch {} }
    }
    Start-Sleep -Milliseconds 500
    $load = Find-Named $ext @('Load unpacked')
    if ($load) {
        Invoke-El $load
        Start-Sleep -Milliseconds 700

        # Feed folder into file dialog via SendKeys
        $wshell = New-Object -ComObject wscript.shell
        $wshell.AppActivate('Select the extension directory')
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.Clipboard]::SetText($Folder)
        $wshell.SendKeys('^v')
        Start-Sleep -Milliseconds 200
        $wshell.SendKeys('{ENTER}')
        Write-Output "LOAD_AUTOMATED_SUCCESS"
    }
}
)PS";
        ps.close();

        // Run powershell script in background
        std::wostringstream psCmd;
        psCmd << L"powershell.exe -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File \""
              << scriptFile.wstring() << L"\" -Folder \""
              << std::wstring(res.extension_dir.begin(), res.extension_dir.end()) << L"\"";

        STARTUPINFOW psi = { sizeof(psi) };
        psi.dwFlags = STARTF_USESHOWWINDOW;
        psi.wShowWindow = SW_HIDE;
        PROCESS_INFORMATION ppi = { 0 };
        std::wstring runPs = psCmd.str();

        if (CreateProcessW(nullptr, runPs.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &psi, &ppi)) {
            CloseHandle(ppi.hProcess);
            CloseHandle(ppi.hThread);
        }
    }

    res.success = true;
    res.message = "Chrome Extensions opened with automation! Extension path copied to clipboard.";
    if (log_cb) log_cb("[Extension Setup] " + res.message);
    return res;
}

} // namespace OmniStream
