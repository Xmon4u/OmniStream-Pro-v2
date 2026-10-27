#pragma once

#include "common.hpp"
#include <functional>

namespace OmniStream {

class NetflixResolver {
public:
    static std::string ExtractNetflixId(const std::string& input);
    static std::string ExtractImdbId(const std::string& input);
    static std::string ExtractTmdbId(const std::string& input);
    static std::string ExtractEpisodeTag(const std::string& input);

    static std::string SanitizeFilename(const std::string& rawName);
    static std::string GetNonConflictingPath(const std::string& targetPath);

    static std::string ResolveOnlineTitle(const std::string& netflixId, std::function<void(const std::string&)> logCallback = nullptr);
    static std::string ResolveOnlineImdbId(const std::string& title);
    static std::string ResolveOnlineTmdbId(const std::string& imdbId, const std::string& title = "");

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
