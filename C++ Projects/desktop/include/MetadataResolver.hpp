#pragma once

#include "Common.hpp"
#include <string>
#include <regex>
#include <optional>

namespace OmniStream {

class MetadataResolver {
public:
    static std::string ComputeMovieUniqueId(
        const std::string& url_or_input,
        const std::string& page_url = "",
        const std::string& title = "",
        const std::string& year = ""
    );

    static std::string CleanTitleForMatching(const std::string& title);
    static std::string SanitizeInputTitle(const std::string& title);

    static std::string ExtractNetflixId(const std::string& text);
    static std::string ExtractIMDbId(const std::string& text);
    static std::string ExtractTMDbId(const std::string& text);

    struct SeasonEpisodeInfo {
        int season = 0;
        int episode = 0;
        bool found = false;
    };
    static SeasonEpisodeInfo ExtractSeasonEpisode(const std::string& text);

    static std::string ResolveTargetFilename(
        const std::string& input_text,
        const std::string& custom_title,
        DownloadMode mode,
        const std::string& year = ""
    );

private:
    static std::string ExtractRefererFromCurl(const std::string& curl_cmd);
};

} // namespace OmniStream

