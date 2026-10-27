#pragma once

#include "common.hpp"

namespace OmniStream {

struct HlsKey {
    std::string method;
    std::string uri;
    std::string ivHex;
    std::vector<uint8_t> keyData;
};

struct HlsSegment {
    int index = 0;
    double duration = 0.0;
    std::string url;
    HlsKey key;
};

struct HlsTrack {
    std::string type; // "VIDEO", "AUDIO", "SUBTITLES"
    std::string name;
    std::string language;
    std::string resolution;
    uint64_t bandwidth = 0;
    std::string uri;
};

struct HlsPlaylist {
    bool isMaster = false;
    std::string baseUrl;
    std::vector<HlsTrack> tracks;
    std::vector<HlsSegment> segments;
    std::string initSegmentUrl; // For fMP4 EXT-X-MAP
};

class HlsParser {
public:
    static HlsPlaylist Parse(const std::string& manifestContent, const std::string& manifestUrl);
    static HlsTrack SelectBestVideoTrack(const HlsPlaylist& master, const std::string& preferredResolution = "1080p");
    static std::vector<HlsTrack> GetAudioTracks(const HlsPlaylist& master);
    static std::vector<HlsTrack> GetSubtitleTracks(const HlsPlaylist& master);
};

} // namespace OmniStream
