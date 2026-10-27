#pragma once

#include "common.hpp"
#include <functional>

namespace OmniStream {

struct MediaMetadata {
    std::string title;
    std::string year;
    std::string episodeTag;
    std::string netflixId;
    std::string imdbId;
    std::string tmdbId;
};

class NetflixResolver {
public:
    static std::string ExtractNetflixId(const std::string& input);
    static std::string ExtractImdbId(const std::string& input);
    static std::string ExtractTmdbId(const std::string& input);
    static std::string ExtractEpisodeTag(const std::string& input);

    static std::string SanitizeFilename(const std::string& rawName);
    static std::string GetNonConflictingPath(const std::string& targetPath);

    // Thread-safe active path reservation to prevent concurrent collisions in the same folder
    static std::string ReserveNonConflictingPath(const std::string& targetPath);
    static void ReleaseReservedPath(const std::string& targetPath);

    static MediaMetadata ResolveFullMetadata(
        const std::string& inputText,
        const std::string& customTitle = "",
        const std::string& netflixId = "",
        const std::string& imdbId = "",
        const std::string& tmdbId = "",
        std::function<void(const std::string&)> logCallback = nullptr
    );

    static std::string ResolveOnlineTitle(const std::string& netflixId, std::function<void(const std::string&)> logCallback = nullptr);
    static std::string ResolveOnlineImdbId(const std::string& title, const std::string& year = "");
    static std::string ResolveOnlineTmdbId(const std::string& imdbId, const std::string& title = "", const std::string& year = "");

    static std::string ResolveMediaRename(
        const std::string& mode,
        const std::string& inputText,
        const std::string& customTitle = "",
        const std::string& netflixId = "",
        const std::string& imdbId = "",
        const std::string& tmdbId = "",
        std::function<void(const std::string&)> logCallback = nullptr
    );
};

} // namespace OmniStream

