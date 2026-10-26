#include "netflix_resolver.hpp"
#include "http_client.hpp"
#include <iomanip>
#include <sstream>
#include <unordered_set>

namespace OmniStream {

static bool IsGenericStreamName(const std::string& str) {
    if (str.empty()) return true;
    std::string s = str;
    std::transform(s.begin(), s.end(), s.begin(), ::tolower);
    static const std::unordered_set<std::string> generic = {
        "master", "playlist", "manifest", "index", "stream", "chunklist",
        "video", "player", "output", "segment", "media", "play", "hls", "dash",
        "main", "prog_index", "video_1080p", "video_720p", "video_480p",
        "audio_en", "audio_hin", "audio", "subtitle"
    };
    return generic.find(s) != generic.end();
}

static std::string UrlEncodeSlug(const std::string& value) {
    std::ostringstream escaped;
    escaped.fill('0');
    escaped << std::hex;

    for (char c : value) {
        if (isalnum(static_cast<unsigned char>(c)) || c == '-' || c == '_' || c == '.' || c == '~') {
            escaped << c;
        } else if (c == ' ') {
            escaped << '_';
        } else {
            escaped << '%' << std::setw(2) << int(static_cast<unsigned char>(c));
        }
    }
    return escaped.str();
}

std::string NetflixResolver::ExtractNetflixId(const std::string& input) {
    if (input.empty()) return "";

    // 1. Netflix URL: /watch/81902147 or /title/81902147
    std::regex regUrl(R"(netflix\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?(?:watch|title)\/(\d{6,10}))", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, regUrl)) {
        return m[1].str();
    }

    // 2. Query / header parameters
    std::regex regParam(R"((?:movieid|titleid|viewable_id|netflix_id|netflixid|trackid)[=:_\-](\d{6,10}))", std::regex::icase);
    if (std::regex_search(input, m, regParam)) {
        return m[1].str();
    }

    // 3. Filename patterns: 'NF_81902147', '81902147.mp4'
    std::regex regFn(R"((?:netflix\.com\/(?:title|watch)\/|(?:OmniStream|NF|Netflix)[_\-]|_|^|\b)(\d{7,10})(?:\?|[^\d]|$))", std::regex::icase);
    if (std::regex_search(input, m, regFn)) {
        return m[1].str();
    }

    return "";
}

std::string NetflixResolver::ExtractImdbId(const std::string& input) {
    if (input.empty()) return "";
    std::regex reg(R"(\b(tt\d{7,10})\b)", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, reg)) {
        std::string id = m[1].str();
        std::transform(id.begin(), id.end(), id.begin(), ::tolower);
        return id;
    }
    return "";
}

std::string NetflixResolver::ExtractTmdbId(const std::string& input) {
    if (input.empty()) return "";
    // 1. Direct numeric string (3 to 9 digits)
    std::string trimmed = input;
    trimmed.erase(0, trimmed.find_first_not_of(" \t\r\n"));
    trimmed.erase(trimmed.find_last_not_of(" \t\r\n") + 1);
    if (!trimmed.empty() && trimmed.size() >= 3 && trimmed.size() <= 9 &&
        trimmed.find_first_not_of("0123456789") == std::string::npos) {
        return trimmed;
    }
    // 2. URL pattern
    std::regex regUrl(R"(themoviedb\.org\/(?:movie|tv)\/(\d+))", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, regUrl)) {
        return m[1].str();
    }
    // 3. Parameter pattern
    std::regex regParam(R"((?:tmdb|tmdb_id|tmdbid)[=:_\-](\d+))", std::regex::icase);
    if (std::regex_search(input, m, regParam)) {
        return m[1].str();
    }
    return "";
}

std::string NetflixResolver::ExtractEpisodeTag(const std::string& input) {
    if (input.empty()) return "";

    // 1. Matches S01E02 or S1E2
    std::regex regSE(R"(\bS(\d{1,2})E(\d{1,2})\b)", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, regSE)) {
        int s = std::stoi(m[1].str());
        int e = std::stoi(m[2].str());
        std::ostringstream ss;
        ss << "S" << std::setw(2) << std::setfill('0') << s
           << "E" << std::setw(2) << std::setfill('0') << e;
        return ss.str();
    }

    // 2. Matches Season 1 Episode 2
    std::regex regFull(R"(\bSeason\s*(\d+)\s*(?:Episode|Chapter)\s*(\d+)\b)", std::regex::icase);
    if (std::regex_search(input, m, regFull)) {
        int s = std::stoi(m[1].str());
        int e = std::stoi(m[2].str());
        std::ostringstream ss;
        ss << "S" << std::setw(2) << std::setfill('0') << s
           << "E" << std::setw(2) << std::setfill('0') << e;
        return ss.str();
    }

    return "";
}

