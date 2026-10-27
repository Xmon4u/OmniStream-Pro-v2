#include "download_engine.hpp"
#include "netflix_resolver.hpp"
#include <fstream>
#include <queue>

namespace OmniStream {

static std::string FindNM3U8Binary() {
    // 1. Current working directory
    std::filesystem::path curDir = std::filesystem::current_path();
    if (std::filesystem::exists(curDir / "N_m3u8DL-RE.exe")) return (curDir / "N_m3u8DL-RE.exe").string();
    if (std::filesystem::exists(curDir / "bin" / "N_m3u8DL-RE.exe")) return (curDir / "bin" / "N_m3u8DL-RE.exe").string();

    // 2. Executable's directory
    wchar_t exePath[MAX_PATH];
    if (GetModuleFileNameW(NULL, exePath, MAX_PATH)) {
        std::filesystem::path appDir = std::filesystem::path(exePath).parent_path();
        if (std::filesystem::exists(appDir / "N_m3u8DL-RE.exe")) return (appDir / "N_m3u8DL-RE.exe").string();
        if (std::filesystem::exists(appDir / "bin" / "N_m3u8DL-RE.exe")) return (appDir / "bin" / "N_m3u8DL-RE.exe").string();
        if (std::filesystem::exists(appDir / "vs_project" / "Release" / "N_m3u8DL-RE.exe")) return (appDir / "vs_project" / "Release" / "N_m3u8DL-RE.exe").string();
        if (std::filesystem::exists(appDir.parent_path() / "bin" / "N_m3u8DL-RE.exe")) return (appDir.parent_path() / "bin" / "N_m3u8DL-RE.exe").string();
        if (std::filesystem::exists(appDir.parent_path() / "N_m3u8DL-RE.exe")) return (appDir.parent_path() / "N_m3u8DL-RE.exe").string();
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

typedef LONG(NTAPI* pfnNtSuspendProcess)(HANDLE ProcessHandle);
typedef LONG(NTAPI* pfnNtResumeProcess)(HANDLE ProcessHandle);

static pfnNtSuspendProcess s_pfnNtSuspendProcess = nullptr;
static pfnNtResumeProcess s_pfnNtResumeProcess = nullptr;
static bool s_ntProcsInitialized = false;

static void EnsureNtProcessFuncs() {
    if (!s_ntProcsInitialized) {
        HMODULE hNtdll = GetModuleHandleW(L"ntdll.dll");
        if (hNtdll) {
            s_pfnNtSuspendProcess = (pfnNtSuspendProcess)GetProcAddress(hNtdll, "NtSuspendProcess");
            s_pfnNtResumeProcess = (pfnNtResumeProcess)GetProcAddress(hNtdll, "NtResumeProcess");
        }
        s_ntProcsInitialized = true;
    }
}

DownloadEngine::DownloadEngine() = default;
DownloadEngine::~DownloadEngine() {
    Abort();
}

void DownloadEngine::Pause() {
    m_paused.store(true);
    EnsureNtProcessFuncs();
    std::lock_guard<std::mutex> lock(m_processMutex);
    if (m_hCurrentProcess != NULL && s_pfnNtSuspendProcess) {
        s_pfnNtSuspendProcess(m_hCurrentProcess);
    }
}

void DownloadEngine::Resume() {
    m_paused.store(false);
    EnsureNtProcessFuncs();
    std::lock_guard<std::mutex> lock(m_processMutex);
    if (m_hCurrentProcess != NULL && s_pfnNtResumeProcess) {
        s_pfnNtResumeProcess(m_hCurrentProcess);
    }
}

void DownloadEngine::Abort() {
    m_aborted.store(true);
    EnsureNtProcessFuncs();
    std::lock_guard<std::mutex> lock(m_processMutex);
    if (m_hCurrentProcess != NULL) {
        if (m_paused.load() && s_pfnNtResumeProcess) {
            s_pfnNtResumeProcess(m_hCurrentProcess);
        }
        TerminateProcess(m_hCurrentProcess, 1);
    }
    if (!m_reservedTargetPath.empty()) {
        NetflixResolver::ReleaseReservedPath(m_reservedTargetPath);
        m_reservedTargetPath.clear();
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
    if (options.mode == "netflix_rename" || options.mode == "imdb_rename" || options.mode == "tmdb_rename" ||
        options.mode == "title_only" || options.mode == "title_id" || options.mode == "sub_merge") {
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
                size_t end = (qMark != std::string::npos && qMark > lastSlash) ? qMark : std::string::npos;
                baseName = info.url.substr(lastSlash + 1, end == std::string::npos ? end : end - lastSlash - 1);
            }
            if (baseName.empty()) baseName = "OmniStream_Capture";
        }
    }

    baseName = NetflixResolver::SanitizeFilename(baseName);

    std::filesystem::path dirPath;
    if (!options.saveDir.empty() && options.saveDir != ".") {
        dirPath = options.saveDir;
    } else {
        const char* userProfile = std::getenv("USERPROFILE");
        if (userProfile) {
            std::filesystem::path desktop = std::filesystem::path(userProfile) / "Desktop";
            if (std::filesystem::exists(desktop)) dirPath = desktop;
            else dirPath = ".";
        } else {
            dirPath = ".";
        }
    }
    std::filesystem::create_directories(dirPath);

    bool isStream = (info.url.find(".m3u8") != std::string::npos ||
                     info.url.find(".mpd") != std::string::npos ||
                     info.GetHeader("content-type").find("mpegurl") != std::string::npos);

    std::string ext;
    if (options.subtitleOnly) {
        ext = (options.subtitleFormat == "VTT") ? ".vtt" : ".srt";
    } else if (options.resolution == "audio_only") {
        ext = ".m4a";
    } else {
        ext = isStream ? ".mkv" : ".mp4";
    }
    std::filesystem::path targetFile = dirPath / (baseName + ext);
    std::string safeTargetPath = NetflixResolver::ReserveNonConflictingPath(targetFile.string());
    m_reservedTargetPath = safeTargetPath;

    log("Target: " + safeTargetPath);
    log("Mode: " + std::string(options.subtitleOnly ? "Direct Subtitle Stream Extractor" :
                                (isStream ? "HLS/DASH Multi-Stream Downloader" : "Direct Media Stream Downloader")));

    bool success = false;
    if (isStream || options.subtitleOnly) {
        std::string nm3u8Binary = FindNM3U8Binary();
        if (!nm3u8Binary.empty()) {
            log("[Engine] Found N_m3u8DL-RE binary: " + nm3u8Binary);
            success = DownloadWithNM3U8(info, safeTargetPath, options, nm3u8Binary);
            if (!success && !m_aborted.load() && !options.subtitleOnly) {
                log("[Engine] Notice: N_m3u8DL-RE completed with non-zero or failed. Falling back to native C++ HLS engine...");
                success = DownloadHlsStream(info, safeTargetPath, options);
            }
        } else {
            success = DownloadHlsStream(info, safeTargetPath, options);
        }
    } else {
        success = DownloadDirectStream(info, safeTargetPath, options);
    }

    if (!m_reservedTargetPath.empty()) {
        NetflixResolver::ReleaseReservedPath(m_reservedTargetPath);
        m_reservedTargetPath.clear();
    }

    if (success && !m_aborted.load()) {
        if (std::filesystem::exists(safeTargetPath)) {
            outFinalFile = safeTargetPath;
        } else {
            std::vector<std::string> altExts = options.subtitleOnly ? std::vector<std::string>{".srt", ".vtt"} :
                (options.resolution == "audio_only" ? std::vector<std::string>{".m4a", ".aac", ".mp3"} : std::vector<std::string>{".mkv", ".mp4"});
            bool foundAlt = false;
            try {
                for (const auto& entry : std::filesystem::directory_iterator(dirPath)) {
                    if (!entry.is_regular_file()) continue;
                    std::string stem = entry.path().stem().string();
                    if (stem.find(baseName) != std::string::npos && entry.file_size() > 0) {
                        std::string entryExt = entry.path().extension().string();
                        std::transform(entryExt.begin(), entryExt.end(), entryExt.begin(), ::tolower);
                        for (const auto& aExt : altExts) {
                            if (entryExt == aExt) {
                                outFinalFile = entry.path().string();
                                foundAlt = true;
                                break;
                            }
                        }
                        if (foundAlt) break;
                    }
                }
            } catch (...) {}
            if (!foundAlt) {
                outFinalFile = safeTargetPath;
            }
        }
        if (!outFinalFile.empty() && std::filesystem::exists(outFinalFile) && std::filesystem::file_size(outFinalFile) > 0) {
            log("Download successfully completed: " + outFinalFile);
            return true;
        } else {
            log("[Engine] Error: Download finished but output file was not found on disk.");
            return false;
        }
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
            options.onProgress(pct, speedStr, etaStr, downloaded, FormatBytes(downloaded));
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
                while (m_paused.load() && !m_aborted.load()) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
                }
                if (m_aborted.load()) break;

                size_t segIdx = 0;
                {
                    std::lock_guard<std::mutex> lock(queueMutex);
                    if (workQueue.empty()) break;
                    segIdx = workQueue.front();
                    workQueue.pop();
                }

                const auto& seg = playlist.segments[segIdx];
                std::string segFilePath = tempDir + "/seg_" + std::to_string(segIdx) + ".ts";

                HttpResponse resp;
                bool segOk = false;
                for (int retry = 0; retry < 4 && !m_aborted.load(); ++retry) {
                    resp = threadClient.Get(seg.url, info.headers);
                    if (resp.IsSuccess() && !resp.body.empty()) {
                        segOk = true;
                        break;
                    }
                    std::this_thread::sleep_for(std::chrono::milliseconds(250 * (retry + 1)));
                }
                if (!segOk) {
                    continue;
                }

                std::vector<uint8_t> finalData = std::move(resp.body);

                // Handle AES-128 decryption if needed
                if (seg.key.method == "AES-128" && keyCache.count(seg.key.uri)) {
                    std::vector<uint8_t> iv = Crypto::HexToBytes(seg.key.ivHex);
                    if (iv.empty()) {
                        // Default IV is segment sequence number in big-endian (16 bytes)
                        iv.resize(16, 0);
                        uint64_t seq = playlist.mediaSequence + segIdx;
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
                    options.onProgress(pct, speedStr, etaStr, totalDownloadedBytes.load(), FormatBytes(totalDownloadedBytes.load()));
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

    std::ostringstream cmd;
    int thCount = options.threadCount > 0 ? options.threadCount : 16;
    cmd << "\"" << nm3u8Path << "\" \"" << info.url << "\" "
        << "--auto-select --live-perform-as-vod "
        << "--save-dir \"" << saveDir << "\" "
        << "--save-name \"" << saveName << "\" "
        << "--tmp-dir \"" << isolatedTemp << "\" "
        << "--thread-count " << thCount << " --download-retry-count 15 --http-request-timeout 30 "
        << "--disable-update-check --no-log --no-ansi-color ";

    auto buildSubLangArg = [](const std::string& lang) -> std::string {
        if (lang.empty() || lang == "all") return "-ss all ";
        if (lang == "ben" || lang == "bn") return "-ss lang=\"bn|ben|Bengali\":for=all ";
        if (lang == "eng" || lang == "en") return "-ss lang=\"en|eng|English\":for=all ";
        if (lang == "hin" || lang == "hi") return "-ss lang=\"hi|hin|Hindi\":for=all ";
        if (lang == "spa" || lang == "es") return "-ss lang=\"es|spa|Spanish\":for=all ";
        if (lang == "fra" || lang == "fr") return "-ss lang=\"fr|fra|French\":for=all ";
        if (lang == "deu" || lang == "de") return "-ss lang=\"de|deu|German\":for=all ";
        if (lang == "jpn" || lang == "ja") return "-ss lang=\"ja|jpn|Japanese\":for=all ";
        return "-ss lang=\"" + lang + "\":for=all ";
    };


    std::string subFmt = options.subtitleFormat.empty() ? "SRT" : options.subtitleFormat;

    if (options.subtitleOnly) {
        cmd << "--sub-only --sub-format " << subFmt << " --auto-subtitle-fix ";
        cmd << buildSubLangArg(options.subtitleLanguage);
    } else {
        // Video stream selection
        if (options.resolution == "audio_only") {
            cmd << "-dv all ";
        } else if (options.resolution == "720p") {
            cmd << "-sv res=\"720*|1280*\":for=best ";
        } else if (options.resolution == "480p") {
            cmd << "-sv res=\"480*|854*\":for=best ";
        } else if (options.resolution == "1080p") {
            cmd << "-sv res=\"1080*|1920*\":for=best ";
        } else {
            cmd << "-sv best ";
        }

        // Audio selection
        if (options.mode == "sub_merge") {
            cmd << "-sa all ";
        } else if (options.audioChoice == "dual") {
            cmd << "-sa lang=\"en|eng|hi|hin\":for=all ";
        } else if (options.audioChoice == "en") {
            cmd << "-sa lang=\"en|eng\":for=best ";
        } else if (options.audioChoice == "hi") {
            cmd << "-sa lang=\"hi|hin\":for=best ";
        } else {
            cmd << "-sa all ";
        }

        // Subtitles inclusion
        if (options.includeSubtitles || options.mode == "sub_merge") {
            cmd << "--sub-format " << subFmt << " --auto-subtitle-fix ";
            if (options.mode == "sub_merge") {
                cmd << "-ss all ";
            } else {
                cmd << buildSubLangArg(options.subtitleLanguage);
            }
        }

        // Muxer container
        std::string ffmpegPath;
        if (options.resolution == "audio_only") {
            if (Muxer::FindFFmpeg(ffmpegPath)) {
                cmd << "-M format=m4a:muxer=ffmpeg --ffmpeg-binary-path \"" << ffmpegPath << "\" ";
            } else {
                cmd << "-M format=m4a ";
            }
        } else {
            if (Muxer::FindFFmpeg(ffmpegPath)) {
                cmd << "-M format=mkv:muxer=ffmpeg --ffmpeg-binary-path \"" << ffmpegPath << "\" ";
            } else {
                cmd << "-M format=mkv ";
            }
        }
    }

    auto escapeHeaderVal = [](const std::string& s) -> std::string {
        std::string r;
        r.reserve(s.size());
        for (char c : s) {
            if (c == '"') r += "\\\"";
            else if (c == '\n' || c == '\r') r += ' ';
            else r += c;
        }
        return r;
    };

    if (!info.referer.empty()) {
        cmd << "-H \"Referer: " << escapeHeaderVal(info.referer) << "\" ";
    }
    if (!info.origin.empty()) {
        cmd << "-H \"Origin: " << escapeHeaderVal(info.origin) << "\" ";
    }
    if (!info.user_agent.empty()) {
        cmd << "-H \"User-Agent: " << escapeHeaderVal(info.user_agent) << "\" ";
    }
    if (!info.cookie.empty()) {
        cmd << "-H \"Cookie: " << escapeHeaderVal(info.cookie) << "\" ";
    }

    // Add custom request headers
    for (const auto& [k, v] : info.headers) {
        std::string lo = k;
        std::transform(lo.begin(), lo.end(), lo.begin(), ::tolower);
        if (lo != "referer" && lo != "origin" && lo != "user-agent" && lo != "cookie" &&
            lo != "host" && lo != "connection" && lo != "content-length" && lo != "accept-encoding") {
            cmd << "-H \"" << escapeHeaderVal(k) << ": " << escapeHeaderVal(v) << "\" ";
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
    std::string streamAccumulator;

    std::regex pctRegex(R"((\d+(?:\.\d+)?)\s*%)");
    std::regex sizePairRegex(R"((\d+(?:\.\d+)?\s*[KMGT]i?B)\s*/\s*(\d+(?:\.\d+)?\s*[KMGT]i?B))", std::regex::icase);
    std::regex speedRegex(R"((\d+(?:\.\d+)?)\s*([KMGT]i?B(?:ps|/s)|Bps|B/s))", std::regex::icase);
    std::regex etaRegex(R"((\d{1,2}:\d{2}(?::\d{2})?))");

    float lastReportedPct = 0.0f;
    std::string lastReportedSpeed = "0.0 MB/s";
    std::string lastReportedEta = "--";
    std::string lastReportedSize = "-- / --";
    uint64_t lastReportedBytes = 0;

    auto lastProgressCheck = std::chrono::steady_clock::now();

    std::atomic<bool> readLoopDone{ false };
    std::thread pauseHeartbeat([&]() {
        while (!readLoopDone.load()) {
            if (m_paused.load() && options.onProgress) {
                options.onProgress(lastReportedPct, "Paused", "Paused", lastReportedBytes, lastReportedSize);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(250));
        }
    });

    while (ReadFile(hStdOutRead, buffer, sizeof(buffer) - 1, &bytesRead, NULL) && bytesRead > 0) {
        if (m_aborted.load()) {
            TerminateProcess(pi.hProcess, 1);
            break;
        }

        if (m_paused.load()) {
            if (options.onProgress) {
                options.onProgress(lastReportedPct, "Paused", "Paused", lastReportedBytes, lastReportedSize);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        buffer[bytesRead] = '\0';
        streamAccumulator.append(buffer, bytesRead);

        // Forward complete lines to onLog if newlines exist
        size_t nlPos = std::string::npos;
        while ((nlPos = streamAccumulator.find('\n')) != std::string::npos) {
            std::string line = streamAccumulator.substr(0, nlPos);
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (options.onLog && !line.empty()) {
                options.onLog(line);
            }
            streamAccumulator.erase(0, nlPos + 1);
        }

        auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastProgressCheck).count() < 60) {
            continue;
        }
        lastProgressCheck = now;

        // Search for progress in recent window (since piped N_m3u8DL-RE outputs continuous records without newlines)
        std::string searchWindow = streamAccumulator;
        if (searchWindow.size() > 800) {
            searchWindow = searchWindow.substr(searchWindow.size() - 800);
        }

        auto pBegin = std::sregex_iterator(searchWindow.begin(), searchWindow.end(), pctRegex);
        auto pEnd = std::sregex_iterator();
        std::smatch lastPct;
        bool foundPct = false;
        for (std::sregex_iterator it = pBegin; it != pEnd; ++it) {
            lastPct = *it;
            foundPct = true;
        }

        if (foundPct) {
            float pct = std::stof(lastPct[1].str());
            std::string sub = searchWindow.substr(lastPct.position(0));

            std::smatch mSize;
            if (std::regex_search(sub, mSize, sizePairRegex)) {
                lastReportedSize = mSize[1].str() + " / " + mSize[2].str();
            }

            std::smatch mSpeed;
            if (std::regex_search(sub, mSpeed, speedRegex)) {
                std::string sVal = mSpeed[1].str();
                std::string rawUnit = mSpeed[2].str();
                std::string uUpper = rawUnit;
                std::transform(uUpper.begin(), uUpper.end(), uUpper.begin(), ::toupper);
                if (uUpper == "MBPS" || uUpper == "MIBPS") rawUnit = "MB/s";
                else if (uUpper == "KBPS" || uUpper == "KIBPS") rawUnit = "KB/s";
                else if (uUpper == "GBPS" || uUpper == "GIBPS") rawUnit = "GB/s";
                else if (uUpper == "BPS") rawUnit = "B/s";
                lastReportedSpeed = sVal + " " + rawUnit;
            }

            std::smatch mEta;
            if (std::regex_search(sub, mEta, etaRegex)) {
                lastReportedEta = mEta[1].str();
            }

            lastReportedPct = pct;

            if (options.onProgress && !m_paused.load()) {
                options.onProgress(lastReportedPct, lastReportedSpeed, lastReportedEta, lastReportedBytes, lastReportedSize);
            }
        } else if (searchWindow.find("Muxing") != std::string::npos || searchWindow.find("merging") != std::string::npos) {
            if (options.onProgress && !m_paused.load()) {
                options.onProgress(99.0f, "Muxing", "0s", lastReportedBytes, lastReportedSize);
            }
        }

        if (streamAccumulator.size() > 8192) {
            streamAccumulator = streamAccumulator.substr(streamAccumulator.size() - 2048);
        }
    }

    readLoopDone.store(true);
    if (pauseHeartbeat.joinable()) {
        pauseHeartbeat.join();
    }

    WaitForSingleObject(pi.hProcess, INFINITE);

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

    uint64_t finalSz = 0;
    if (std::filesystem::exists(outputFile) && (finalSz = std::filesystem::file_size(outputFile)) > 0) {
        if (options.onProgress) {
            options.onProgress(100.0f, "Done", "0s", finalSz, FormatBytes(finalSz));
        }
        return true;
    }

    std::vector<std::string> altExts;
    if (options.subtitleOnly) {
        altExts = { ".srt", ".vtt" };
    } else if (options.resolution == "audio_only") {
        altExts = { ".m4a", ".aac", ".mp3", ".mkv", ".mp4" };
    } else {
        altExts = { ".mkv", ".mp4", ".ts" };
    }

    for (const auto& aExt : altExts) {
        std::filesystem::path altFile = outPath.parent_path() / (saveName + aExt);
        if (std::filesystem::exists(altFile) && (finalSz = std::filesystem::file_size(altFile)) > 0) {
            if (altFile.string() != outputFile && !std::filesystem::exists(outputFile)) {
                try {
                    std::filesystem::rename(altFile, outputFile);
                } catch (...) {}
            }
            if (options.onProgress) {
                options.onProgress(100.0f, "Done", "0s", finalSz, FormatBytes(finalSz));
            }
            return true;
        }
    }

    // Check directory iterator for files matching saveName prefix (e.g. saveName.en.srt)
    try {
        for (const auto& entry : std::filesystem::directory_iterator(outPath.parent_path())) {
            if (!entry.is_regular_file()) continue;
            std::string stem = entry.path().stem().string();
            if (stem.find(saveName) != std::string::npos && entry.file_size() > 0) {
                std::string ext = entry.path().extension().string();
                std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
                for (const auto& aExt : altExts) {
                    if (ext == aExt) {
                        finalSz = entry.file_size();
                        if (options.onProgress) {
                            options.onProgress(100.0f, "Done", "0s", finalSz, FormatBytes(finalSz));
                        }
                        return true;
                    }
                }
            }
        }
    } catch (...) {}
    if (options.onLog) {
        options.onLog("[Engine] Error: N_m3u8DL-RE completed without producing any output media file on disk.");
    }
    return false;
}

} // namespace OmniStream
