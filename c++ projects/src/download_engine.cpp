#include "download_engine.hpp"
#include "netflix_resolver.hpp"
#include <fstream>
#include <queue>

namespace OmniStream {

DownloadEngine::DownloadEngine() = default;
DownloadEngine::~DownloadEngine() {
    Abort();
}

void DownloadEngine::Abort() {
    m_aborted.store(true);
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

    bool isHls = (info.url.find(".m3u8") != std::string::npos ||
                  info.GetHeader("content-type").find("mpegurl") != std::string::npos);

    std::string ext = isHls ? ".mkv" : ".mp4";
    std::filesystem::path targetFile = dirPath / (baseName + ext);
    std::string safeTargetPath = NetflixResolver::GetNonConflictingPath(targetFile.string());

    log("Target: " + safeTargetPath);
    log("Mode: " + std::string(isHls ? "HLS Multi-Stream Downloader" : "Direct Media Stream Downloader"));

    bool success = false;
    if (isHls) {
        success = DownloadHlsStream(info, safeTargetPath, options);
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

} // namespace OmniStream