std::string NetflixResolver::SanitizeFilename(const std::string& rawName) {
    std::string safe = rawName;
    const std::string badChars = "<>:\"/\\|?*";
    for (char& c : safe) {
        if (badChars.find(c) != std::string::npos || static_cast<unsigned char>(c) < 32) {
            c = '_';
        }
    }
    // Trim spaces and periods from ends
    safe.erase(0, safe.find_first_not_of(" ."));
    safe.erase(safe.find_last_not_of(" .") + 1);

    if (safe.empty()) safe = "OmniStream_Download";
    if (safe.size() > 180) safe = safe.substr(0, 180);
    return safe;
}

std::string NetflixResolver::GetNonConflictingPath(const std::string& targetPath) {
    if (!std::filesystem::exists(targetPath)) {
        return targetPath;
    }

    std::filesystem::path p(targetPath);
    std::string parentDir = p.parent_path().string();
    std::string stem = p.stem().string();
    std::string ext = p.extension().string();

    int counter = 2;
    while (true) {
        std::filesystem::path nextPath = std::filesystem::path(parentDir) / (stem + " (" + std::to_string(counter) + ")" + ext);
        if (!std::filesystem::exists(nextPath)) {
            return nextPath.string();
        }
        counter++;
    }
}

std::string NetflixResolver::ResolveOnlineTitle(const std::string& netflixId) {
    if (netflixId.empty()) return "";

    std::string url = "https://www.netflix.com/title/" + netflixId;
    HttpClient client("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36");
    HttpResponse res = client.Get(url);

    if (res.IsSuccess()) {
        std::string html = res.Text();
        std::regex titleRegex(R"(<title>([^<]+)<\/title>)", std::regex::icase);
        std::smatch m;
        if (std::regex_search(html, m, titleRegex)) {
            std::string fullTitle = m[1].str();
            size_t barPos = fullTitle.find('|');
            if (barPos != std::string::npos) {
                fullTitle = fullTitle.substr(0, barPos);
            }
            return SanitizeFilename(fullTitle);
        }
    }

    return "Netflix_" + netflixId;
}

