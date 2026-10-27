#pragma once

#include "common.hpp"

namespace OmniStream {

class Muxer {
public:
    static bool FindFFmpeg(std::string& outPath);

    static bool ConcatenateSegments(
        const std::vector<std::string>& segmentFiles,
        const std::string& outputFile,
        const std::string& initSegmentFile = ""
    );

    static bool MuxTracks(
        const std::string& videoFile,
        const std::vector<std::pair<std::string, std::string>>& audioFilesWithLang,
        const std::vector<std::pair<std::string, std::string>>& subtitleFilesWithLang,
        const std::string& outputFile
    );
};

} // namespace OmniStream
