#include "MetadataResolver.hpp"
#include <regex>
#include <algorithm>
#include <cctype>

namespace OmniStream {

std::string MetadataResolver::ExtractRefererFromCurl(const std::string& curl_cmd) {
    static const std::regex ref_regex(R"(-H\s+['"](?:Referer|referer):\s*([^\s'"\\]+))", std::regex::icase);
    std::smatch match;
    if (std::regex_search(curl_cmd, match, ref_regex)) {
        return match[1].str();
    }
    static const std::regex url_regex(R"(https?://[^\s'"\\]+)", std::regex::icase);
    if (std::regex_search(curl_cmd, match, url_regex)) {
        return match[0].str();
    }
    return "";
}

std::string MetadataResolver::CleanTitleForMatching(const std::string& title) {
    std::string t = Utils::ToLower(title);
    static const std::regex junk_regex(
        R"(\b(?:download|full\s*movie|watch\s*online|hindi\s*dubbed|dual\s*audio|hd\s*rip|web\s*rip|720p|1080p|480p|prmovies|free\s*movies|tv\s*shows\s*online|on|and|free|movies)\b)",
        std::regex::icase
    );
    t = std::regex_replace(t, junk_regex, " ");

    std::string clean;
    for (char c : t) {
        if (std::isalnum(static_cast<unsigned char>(c))) {
            clean += c;
        }
    }
    return clean;
}

std::string MetadataResolver::SanitizeInputTitle(const std::string& title) {
    // Strip stream extension suffixes e.g. .m3u8, .mpd, .mp4
    static const std::regex ext_regex(R"(\.(?:m3u8|mpd|mp4|webm|mkv|m4s)(\?.*)?$)", std::regex::icase);
    std::string res = std::regex_replace(title, ext_regex, "");

    // Remove illegal Windows filename characters: \ / : * ? " < > |
    for (char& c : res) {
        if (c == '\\' || c == '/' || c == ':' || c == '*' || c == '?' ||
            c == '"' || c == '<' || c == '>' || c == '|') {
            c = '_';
        }
    }
    res = Utils::Trim(res);
    // Windows file safety: strip trailing periods and spaces
    while (!res.empty() && (res.back() == '.' || res.back() == ' ')) {
        res.pop_back();
    }
    if (res.empty()) res = "OmniStream_Download";
    return res;
}

std::string MetadataResolver::ComputeMovieUniqueId(
    const std::string& url_or_input,
    const std::string& page_url,
    const std::string& title,
    const std::string& year
) {
    std::string stream_tag = "";
    if (!url_or_input.empty()) {
        std::string s_lo = Utils::ToLower(url_or_input);
        if (s_lo.find(".m3u8") != std::string::npos || s_lo.find(".mpd") != std::string::npos ||
            s_lo.find(".mp4") != std::string::npos || s_lo.find(".mkv") != std::string::npos ||
            s_lo.find(".webm") != std::string::npos) {
            std::smatch sm;
            static const std::regex track_regex(R"(/a/(\d+)/|/(\d{3,4}p)/|/(?:video|audio|master|player)\.m3u8)", std::regex::icase);
            if (std::regex_search(s_lo, sm, track_regex)) {
                stream_tag = ":" + sm[0].str();
            } else {
                size_t q = s_lo.find('?');
                std::string path_only = (q != std::string::npos) ? s_lo.substr(0, q) : s_lo;
                size_t last_slash = path_only.rfind('/');
                if (last_slash != std::string::npos) {
                    stream_tag = ":" + path_only.substr(last_slash + 1);
                }
            }
        }
    }

    std::string cand_url = !page_url.empty() ? page_url : url_or_input;
    if (cand_url.find("curl") != std::string::npos) {
        cand_url = ExtractRefererFromCurl(cand_url);
    }

    if (cand_url.rfind("http://", 0) == 0 || cand_url.rfind("https://", 0) == 0) {
        // Parse host and path
        size_t scheme_pos = cand_url.find("://");
        if (scheme_pos != std::string::npos) {
            std::string rest = cand_url.substr(scheme_pos + 3);
            size_t slash_pos = rest.find('/');
            std::string host = (slash_pos != std::string::npos) ? rest.substr(0, slash_pos) : rest;
            std::string path = (slash_pos != std::string::npos) ? rest.substr(slash_pos) : "";

            // Remove port and query params
            size_t query_pos = path.find('?');
            if (query_pos != std::string::npos) path = path.substr(0, query_pos);
            while (!path.empty() && path.back() == '/') path.pop_back();

            host = Utils::ToLower(host);
            if (host.rfind("www.", 0) == 0) host = host.substr(4);
            path = Utils::ToLower(path);

            static const std::regex stream_regex(R"(\.(?:m3u8|mpd|mp4|mkv|webm|m4s)$)", std::regex::icase);
            if (std::regex_search(path, stream_regex)) {
                return "stream:" + host + path;
            } else if (!path.empty() && path != "/") {
                return "page:" + host + path + stream_tag;
            }
        }
    }

    std::string clean_t = CleanTitleForMatching(title);
    std::string clean_y = Utils::Trim(year);
    if (!clean_y.empty() && clean_t.find(clean_y) == std::string::npos) {
        clean_t += clean_y;
    }

    if (!clean_t.empty()) {
        return "title:" + clean_t + stream_tag;
    }
    return "raw:" + std::to_string(Utils::CurrentTimestampMs()) + stream_tag;
}

std::string MetadataResolver::ExtractNetflixId(const std::string& text) {
    // 8-digit pattern
    static const std::regex nf_regex(R"(\b(8\d{7})\b)");
    std::smatch match;
    if (std::regex_search(text, match, nf_regex)) {
        return match[1].str();
    }
    return "";
}

std::string MetadataResolver::ExtractIMDbId(const std::string& text) {
    static const std::regex imdb_regex(R"(\b(tt\d{7,8})\b)", std::regex::icase);
    std::smatch match;
    if (std::regex_search(text, match, imdb_regex)) {
        return match[1].str();
    }
    return "";
}

std::string MetadataResolver::ExtractTMDbId(const std::string& text) {
    static const std::regex tmdb_regex(R"((?:tmdb(?:id)?[:\s/]+|themoviedb\.org/(?:movie|tv)/)(\d{4,8}))", std::regex::icase);
    std::smatch match;
    if (std::regex_search(text, match, tmdb_regex)) {
        return match[1].str();
    }
    return "";
}

MetadataResolver::SeasonEpisodeInfo MetadataResolver::ExtractSeasonEpisode(const std::string& text) {
    SeasonEpisodeInfo info;
    static const std::regex se_regex(R"(\bS(\d{1,2})E(\d{1,3})\b)", std::regex::icase);
    std::smatch match;
    if (std::regex_search(text, match, se_regex)) {
        info.season = std::stoi(match[1].str());
        info.episode = std::stoi(match[2].str());
        info.found = true;
        return info;
    }

    static const std::regex alt_regex(R"(\bSeason\s*(\d{1,2})\b.*?\bEpisode\s*(\d{1,3})\b)", std::regex::icase);
    if (std::regex_search(text, match, alt_regex)) {
        info.season = std::stoi(match[1].str());
        info.episode = std::stoi(match[2].str());
        info.found = true;
    }
    return info;
}

std::string MetadataResolver::ResolveTargetFilename(
    const std::string& input_text,
    const std::string& custom_title,
    DownloadMode mode,
    const std::string& year
) {
    std::string base = SanitizeInputTitle(custom_title.empty() ? "OmniStream_Download" : custom_title);
    std::string nid = ExtractNetflixId(input_text);
    if (nid.empty()) nid = ExtractNetflixId(custom_title);

    switch (mode) {
        case DownloadMode::Netflix: {
            if (!nid.empty() && (custom_title.empty() || custom_title == nid)) {
                return nid;
            }
            return base;
        }
        case DownloadMode::TitleOnly: {
            return base;
        }
        case DownloadMode::IMDb: {
            std::string imdb = ExtractIMDbId(input_text);
            if (!imdb.empty()) return imdb;
            return base;
        }
        case DownloadMode::TMDB: {
            std::string tmdb = ExtractTMDbId(input_text);
            if (!tmdb.empty()) return tmdb;
            return base;
        }
        case DownloadMode::TitleAndId: {
            if (!nid.empty()) return base + " [" + nid + "]";
            return base;
        }
        default:
            return base;
    }
}

} // namespace OmniStream