std::string NetflixResolver::ResolveOnlineImdbId(const std::string& title) {
    if (title.empty()) return "";

    // Clean title for search
    std::string clean = title;
    // Remove (2024), etc.
    std::regex regParen(R"(\s*\([^)]*\))");
    clean = std::regex_replace(clean, regParen, "");
    // Remove S01E01, etc.
    std::regex regEp(R"(\s*S\d{1,2}E\d{1,2}.*)", std::regex::icase);
    clean = std::regex_replace(clean, regEp, "");
    clean.erase(0, clean.find_first_not_of(" -:_"));
    clean.erase(clean.find_last_not_of(" -:_") + 1);

    if (clean.empty()) return "";

    std::string slug = UrlEncodeSlug(clean);
    std::string url = "https://v3.sg.media-imdb.com/suggestion/x/" + slug + ".json";

    HttpClient client("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
    HttpResponse res = client.Get(url);
    if (res.IsSuccess()) {
        std::string body = res.Text();
        std::regex regTt("\"id\"\\s*:\\s*\"(tt\\d{7,10})\"", std::regex::icase);
        std::smatch m;
        if (std::regex_search(body, m, regTt)) {
            std::string imdbId = m[1].str();
            std::transform(imdbId.begin(), imdbId.end(), imdbId.begin(), ::tolower);
            return imdbId;
        }
    }
    return "";
}

std::string NetflixResolver::ResolveOnlineTmdbId(const std::string& imdbId, const std::string& title) {
    // 1. Try Wikidata mapping from IMDb ID (100% precision)
    if (!imdbId.empty() && imdbId.rfind("tt", 0) == 0) {
        std::string query = "SELECT ?tmdb WHERE { ?item wdt:P345 \"" + imdbId + "\" . { ?item wdt:P4947 ?tmdb } UNION { ?item wdt:P4983 ?tmdb } }";
        std::string url = "https://query.wikidata.org/sparql?query=" + UrlEncodeSlug(query) + "&format=json";
        HttpClient client("OmniStreamPro/2.5 (contact@omnistream.pro)");
        HttpResponse res = client.Get(url);
        if (res.IsSuccess()) {
            std::string body = res.Text();
            std::regex regVal("\"value\"\\s*:\\s*\"(\\d+)\"");
            std::smatch m;
            if (std::regex_search(body, m, regVal)) {
                return m[1].str();
            }
        }
    }

    // 2. Fallback search via title
    if (!title.empty()) {
        std::string clean = title;
        std::regex regParen(R"(\s*\([^)]*\))");
        clean = std::regex_replace(clean, regParen, "");
        std::regex regEp(R"(\s*S\d{1,2}E\d{1,2}.*)", std::regex::icase);
        clean = std::regex_replace(clean, regEp, "");
        clean.erase(0, clean.find_first_not_of(" -:_"));
        clean.erase(clean.find_last_not_of(" -:_") + 1);

        if (!clean.empty()) {
            std::string url = "https://lite.duckduckgo.com/lite/";
            std::string q = "\"" + clean + "\" site:themoviedb.org";
            std::string postData = "q=" + UrlEncodeSlug(q);
            HttpClient client("Mozilla/5.0 (Windows NT 10.0; Win64; x64)");
            HttpResponse res = client.Post(url, postData, "application/x-www-form-urlencoded");
            if (res.IsSuccess()) {
                std::string body = res.Text();
                std::regex regTmdb(R"(themoviedb\.org\/(?:movie|tv)\/(\d+))", std::regex::icase);
                std::smatch m;
                if (std::regex_search(body, m, regTmdb)) {
                    return m[1].str();
                }
            }
        }
    }

    return "";
}

std::string NetflixResolver::ResolveMediaRename(
    const std::string& mode,
    const std::string& inputText,
    const std::string& customTitle,
    const std::string& netflixId,
    const std::string& imdbId,
    const std::string& tmdbId,
    std::function<void(const std::string&)> logCallback
) {
    auto log = [&](const std::string& msg) {
        if (logCallback) logCallback(msg);
    };

    if (mode != "netflix_rename" && mode != "imdb_rename" && mode != "tmdb_rename") {
        return "";
    }

    // Detect episode tag if present
    std::string epTag = ExtractEpisodeTag(customTitle);
    if (epTag.empty()) epTag = ExtractEpisodeTag(inputText);
    std::string epSuffix = epTag.empty() ? "" : ("_" + epTag);

    if (mode == "netflix_rename") {
        std::string nid = !netflixId.empty() ? netflixId : ExtractNetflixId(inputText);
        if (nid.empty()) nid = ExtractNetflixId(customTitle);

        if (!nid.empty()) {
            std::string result = nid + epSuffix;
            log("[Netflix Rename] Successfully identified Netflix ID: " + result);
            return result;
        }
        log("[Netflix Rename] Notice: No Netflix ID could be extracted from input.");
        return "";
    }

    if (mode == "imdb_rename") {
        std::string directImdb = !imdbId.empty() ? imdbId : ExtractImdbId(inputText);
        if (directImdb.empty()) directImdb = ExtractImdbId(customTitle);
        if (directImdb.empty() && !netflixId.empty()) directImdb = ExtractImdbId(netflixId);

        if (!directImdb.empty()) {
            std::string result = directImdb + epSuffix;
            log("[IMDb Rename] Using identified IMDb ID: " + result);
            return result;
        }

        // Online lookup
        std::string searchTitle = IsGenericStreamName(customTitle) ? "" : customTitle;
        if (searchTitle.empty()) {
            std::string nid = ExtractNetflixId(inputText);
            if (!nid.empty()) {
                searchTitle = ResolveOnlineTitle(nid);
            }
        }

        if (!searchTitle.empty()) {
            log("[IMDb Rename] Querying IMDb metadata for title: '" + searchTitle + "'...");
            std::string resolved = ResolveOnlineImdbId(searchTitle);
            if (!resolved.empty()) {
                std::string result = resolved + epSuffix;
                log("[IMDb Rename] Successfully resolved IMDb ID: " + result);
                return result;
            }
        }
        log("[IMDb Rename] Notice: Could not resolve IMDb ID for title.");
        return "";
    }

    if (mode == "tmdb_rename") {
        std::string directTmdb = !tmdbId.empty() ? tmdbId : ExtractTmdbId(inputText);
        if (directTmdb.empty()) directTmdb = ExtractTmdbId(customTitle);

        if (!directTmdb.empty()) {
            std::string result = directTmdb + epSuffix;
            log("[TMDB Rename] Using identified TMDB ID: " + result);
            return result;
        }

        // Try mapping via IMDb ID or title
        std::string iid = !imdbId.empty() ? imdbId : ExtractImdbId(inputText);
        if (iid.empty()) iid = ExtractImdbId(customTitle);

        std::string searchTitle = IsGenericStreamName(customTitle) ? "" : customTitle;
        if (searchTitle.empty()) {
            std::string nid = ExtractNetflixId(inputText);
            if (!nid.empty()) {
                searchTitle = ResolveOnlineTitle(nid);
            }
        }

        if (iid.empty() && !searchTitle.empty()) {
            iid = ResolveOnlineImdbId(searchTitle);
        }

        log("[TMDB Rename] Querying TMDB ID metadata...");
        std::string resolved = ResolveOnlineTmdbId(iid, searchTitle);
        if (!resolved.empty()) {
            std::string result = resolved + epSuffix;
            log("[TMDB Rename] Successfully resolved TMDB ID: " + result);
            return result;
        }

        log("[TMDB Rename] Notice: Could not resolve TMDB ID.");
        return "";
    }

    return "";
}

} // namespace OmniStream
