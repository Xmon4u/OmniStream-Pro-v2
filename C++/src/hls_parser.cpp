#include "hls_parser.hpp"
#include "curl_parser.hpp"

namespace OmniStream {

static std::string ExtractAttribute(const std::string& line, const std::string& key) {
    std::regex reg(key + R"(=(?:\"([^\"]*)\"|([^,\r\n]+)))", std::regex::icase);
    std::smatch match;
    if (std::regex_search(line, match, reg)) {
        return match[1].matched ? match[1].str() : match[2].str();
    }
    return "";
}

HlsPlaylist HlsParser::Parse(const std::string& manifestContent, const std::string& manifestUrl) {
    HlsPlaylist playlist;
    playlist.baseUrl = manifestUrl;

    std::istringstream stream(manifestContent);
    std::string line;

    bool hasStreamInf = false;
    HlsKey currentKey;
    int segIndex = 0;

    HlsTrack pendingTrack;
    bool hasPendingTrack = false;

    while (std::getline(stream, line)) {
        // Strip trailing \r
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;

        if (line.rfind("#EXT-X-STREAM-INF:", 0) == 0) {
            hasStreamInf = true;
            pendingTrack = HlsTrack();
            pendingTrack.type = "VIDEO";
            pendingTrack.resolution = ExtractAttribute(line, "RESOLUTION");
            std::string bw = ExtractAttribute(line, "BANDWIDTH");
            if (!bw.empty()) pendingTrack.bandwidth = std::strtoull(bw.c_str(), nullptr, 10);
            pendingTrack.name = pendingTrack.resolution.empty() ? ("Bandwidth " + bw) : pendingTrack.resolution;
            hasPendingTrack = true;
        }
        else if (line.rfind("#EXT-X-MEDIA:", 0) == 0) {
            std::string mediaType = ExtractAttribute(line, "TYPE");
            std::string uri = ExtractAttribute(line, "URI");
            std::string name = ExtractAttribute(line, "NAME");
            std::string lang = ExtractAttribute(line, "LANGUAGE");

            if (!uri.empty()) {
                HlsTrack track;
                track.type = mediaType;
                track.name = name;
                track.language = lang;
                track.uri = CurlParser::ResolveUrl(manifestUrl, uri);
                playlist.tracks.push_back(track);
            }
        }
        else if (line.rfind("#EXT-X-KEY:", 0) == 0) {
            currentKey.method = ExtractAttribute(line, "METHOD");
            currentKey.uri = ExtractAttribute(line, "URI");
            if (!currentKey.uri.empty()) {
                currentKey.uri = CurlParser::ResolveUrl(manifestUrl, currentKey.uri);
            }
            currentKey.ivHex = ExtractAttribute(line, "IV");
        }
        else if (line.rfind("#EXT-X-MAP:", 0) == 0) {
            std::string initUri = ExtractAttribute(line, "URI");
            if (!initUri.empty()) {
                playlist.initSegmentUrl = CurlParser::ResolveUrl(manifestUrl, initUri);
            }
        }
        else if (line.rfind("#EXTINF:", 0) == 0) {
            HlsSegment seg;
            seg.index = segIndex++;
            seg.key = currentKey;

            // Extract duration: #EXTINF:6.000,
            size_t colon = line.find(':');
            size_t comma = line.find(',', colon);
            if (colon != std::string::npos) {
                std::string durStr = line.substr(colon + 1, comma == std::string::npos ? comma : comma - colon - 1);
                seg.duration = std::strtod(durStr.c_str(), nullptr);
            }

            // Next non-comment line is segment URL
            std::string segUrlLine;
            while (std::getline(stream, segUrlLine)) {
                if (!segUrlLine.empty() && segUrlLine.back() == '\r') segUrlLine.pop_back();
                if (segUrlLine.empty()) continue;
                if (segUrlLine[0] == '#') continue;

                seg.url = CurlParser::ResolveUrl(manifestUrl, segUrlLine);
                playlist.segments.push_back(seg);
                break;
            }
        }
        else if (hasPendingTrack && line[0] != '#') {
            pendingTrack.uri = CurlParser::ResolveUrl(manifestUrl, line);
            playlist.tracks.push_back(pendingTrack);
            hasPendingTrack = false;
        }
    }

    playlist.isMaster = hasStreamInf || (!playlist.tracks.empty() && playlist.segments.empty());
    return playlist;
}

HlsTrack HlsParser::SelectBestVideoTrack(const HlsPlaylist& master, const std::string& preferredResolution) {
    if (master.tracks.empty()) return HlsTrack();

    std::vector<HlsTrack> videoTracks;
    for (const auto& t : master.tracks) {
        if (t.type == "VIDEO") videoTracks.push_back(t);
    }

    if (videoTracks.empty()) {
        return master.tracks.front();
    }

    // Try matching preferred resolution
    for (const auto& t : videoTracks) {
        if (!preferredResolution.empty() && t.resolution.find(preferredResolution) != std::string::npos) {
            return t;
        }
    }

    // Pick highest bandwidth
    auto it = std::max_element(videoTracks.begin(), videoTracks.end(), [](const HlsTrack& a, const HlsTrack& b) {
        return a.bandwidth < b.bandwidth;
    });

    return *it;
}

std::vector<HlsTrack> HlsParser::GetAudioTracks(const HlsPlaylist& master) {
    std::vector<HlsTrack> audioTracks;
    for (const auto& t : master.tracks) {
        if (t.type == "AUDIO") audioTracks.push_back(t);
    }
    return audioTracks;
}

std::vector<HlsTrack> HlsParser::GetSubtitleTracks(const HlsPlaylist& master) {
    std::vector<HlsTrack> subTracks;
    for (const auto& t : master.tracks) {
        if (t.type == "SUBTITLES") subTracks.push_back(t);
    }
    return subTracks;
}

} // namespace OmniStream
