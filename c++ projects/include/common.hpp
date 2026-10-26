#pragma once

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <bcrypt.h>

#include <iostream>
#include <string>
#include <string_view>
#include <vector>
#include <map>
#include <memory>
#include <thread>
#include <mutex>
#include <atomic>
#include <condition_variable>
#include <functional>
#include <filesystem>
#include <chrono>
#include <sstream>
#include <iomanip>
#include <regex>
#include <cstdint>
#include <algorithm>

namespace OmniStream {

constexpr const char* VERSION = "2.6.0";
constexpr int BRIDGE_PORT = 28795;
constexpr const char* DEFAULT_USER_AGENT =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

// Terminal ANSI styling
namespace Color {
    inline const char* Reset   = "\033[0m";
    inline const char* Bold    = "\033[1m";
    inline const char* Dim     = "\033[2m";
    inline const char* Cyan    = "\033[36m";
    inline const char* Green   = "\033[32m";
    inline const char* Yellow  = "\033[33m";
    inline const char* Red     = "\033[31m";
    inline const char* Magenta = "\033[35m";
    inline const char* Blue    = "\033[34m";
}

class Logger {
public:
    static void Info(const std::string& msg) {
        std::lock_guard<std::mutex> lock(s_mutex);
        std::cout << Color::Cyan << "[INFO] " << Color::Reset << msg << std::endl;
    }
    static void Success(const std::string& msg) {
        std::lock_guard<std::mutex> lock(s_mutex);
        std::cout << Color::Green << "[SUCCESS] " << Color::Reset << msg << std::endl;
    }
    static void Warn(const std::string& msg) {
        std::lock_guard<std::mutex> lock(s_mutex);
        std::cout << Color::Yellow << "[WARN] " << Color::Reset << msg << std::endl;
    }
    static void Error(const std::string& msg) {
        std::lock_guard<std::mutex> lock(s_mutex);
        std::cerr << Color::Red << "[ERROR] " << Color::Reset << msg << std::endl;
    }
    static void Status(const std::string& msg) {
        std::lock_guard<std::mutex> lock(s_mutex);
        std::cout << Color::Magenta << "  ▶ " << Color::Reset << msg << std::endl;
    }

private:
    inline static std::mutex s_mutex;
};

// Utilities for UTF-8 and Wide string conversions on Windows
inline std::wstring Utf8ToWide(std::string_view utf8) {
    if (utf8.empty()) return L"";
    int size = MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), nullptr, 0);
    std::wstring result(size, 0);
    MultiByteToWideChar(CP_UTF8, 0, utf8.data(), (int)utf8.size(), &result[0], size);
    return result;
}

inline std::string WideToUtf8(std::wstring_view wide) {
    if (wide.empty()) return "";
    int size = WideCharToMultiByte(CP_UTF8, 0, wide.data(), (int)wide.size(), nullptr, 0, nullptr, nullptr);
    std::string result(size, 0);
    WideCharToMultiByte(CP_UTF8, 0, wide.data(), (int)wide.size(), &result[0], size, nullptr, nullptr);
    return result;
}

inline std::string FormatBytes(uint64_t bytes) {
    const char* units[] = {"B", "KB", "MB", "GB", "TB"};
    int idx = 0;
    double d = static_cast<double>(bytes);
    while (d >= 1024.0 && idx < 4) {
        d /= 1024.0;
        idx++;
    }
    std::ostringstream ss;
    ss << std::fixed << std::setprecision(idx == 0 ? 0 : 2) << d << " " << units[idx];
    return ss.str();
}

} // namespace OmniStream
