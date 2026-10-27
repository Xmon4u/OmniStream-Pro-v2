#include "muxer.hpp"
#include <fstream>

namespace OmniStream {

bool Muxer::FindFFmpeg(std::string& outPath) {
    // 1. Check application directory where executable lives
    wchar_t modPath[MAX_PATH];
    if (GetModuleFileNameW(NULL, modPath, MAX_PATH) > 0) {
        std::filesystem::path appDir = std::filesystem::path(modPath).parent_path();
        if (std::filesystem::exists(appDir / "ffmpeg.exe")) {
            outPath = (appDir / "ffmpeg.exe").string();
            return true;
        }
        if (std::filesystem::exists(appDir / "bin" / "ffmpeg.exe")) {
            outPath = (appDir / "bin" / "ffmpeg.exe").string();
            return true;
        }
    }

    // 2. Check local relative bin/
    const char* candidates[] = {
        "bin\\ffmpeg.exe",
        "..\\desktop\\bin\\ffmpeg.exe",
        "desktop\\bin\\ffmpeg.exe",
        "ffmpeg.exe"
    };
    for (const char* path : candidates) {
        if (std::filesystem::exists(path)) {
            outPath = std::filesystem::absolute(path).string();
            return true;
        }
    }

    // 3. Check PATH via SearchPathW
    wchar_t buffer[MAX_PATH];
    DWORD res = SearchPathW(nullptr, L"ffmpeg.exe", nullptr, MAX_PATH, buffer, nullptr);
    if (res > 0 && res < MAX_PATH) {
        outPath = WideToUtf8(buffer);
        return true;
    }

    return false;
}

bool Muxer::ConcatenateSegments(
    const std::vector<std::string>& segmentFiles,
    const std::string& outputFile,
    const std::string& initSegmentFile
) {
    std::filesystem::path outP(outputFile);
    if (outP.has_parent_path()) {
        std::filesystem::create_directories(outP.parent_path());
    }

    std::ofstream out(outputFile, std::ios::binary);
    if (!out.is_open()) return false;

    char buffer[65536];

    // Write init segment if present (fMP4)
    if (!initSegmentFile.empty() && std::filesystem::exists(initSegmentFile)) {
        std::ifstream initIn(initSegmentFile, std::ios::binary);
        while (initIn.read(buffer, sizeof(buffer)) || initIn.gcount() > 0) {
            out.write(buffer, initIn.gcount());
        }
    }

    // Write each segment
    for (const auto& file : segmentFiles) {
        if (!std::filesystem::exists(file)) continue;
        std::ifstream segIn(file, std::ios::binary);
        while (segIn.read(buffer, sizeof(buffer)) || segIn.gcount() > 0) {
            out.write(buffer, segIn.gcount());
        }
    }

    return out.good();
}

bool Muxer::MuxTracks(
    const std::string& videoFile,
    const std::vector<std::pair<std::string, std::string>>& audioFilesWithLang,
    const std::vector<std::pair<std::string, std::string>>& subtitleFilesWithLang,
    const std::string& outputFile
) {
    std::string ffmpegPath;
    if (!FindFFmpeg(ffmpegPath)) {
        Logger::Warn("FFmpeg not found in PATH or bin/. Keeping direct track file: " + videoFile);
        return false;
    }

    std::ostringstream cmd;
    cmd << "\"" << ffmpegPath << "\" -y ";
    cmd << "-i \"" << videoFile << "\" ";

    for (const auto& [audioFile, lang] : audioFilesWithLang) {
        cmd << "-i \"" << audioFile << "\" ";
    }
    for (const auto& [subFile, lang] : subtitleFilesWithLang) {
        cmd << "-i \"" << subFile << "\" ";
    }

    cmd << "-map 0:v? ";
    int inputIdx = 1;
    for (size_t i = 0; i < audioFilesWithLang.size(); ++i, ++inputIdx) {
        cmd << "-map " << inputIdx << ":a? ";
    }
    for (size_t i = 0; i < subtitleFilesWithLang.size(); ++i, ++inputIdx) {
        cmd << "-map " << inputIdx << ":s? ";
    }

    // Set audio metadata language
    for (size_t i = 0; i < audioFilesWithLang.size(); ++i) {
        if (!audioFilesWithLang[i].second.empty()) {
            cmd << "-metadata:s:a:" << i << " language=" << audioFilesWithLang[i].second << " ";
        }
    }

    // Set subtitle metadata language
    for (size_t i = 0; i < subtitleFilesWithLang.size(); ++i) {
        if (!subtitleFilesWithLang[i].second.empty()) {
            cmd << "-metadata:s:s:" << i << " language=" << subtitleFilesWithLang[i].second << " ";
        }
    }

    cmd << "-c copy \"" << outputFile << "\"";

    std::wstring wCmd = Utf8ToWide(cmd.str());

    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi = { 0 };
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    std::vector<wchar_t> cmdBuf(wCmd.begin(), wCmd.end());
    cmdBuf.push_back(L'\0');

    BOOL ok = CreateProcessW(
        nullptr,
        cmdBuf.data(),
        nullptr,
        nullptr,
        FALSE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &si,
        &pi
    );

    if (!ok) return false;

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode = 0;
    GetExitCodeProcess(pi.hProcess, &exitCode);

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    return (exitCode == 0 && std::filesystem::exists(outputFile));
}

} // namespace OmniStream
