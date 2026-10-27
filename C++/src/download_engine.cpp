#include "download_engine.hpp"
#include "netflix_resolver.hpp"
#include <fstream>
#include <queue>

namespace OmniStream {

static std::string FindNM3U8Binary() {
    // 1. Current working directory
    std::filesystem::path curDir = std::filesystem::current_path();
    std::filesystem::path p1 = curDir / "N_m3u8DL-RE.exe";
    if (std::filesystem::exists(p1)) return p1.string();

    // 2. Executable's directory
    wchar_t exePath[MAX_PATH];
    if (GetModuleFileNameW(NULL, exePath, MAX_PATH)) {
        std::filesystem::path appDir = std::filesystem::path(exePath).parent_path();
        std::filesystem::path p2 = appDir / "N_m3u8DL-RE.exe";
        if (std::filesystem::exists(p2)) return p2.string();
    }

    // 3. LocalAppData folder
    const char* localApp = std::getenv("LOCALAPPDATA");
    if (localApp) {
        std::filesystem::path p3 = std::filesystem::path(localApp) / "OmniStreamPro" / "bin" / "N_m3u8DL-RE.exe";
        if (std::filesystem::exists(p3)) return p3.string();
        std::filesystem::path p4 = std::filesystem::path(localApp) / "OmniStreamPro" / "N_m3u8DL-RE.exe";
        if (std::filesystem::exists(p4)) return p4.string();
    }

    return "";
}

DownloadEngine::DownloadEngine() = default;
DownloadEngine::~DownloadEngine() {
    Abort();
}

void DownloadEngine::Abort() {
    m_aborted.store(true);
    std::lock_guard<std::mutex> lock(m_processMutex);
    if (m_hCurrentProcess != NULL) {
        TerminateProcess(m_hCurrentProcess, 1);
    }
}

bool DownloadEngine::Download(const DownloadOptions& options, std::string& outFinalFile) {
    m_aborted.store(false);

    auto log = [&](const std::string& msg) {
        if (options.onLog) options.onLog(msg);
        else Logger::Info(msg);
    };

    StreamInfo info = CurlParser::Parse(options.inputText);
    if (info.url.empty()) {
        log("No valid URL found in input.");
        return false;
    }

    // Determine save name based on active mode
    std::string baseName;
    if (options.mode == "netflix_rename" || options.mode == "imdb_rename" || options.mode == "tmdb_rename") {
        baseName = NetflixResolver::ResolveMediaRename(
            options.mode,
            options.inputText,
            options.saveName,
            options.netflixId,
            options.imdbId,
            options.tmdbId,
            log
        );
    }

    if (baseName.empty()) {
        baseName = options.saveName;
    }

    if (baseName.empty()) {
        std::string nfId = NetflixResolver::ExtractNetflixId(options.inputText);
        if (!nfId.empty()) {
            baseName = NetflixResolver::ResolveOnlineTitle(nfId);
        } else {
            // Extract from URL filename
            size_t lastSlash = info.url.find_last_of('/');
            size_t qMark = info.url.find('?');
            if (lastSlash != std::string::npos) {
                baseName = info.url.substr(lastSlash + 1, qMark == std::string::npos ? qMark : qMark - lastSlash - 1);
            }
            if (baseName.empty()) baseName = "OmniStream_Capture";
        }
    }

    baseName = NetflixResolver::SanitizeFilename(baseName);

    std::filesystem::path dirPath = options.saveDir.empty() ? "." : options.saveDir;
    std::filesystem::create_directories(dirPath);

    bool isStream = (info.url.find(".m3u8") != std::string::npos ||
                     info.url.find(".mpd") != std::string::npos ||
                     info.GetHeader("content-type").find("mpegurl") != std::string::npos);

    std::string ext = isStream ? ".mkv" : ".mp4";
    std::filesystem::path targetFile = dirPath / (baseName + ext);
    std::string safeTargetPath = NetflixResolver::GetNonConflictingPath(targetFile.string());

    log("Target: " + safeTargetPath);
    log("Mode: " + std::string(isStream ? "HLS/DASH Multi-Stream Downloader" : "Direct Media Stream Downloader"));

    bool success = false;
    if (isStream) {
        std::string nm3u8Binary = FindNM3U8Binary();
        if (!nm3u8Binary.empty()) {
            log("[Engine] Found N_m3u8DL-RE binary: " + nm3u8Binary);
            success = DownloadWithNM3U8(info, safeTargetPath, options, nm3u8Binary);
            if (!success && !m_aborted.load()) {
                log("[Engine] Notice: N_m3u8DL-RE completed with non-zero or failed. Falling back to native C++ HLS engine...");
                success = DownloadHlsStream(info, safeTargetPath, options);
            }
        } else {
            success = DownloadHlsStream(info, safeTargetPath, options);
        }
    } else {
        success = DownloadDirectStream(info, safeTargetPath, options);
    }

    if (success && !m_aborted.load()) {
        outFinalFile = safeTargetPath;
        log("Download successfully completed: " + safeTargetPath);
        return true;
    }

    if (m_aborted.load()) {
        log("Download aborted by user.");
    }
    return false;
}

bool DownloadEngine::DownloadDirectStream(const StreamInfo& info, const std::string& outputFile, const DownloadOptions& options) {
    HttpClient client(info.user_agent);
    auto startTime = std::chrono::steady_clock::now();

    auto progressCb = [&](uint64_t downloaded, uint64_t total) {
        if (m_aborted.load()) return;
        auto now = std::chrono::steady_clock::now();
        double elapsedSec = std::chrono::duration<double>(now - startTime).count();
        double speedBps = elapsedSec > 0 ? (downloaded / elapsedSec) : 0;
        std::string speedStr = FormatBytes((uint64_t)speedBps) + "/s";

        float pct = (total > 0) ? (static_cast<float>(downloaded) / total * 100.0f) : 0.0f;
        std::string etaStr = "--";
        if (speedBps > 0 && total > downloaded) {
            uint64_t remainingSec = static_cast<uint64_t>((total - downloaded) / speedBps);
            etaStr = std::to_string(remainingSec) + "s";
        }

        if (options.onProgress) {
            options.onProgress(pct, speedStr, etaStr, downloaded);
        }
    };

    return client.DownloadFile(info.url, outputFile, info.headers, progressCb);
}

bool DownloadEngine::DownloadTrackSegments(
    const HlsPlaylist& playlist,
    const StreamInfo& info,
    const std::string& tempDir,
    const std::string& trackName,
    std::vector<std::string>& outSegmentFiles,
    const DownloadOptions& options
) {
    if (playlist.segments.empty()) return false;

    // Cache encryption keys
    std::map<std::string, std::vector<uint8_t>> keyCache;
    HttpClient client(info.user_agent);

    for (const auto& seg : playlist.segments) {
        if (!seg.key.uri.empty() && keyCache.find(seg.key.uri) == keyCache.end()) {
            HttpResponse keyResp = client.Get(seg.key.uri, info.headers);
            if (keyResp.IsSuccess() && !keyResp.body.empty()) {
                keyCache[seg.key.uri] = keyResp.body;
            }
        }
    }

    std::filesystem::create_directories(tempDir);
    outSegmentFiles.resize(playlist.segments.size());

    // Thread-safe work queue
    std::queue<size_t> workQueue;
    for (size_t i = 0; i < playlist.segments.size(); ++i) {
        workQueue.push(i);
    }

    std::mutex queueMutex;
    std::atomic<uint64_t> totalDownloadedBytes{ 0 };
    std::atomic<size_t> completedSegments{ 0 };
    auto startTime = std::chrono::steady_clock::now();

    size_t numThreads = std::min<size_t>(options.threadCount, playlist.segments.size());
    if (numThreads < 1) numThreads = 1;

    std::vector<std::thread> workers;
    for (size_t t = 0; t < numThreads; ++t) {
        workers.emplace_back([&]() {
            HttpClient threadClient(info.user_agent);

            while (!m_aborted.load()) {
                size_t segIdx = 0;
                {
                    std::lock_guard<std::mutex> lock(queueMutex);
                    if (workQueue.empty()) break;
                    segIdx = workQueue.front();
                    workQueue.pop();
                }

                const auto& seg = playlist.segments[segIdx];
                std::string segFilePath = tempDir + "/seg_" + std::to_string(segIdx) + ".ts";

                HttpResponse resp = threadClient.Get(seg.url, info.headers);
                if (!resp.IsSuccess() || resp.body.empty()) {
                    continue; // Retry logic can be added here
                }

                std::vector<uint8_t> finalData = std::move(resp.body);

                // Handle AES-128 decryption if needed
                if (seg.key.method == "AES-128" && keyCache.count(seg.key.uri)) {
                    std::vector<uint8_t> iv = Crypto::HexToBytes(seg.key.ivHex);
                    if (iv.empty()) {
                        // Default IV is segment sequence number in big-endian (16 bytes)
                        iv.resize(16, 0);
                        uint64_t seq = segIdx;
                        for (int b = 15; b >= 8; --b) {
                            iv[b] = static_cast<uint8_t>(seq & 0xFF);
                            seq >>= 8;
                        }
                    }
                    std::vector<uint8_t> decrypted;
                    if (Crypto::DecryptAes128Cbc(finalData, keyCache[seg.key.uri], iv, decrypted)) {
                        finalData = std::move(decrypted);
                    }
                }

                // Write segment file
                std::ofstream out(segFilePath, std::ios::binary);
                if (out.is_open()) {
                    out.write(reinterpret_cast<const char*>(finalData.data()), finalData.size());
                    outSegmentFiles[segIdx] = segFilePath;
                }

                totalDownloadedBytes += finalData.size();
                size_t done = ++completedSegments;

                // Progress update
                auto now = std::chrono::steady_clock::now();
                double elapsed = std::chrono::duration<double>(now - startTime).count();
                double speed = elapsed > 0 ? (totalDownloadedBytes.load() / elapsed) : 0;
                std::string speedStr = FormatBytes((uint64_t)speed) + "/s";

                float pct = (playlist.segments.size() > 0)
                    ? (static_cast<float>(done) / playlist.segments.size() * 100.0f)
                    : 0.0f;

                std::string etaStr = "--";
                if (done > 0 && elapsed > 0) {
                    double timePerSeg = elapsed / done;
                    uint64_t remainingSec = static_cast<uint64_t>((playlist.segments.size() - done) * timePerSeg);
                    etaStr = std::to_string(remainingSec) + "s";
                }

                if (options.onProgress) {
                    options.onProgress(pct, speedStr, etaStr, totalDownloadedBytes.load());
                }
            }
        });
    }

    for (auto& th : workers) {
        if (th.joinable()) th.join();
    }

    return !m_aborted.load() && completedSegments.load() > 0;
}

bool DownloadEngine::DownloadHlsStream(const StreamInfo& info, const std::string& outputFile, const DownloadOptions& options) {
    HttpClient client(info.user_agent);

    if (options.onLog) options.onLog("Fetching Master Playlist: " + info.url);
    HttpResponse masterResp = client.Get(info.url, info.headers);
    if (!masterResp.IsSuccess()) {
        if (options.onLog) options.onLog("Failed to fetch master playlist: HTTP " + std::to_string(masterResp.statusCode));
        return false;
    }

    std::string masterContent = masterResp.Text();
    HlsPlaylist master = HlsParser::Parse(masterContent, info.url);

    std::string videoUrl = info.url;
    if (master.isMaster) {
        HlsTrack bestVideo = HlsParser::SelectBestVideoTrack(master, options.resolution);
        if (bestVideo.uri.empty()) {
            if (options.onLog) options.onLog("No valid video variant found in master playlist.");
            return false;
        }
        videoUrl = bestVideo.uri;
        if (options.onLog) options.onLog("Selected Stream Variant: " + bestVideo.name + " (" + bestVideo.resolution + ")");
    }

    // Fetch Variant Media Playlist
    HttpResponse variantResp = client.Get(videoUrl, info.headers);
    if (!variantResp.IsSuccess()) {
        if (options.onLog) options.onLog("Failed to fetch media playlist.");
        return false;
    }

    HlsPlaylist mediaPlaylist = HlsParser::Parse(variantResp.Text(), videoUrl);
    if (mediaPlaylist.segments.empty()) {
        if (options.onLog) options.onLog("No segments found in media playlist.");
        return false;
    }

    if (options.onLog) {
        options.onLog("Total Segments: " + std::to_string(mediaPlaylist.segments.size()) +
                      " | Concurrency: " + std::to_string(options.threadCount) + " threads");
    }

    std::string tempDir = outputFile + ".tmp_segments";
    std::vector<std::string> segmentFiles;

    bool downloaded = DownloadTrackSegments(mediaPlaylist, info, tempDir, "video", segmentFiles, options);
    if (!downloaded || m_aborted.load()) {
        std::filesystem::remove_all(tempDir);
        return false;
    }

    if (options.onLog) options.onLog("Muxing and assembling video segments...");

    // Stitched video file
    std::string stitchedVideo = tempDir + "/stitched_video.ts";
    Muxer::ConcatenateSegments(segmentFiles, stitchedVideo, mediaPlaylist.initSegmentUrl);

    // If FFmpeg is available, mux into lossless container; otherwise copy stitched file
    std::string ffmpegPath;
    if (Muxer::FindFFmpeg(ffmpegPath)) {
        if (options.onLog) options.onLog("FFmpeg detected (" + ffmpegPath + "). Lossless container packaging...");
        Muxer::MuxTracks(stitchedVideo, {}, {}, outputFile);
    } else {
        std::filesystem::copy_file(stitchedVideo, outputFile, std::filesystem::copy_options::overwrite_existing);
    }

    // Clean up temporary files
    try {
        std::filesystem::remove_all(tempDir);
    } catch (...) {}

    return std::filesystem::exists(outputFile);
}

bool DownloadEngine::DownloadWithNM3U8(
    const StreamInfo& info,
    const std::string& outputFile,
    const DownloadOptions& options,
    const std::string& nm3u8Path
) {
    std::filesystem::path outPath(outputFile);
    std::string saveDir = outPath.parent_path().string();
    std::string saveName = outPath.stem().string();

    std::string isolatedTemp = (outPath.parent_path() / (".omnistream_tmp_" + std::to_string(GetCurrentProcessId()) + "_" + std::to_string(std::chrono::system_clock::now().time_since_epoch().count()))).string();
    std::filesystem::create_directories(isolatedTemp);

    std::string videoSel = "best";
    if (options.resolution == "720p") videoSel = "res=\"720|1280\":for=best || best";
    else if (options.resolution == "480p") videoSel = "res=\"480|854\":for=best || best";
    else videoSel = "best";

    std::ostringstream cmd;
    cmd << "\"" << nm3u8Path << "\" \"" << info.url << "\" "
        << "--auto-select -sv " << videoSel << " -sa all -mt "
        << "--save-dir \"" << saveDir << "\" "
        << "--save-name \"" << saveName << "\" "
        << "--tmp-dir \"" << isolatedTemp << "\" "
        << "--thread-count 16 --download-retry-count 3 --http-request-timeout 15 "
        << "--disable-update-check --no-log --no-ansi-color ";

    std::string ffmpegPath;
    if (Muxer::FindFFmpeg(ffmpegPath)) {
        cmd << "-M format=mkv:muxer=ffmpeg --ffmpeg-binary-path \"" << ffmpegPath << "\" ";
    } else {
        cmd << "-M format=mkv ";
    }

    if (options.includeSubtitles) {
        cmd << "--sub-format SRT --auto-subtitle-fix -ss all ";
    }

    if (!info.referer.empty()) {
        cmd << "-H \"Referer: " << info.referer << "\" ";
    }
    if (!info.origin.empty()) {
        cmd << "-H \"Origin: " << info.origin << "\" ";
    }
    if (!info.user_agent.empty()) {
        cmd << "-H \"User-Agent: " << info.user_agent << "\" ";
    }
    if (!info.cookie.empty()) {
        cmd << "-H \"Cookie: " << info.cookie << "\" ";
    }

    // Add custom request headers
    for (const auto& [k, v] : info.headers) {
        std::string lo = k;
        std::transform(lo.begin(), lo.end(), lo.begin(), ::tolower);
        if (lo != "referer" && lo != "origin" && lo != "user-agent" && lo != "cookie" &&
            lo != "host" && lo != "connection" && lo != "content-length" && lo != "accept-encoding") {
            cmd << "-H \"" << k << ": " << v << "\" ";
        }
    }

    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;
    sa.lpSecurityDescriptor = NULL;

    HANDLE hStdOutRead = NULL;
    HANDLE hStdOutWrite = NULL;
    if (!CreatePipe(&hStdOutRead, &hStdOutWrite, &sa, 0)) {
        return false;
    }
    SetHandleInformation(hStdOutRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOA si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.hStdOutput = hStdOutWrite;
    si.hStdError = hStdOutWrite;
    si.dwFlags |= STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    std::string cmdStr = cmd.str();
    std::vector<char> cmdBuf(cmdStr.begin(), cmdStr.end());
    cmdBuf.push_back('\0');

    if (!CreateProcessA(NULL, cmdBuf.data(), NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(hStdOutRead);
        CloseHandle(hStdOutWrite);
        return false;
    }

    CloseHandle(hStdOutWrite);

    {
        std::lock_guard<std::mutex> lock(m_processMutex);
        m_hCurrentProcess = pi.hProcess;
    }

    char buffer[4096];
    DWORD bytesRead = 0;
    std::string lineAccumulator;

    std::regex pctRegex(R"((\d+(?:\.\d+)?)\s*%)");
    std::regex speedRegex(R"((\d+(?:\.\d+)?)\s*([KMGT]i?B/s))", std::regex::icase);
    std::regex etaRegex(R"((\d{1,2}:\d{2}(?::\d{2})?))");

    while (ReadFile(hStdOutRead, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
        if (m_aborted.load()) {
            TerminateProcess(pi.hProcess, 1);
            break;
        }

        buffer[bytesRead] = '\0';
        for (DWORD i = 0; i < bytesRead; ++i) {
            char c = buffer[i];
            if (c == '\r' || c == '\n') {
                if (!lineAccumulator.empty()) {
                    if (options.onLog) {
                        options.onLog(lineAccumulator);
                    }
                    std::smatch mPct;
                    if (std::regex_search(lineAccumulator, mPct, pctRegex)) {
                        float pct = std::stof(mPct[1].str());
                        std::string speedStr = "0.0 MB/s";
                        std::string etaStr = "--";

                        std::smatch mSpeed;
                        if (std::regex_search(lineAccumulator, mSpeed, speedRegex)) {
                            speedStr = mSpeed[0].str();
                        }
                        std::smatch mEta;
                        if (std::regex_search(lineAccumulator, mEta, etaRegex)) {
                            etaStr = mEta[1].str();
                        }

                        if (options.onProgress) {
                            options.onProgress(pct, speedStr, etaStr, 0);
                        }
                    } else if (lineAccumulator.find("Muxing") != std::string::npos || lineAccumulator.find("merging") != std::string::npos) {
                        if (options.onProgress) {
                            options.onProgress(99.0f, "Muxing", "0s", 0);
                        }
                    }
                    lineAccumulator.clear();
                }
            } else {
                lineAccumulator += c;
            }
        }
    }

    if (WaitForSingleObject(pi.hProcess, 5000) == WAIT_TIMEOUT) {
        TerminateProcess(pi.hProcess, 1);
    }
    DWORD exitCode = 1;
    GetExitCodeProcess(pi.hProcess, &exitCode);

    {
        std::lock_guard<std::mutex> lock(m_processMutex);
        m_hCurrentProcess = NULL;
    }

    CloseHandle(hStdOutRead);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    try {
        std::filesystem::remove_all(isolatedTemp);
    } catch (...) {}

    if (std::filesystem::exists(outputFile) && std::filesystem::file_size(outputFile) > 0) {
        return true;
    }

    std::filesystem::path altMkv = outPath.parent_path() / (saveName + ".mkv");
    std::filesystem::path altMp4 = outPath.parent_path() / (saveName + ".mp4");
    if (std::filesystem::exists(altMkv) && std::filesystem::file_size(altMkv) > 0) {
        if (altMkv.string() != outputFile) {
            std::filesystem::rename(altMkv, outputFile);
        }
        return true;
    }
    if (std::filesystem::exists(altMp4) && std::filesystem::file_size(altMp4) > 0) {
        if (altMp4.string() != outputFile) {
            std::filesystem::rename(altMp4, outputFile);
        }
        return true;
    }

    return exitCode == 0 && !m_aborted.load();
}

} // namespace OmniStream
