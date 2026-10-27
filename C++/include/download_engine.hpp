#pragma once

#include "common.hpp"
#include "curl_parser.hpp"
#include "hls_parser.hpp"
#include "http_client.hpp"
#include "crypto.hpp"
#include "muxer.hpp"

namespace OmniStream {

struct DownloadOptions {
    std::string inputText;
    std::string saveName;
    std::string saveDir = ".";
    std::string resolution = "1080p";
    std::string audioChoice = "all";
    bool includeSubtitles = true;
    std::string subtitleFormat = "SRT";
    int threadCount = 16;
    std::string mode = "normal"; // "normal", "sub_merge", "netflix_rename", "imdb_rename", "tmdb_rename"
    std::string netflixId;
    std::string imdbId;
    std::string tmdbId;

    std::function<void(float percent, const std::string& speed, const std::string& eta, uint64_t downloadedBytes, const std::string& sizeStr)> onProgress;
    std::function<void(const std::string& message)> onLog;
};

class DownloadEngine {
public:
    DownloadEngine();
    ~DownloadEngine();

    bool Download(const DownloadOptions& options, std::string& outFinalFile);
    void Abort();
    bool IsAborted() const { return m_aborted.load(); }

private:
    bool DownloadDirectStream(const StreamInfo& info, const std::string& outputFile, const DownloadOptions& options);
    bool DownloadHlsStream(const StreamInfo& info, const std::string& outputFile, const DownloadOptions& options);
    bool DownloadTrackSegments(
        const HlsPlaylist& playlist,
        const StreamInfo& info,
        const std::string& tempDir,
        const std::string& trackName,
        std::vector<std::string>& outSegmentFiles,
        const DownloadOptions& options
    );
    bool DownloadWithNM3U8(const StreamInfo& info, const std::string& outputFile, const DownloadOptions& options, const std::string& nm3u8Path);

    std::atomic<bool> m_aborted{ false };
    std::mutex m_processMutex;
    HANDLE m_hCurrentProcess{ NULL };
};

} // namespace OmniStream
