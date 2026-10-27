#include "netflix_resolver.hpp"
#include "http_client.hpp"
#include <iomanip>
#include <sstream>
#include <unordered_set>
#include <unordered_map>
#include <mutex>
#include <regex>
#include <algorithm>
#include <filesystem>
#include <cstdio>

namespace OmniStream {

static std::unordered_map<std::string, std::string> s_netflixCache;
static std::mutex s_cacheMutex;

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

static std::string HtmlUnescape(const std::string& input) {
    std::string s = input;
    static const std::vector<std::pair<std::string, std::string>> entities = {
        {"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"}, {"&quot;", "\""},
        {"&#39;", "'"}, {"&apos;", "'"}, {"&#x27;", "'"}, {"&#x2F;", "/"},
        {"&#32;", " "}, {"&nbsp;", " "}
    };
    for (const auto& [from, to] : entities) {
        size_t pos = 0;
        while ((pos = s.find(from, pos)) != std::string::npos) {
            s.replace(pos, from.length(), to);
            pos += to.length();
        }
    }
    return s;
}

static std::string UnescapeHexStrings(const std::string& input) {
    std::string s = input;
    std::regex hexReg(R"(\\x([0-9a-fA-F]{2}))");
    std::string res;
    auto words_begin = std::sregex_iterator(s.begin(), s.end(), hexReg);
    auto words_end = std::sregex_iterator();
    size_t lastPos = 0;
    for (auto it = words_begin; it != words_end; ++it) {
        std::smatch m = *it;
        res += s.substr(lastPos, m.position() - lastPos);
        int ch = std::stoi(m[1].str(), nullptr, 16);
        res += static_cast<char>(ch);
        lastPos = m.position() + m.length();
    }
    res += s.substr(lastPos);
    return res;
}

static std::string CleanScrapedTitle(const std::string& raw) {
    std::string t = HtmlUnescape(raw);
    std::regex tagReg("<[^>]+>");
    t = std::regex_replace(t, tagReg, "");

    t.erase(0, t.find_first_not_of(" \t\r\n"));
    t.erase(t.find_last_not_of(" \t\r\n") + 1);

    std::regex rWatch(R"(^Watch\s+)", std::regex::icase);
    t = std::regex_replace(t, rWatch, "");
    std::regex rNfBar(R"(\s*\|\s*Netflix.*$)", std::regex::icase);
    t = std::regex_replace(t, rNfBar, "");
    std::regex rNfDash(R"(\s*-\s*Netflix.*$)", std::regex::icase);
    t = std::regex_replace(t, rNfDash, "");
    std::regex rSite(R"(\s*\|\s*Official Site.*$)", std::regex::icase);
    t = std::regex_replace(t, rSite, "");

    t.erase(0, t.find_first_not_of(" \t\r\n"));
    t.erase(t.find_last_not_of(" \t\r\n") + 1);

    std::string lower = t;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    static const std::vector<std::string> genericPhrases = {
        "netflix", "sign in", "sign up", "sign-in", "sign-up", "login", "tv code",
        "home", "browse", "watch tv shows online", "watch movies online",
        "help center", "customer service", "account", "terms of use", "privacy statement",
        "how to keep your account", "reset your password", "page not found", "error", "404"
    };
    for (const auto& phrase : genericPhrases) {
        if (lower == phrase || lower.find(phrase) != std::string::npos) {
            return "";
        }
    }
    return NetflixResolver::SanitizeFilename(t);
}

static std::string FetchUrlContent(const std::string& url, const std::string& userAgent) {
    // 1. Try curl.exe with 4-second timeout (handles Googlebot crawl headers & SSR redirects)
    std::string cmd = "curl.exe -s -L --max-time 4 -A \"" + userAgent + "\" -H \"Accept-Language: en-US,en;q=0.9\" \"" + url + "\"";
    FILE* pipe = _popen(cmd.c_str(), "rb");
    if (pipe) {
        std::string result;
        char buf[8192];
        while (size_t bytes = fread(buf, 1, sizeof(buf), pipe)) {
            result.append(buf, bytes);
        }
        _pclose(pipe);
        if (!result.empty()) {
            return result;
        }
    }

    // 2. Fallback to native WinHTTP HttpClient
    HttpClient client(userAgent);
    std::map<std::string, std::string> headers = {
        {"Accept-Language", "en-US,en;q=0.9"},
        {"Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    };
    HttpResponse res = client.Get(url, headers);
    if (res.IsSuccess()) {
        return res.Text();
    }
    return "";
}

static std::pair<std::string, std::string> FetchImdbMetadata(const std::string& title) {
    if (title.empty()) return {"", ""};
    std::string clean = title;
    std::regex regParen(R"(\s*\([^)]*\))");
    clean = std::regex_replace(clean, regParen, "");
    clean.erase(0, clean.find_first_not_of(" -:_"));
    clean.erase(clean.find_last_not_of(" -:_") + 1);
    if (clean.empty()) return {"", ""};

    std::string slug = UrlEncodeSlug(clean);
    std::string url = "https://v3.sg.media-imdb.com/suggestion/x/" + slug + ".json";

    std::string body = FetchUrlContent(url, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
    if (!body.empty()) {
        std::regex regL("\"l\"\\s*:\\s*\"([^\"]+)\"");
        std::regex regY("\"y\"\\s*:\\s*(\\d{4})");
        std::smatch mL, mY;
        std::string foundTitle, foundYear;
        if (std::regex_search(body, mL, regL)) foundTitle = mL[1].str();
        if (std::regex_search(body, mY, regY)) foundYear = mY[1].str();
        if (!foundTitle.empty()) {
            return {foundTitle, foundYear};
        }
    }
    return {"", ""};
}

static std::string FetchWikipediaYear(const std::string& title) {
    if (title.empty()) return "";
    std::string clean = title;
    std::regex regParen(R"(\s*\([^)]*\))");
    clean = std::regex_replace(clean, regParen, "");
    clean.erase(0, clean.find_first_not_of(" -:_"));
    clean.erase(clean.find_last_not_of(" -:_") + 1);
    if (clean.empty()) return "";

    std::string url = "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=" + UrlEncodeSlug(clean) + "&utf8=&format=json";
    std::string body = FetchUrlContent(url, "OmniStreamPro/2.6");
    if (!body.empty()) {
        std::regex regYear(R"(\b(19\d{2}|20\d{2})\b)");
        std::smatch m;
        if (std::regex_search(body, m, regYear)) {
            return m[1].str();
        }
    }
    return "";
}

std::string NetflixResolver::ExtractNetflixId(const std::string& input) {
    if (input.empty()) return "";

    // 1. Netflix URL: /watch/81902147 or /title/81902147
    std::regex regUrl(R"(netflix\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?(?:watch|title)\/(\d{6,10}))", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, regUrl)) {
        return m[1].str();
    }

    // 2. Query / header parameter patterns or NF prefix
    std::regex regParam(R"((?:movieid|titleid|viewable_id|netflix_id|netflixid|trackid|nf)[=:_\-](\d{6,10}))", std::regex::icase);
    if (std::regex_search(input, m, regParam)) {
        return m[1].str();
    }

    // 3. Filename patterns: 'OmniStream_81902147', 'NF_81902147', '81902147.mp4'
    std::regex regFn(R"((?:OmniStream[_\-]|NF[_\-]|\b)(\d{6,10})(?:_\d+|\.\w+)?\b)", std::regex::icase);
    if (std::regex_search(input, m, regFn)) {
        return m[1].str();
    }

    // 4. Standalone or non-alphanumeric bounded 6-10 digit number
    std::regex regNum(R"((?:^|[^0-9a-zA-Z])(\d{6,10})(?:[^0-9a-zA-Z]|$))");
    if (std::regex_search(input, m, regNum)) {
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
    std::string trimmed = input;
    trimmed.erase(0, trimmed.find_first_not_of(" \t\r\n"));
    trimmed.erase(trimmed.find_last_not_of(" \t\r\n") + 1);
    if (!trimmed.empty() && trimmed.size() >= 3 && trimmed.size() <= 9 &&
        trimmed.find_first_not_of("0123456789") == std::string::npos) {
        return trimmed;
    }
    std::regex regUrl(R"(themoviedb\.org\/(?:movie|tv)\/(\d+))", std::regex::icase);
    std::smatch m;
    if (std::regex_search(input, m, regUrl)) {
        return m[1].str();
    }
    std::regex regParam(R"((?:tmdb|tmdb_id|tmdbid)[=:_\-](\d+))", std::regex::icase);
    if (std::regex_search(input, m, regParam)) {
        return m[1].str();
    }
    return "";
}

std::string NetflixResolver::ExtractEpisodeTag(const std::string& input) {
    if (input.empty()) return "";

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

std::string NetflixResolver::ResolveOnlineTitle(
    const std::string& netflixId,
    std::function<void(const std::string&)> logCallback
) {
    auto log = [&](const std::string& msg) {
        if (logCallback) logCallback(msg);
    };

    std::string nid = netflixId;
    nid.erase(0, nid.find_first_not_of(" \t\r\n"));
    nid.erase(nid.find_last_not_of(" \t\r\n") + 1);

    if (nid.empty() || nid.find_first_not_of("0123456789") != std::string::npos) {
        return "";
    }

    {
        std::lock_guard<std::mutex> lock(s_cacheMutex);
        auto it = s_netflixCache.find(nid);
        if (it != s_netflixCache.end()) {
            log("[Netflix Resolver] Using cached title for ID " + nid + ": '" + it->second + "'");
            return it->second;
        }
    }

    log("[Netflix Resolver] Querying metadata sources for Netflix ID: " + nid + "...");

    std::string title;
    std::string year;
    std::string episodeTag;

    // ── Source 1: Direct Netflix Title Page via Googlebot Crawl Headers ─────────
    std::string page = FetchUrlContent("https://www.netflix.com/title/" + nid, "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)");
    if (!page.empty()) {
        page = UnescapeHexStrings(page);

        // Step A: Show / Movie title from <h1>
        std::regex h1Reg(R"(<h1[^>]*>(.*?)<\/h1>)", std::regex::icase);
        std::smatch mH1;
        if (std::regex_search(page, mH1, h1Reg)) {
            std::string cand = CleanScrapedTitle(mH1[1].str());
            if (!cand.empty()) {
                title = cand;
            }
        }

        // Step B: Detect if nid is an episode in embedded JSON
        std::regex vidReg("\"videoId\"\\s*:\\s*" + nid);
        std::smatch mVid;
        size_t idx = std::string::npos;
        if (std::regex_search(page, mVid, vidReg)) {
            idx = mVid.position();
        } else {
            idx = page.find(nid);
        }

        if (idx != std::string::npos) {
            size_t fwdLen = std::min<size_t>(page.size() - idx, 800);
            std::string forward = page.substr(idx, fwdLen);

            size_t backStart = (idx > 15000) ? idx - 15000 : 0;
            std::string back = page.substr(backStart, idx - backStart);

            // Episode number
            std::regex epNumReg("\"number\"\\s*:\\s*(\\d+)");
            std::smatch mEpNum;
            int epNum = 0;
            if (std::regex_search(forward, mEpNum, epNumReg)) {
                epNum = std::stoi(mEpNum[1].str());
            }

            // Episode title
            std::regex epTitleReg("\"title\"\\s*:\\s*\"([^\"]+)\"");
            std::smatch mEpTitle;
            std::string epTitle;
            if (std::regex_search(forward, mEpTitle, epTitleReg)) {
                std::string rawEp = mEpTitle[1].str();
                size_t bPos = 0;
                while ((bPos = rawEp.find("\\\"", bPos)) != std::string::npos) {
                    rawEp.replace(bPos, 2, "\"");
                    bPos += 1;
                }
                rawEp = UnescapeHexStrings(rawEp);
                std::regex seasonOnly(R"(^Season\s*\d+$)", std::regex::icase);
                if (!rawEp.empty() && !std::regex_match(rawEp, seasonOnly)) {
                    epTitle = SanitizeFilename(rawEp);
                }
            }

            // Season number
            int seasonNum = 0;
            std::regex seasonReg("Season\\s+(\\d+)", std::regex::icase);
            auto s_begin = std::sregex_iterator(back.begin(), back.end(), seasonReg);
            auto s_end = std::sregex_iterator();
            for (auto it = s_begin; it != s_end; ++it) {
                seasonNum = std::stoi((*it)[1].str());
            }

            if (seasonNum == 0) {
                size_t seasonsStart = back.rfind("\"seasons\"");
                if (seasonsStart != std::string::npos) {
                    std::string afterSeasons = back.substr(seasonsStart);
                    std::regex edgeReg("SeasonEdge");
                    auto e_begin = std::sregex_iterator(afterSeasons.begin(), afterSeasons.end(), edgeReg);
                    auto e_end = std::sregex_iterator();
                    int edgeCount = 0;
                    for (auto it = e_begin; it != e_end; ++it) {
                        edgeCount++;
                    }
                    if (edgeCount > 0) seasonNum = edgeCount;
                }
            }

            if (seasonNum > 0 && epNum > 0) {
                std::ostringstream ss;
                ss << "S" << std::setw(2) << std::setfill('0') << seasonNum
                   << "E" << std::setw(2) << std::setfill('0') << epNum;
                if (!epTitle.empty()) {
                    episodeTag = ss.str() + " - " + epTitle;
                } else {
                    episodeTag = ss.str();
                }
            } else if (epNum > 0 && !epTitle.empty()) {
                std::ostringstream ss;
                ss << "E" << std::setw(2) << std::setfill('0') << epNum << " - " << epTitle;
                episodeTag = ss.str();
            }
        } else {
            // Step B Fallback: parse <title> tag for Season/Episode
            std::regex tagRegex(R"(<title>([^<]+)<\/title>)", std::regex::icase);
            std::smatch mTitleTag;
            if (std::regex_search(page, mTitleTag, tagRegex)) {
                std::string rawTag = HtmlUnescape(mTitleTag[1].str());
                std::regex epMatch("(?:Season|Part)\\s*(\\d+).*?(?:Episode|Chapter)\\s*(\\d+)", std::regex::icase);
                std::smatch mEp;
                if (std::regex_search(rawTag, mEp, epMatch)) {
                    int s = std::stoi(mEp[1].str());
                    int e = std::stoi(mEp[2].str());
                    std::ostringstream ss;
                    ss << "S" << std::setw(2) << std::setfill('0') << s
                       << "E" << std::setw(2) << std::setfill('0') << e;
                    episodeTag = ss.str();
                }
            }
        }

        // Step C: Year extraction
        if (!title.empty()) {
            size_t titleIdx = page.find(title);
            if (titleIdx != std::string::npos) {
                size_t winLen = std::min<size_t>(page.size() - titleIdx, 3000);
                std::string window = page.substr(titleIdx, winLen);
                std::regex yearLi("<li[^>]*>\\s*(19\\d{2}|20\\d{2})\\s*<\\/li>", std::regex::icase);
                std::smatch mYear;
                if (std::regex_search(window, mYear, yearLi)) {
                    year = mYear[1].str();
                } else {
                    std::regex yearGen(">\\s*(19\\d{2}|20\\d{2})\\s*<");
                    if (std::regex_search(window, mYear, yearGen)) {
                        year = mYear[1].str();
                    }
                }
            }
        }
    }

    // ── Source 2: DuckDuckGo Search Fallback ("{id} netflix") ───────────────────
    if (title.empty()) {
        std::string ddgUrl = "https://lite.duckduckgo.com/lite/";
        std::string postData = "q=" + UrlEncodeSlug(nid + " netflix");
        HttpClient ddgClient("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        HttpResponse ddgRes = ddgClient.Post(ddgUrl, postData, "application/x-www-form-urlencoded");
        if (ddgRes.IsSuccess()) {
            std::string content = ddgRes.Text();
            std::regex linkReg("class=['\"]result-link['\"][^>]*>(.*?)<\\/a>", std::regex::icase);
            auto l_begin = std::sregex_iterator(content.begin(), content.end(), linkReg);
            auto l_end = std::sregex_iterator();
            for (auto it = l_begin; it != l_end; ++it) {
                std::string rawLink = (*it)[1].str();
                std::string cleaned = CleanScrapedTitle(rawLink);
                if (!cleaned.empty()) {
                    title = cleaned;
                    std::regex ymReg("\\b(19\\d{2}|20\\d{2})\\b");
                    std::smatch mYm;
                    if (std::regex_search(rawLink, mYm, ymReg)) {
                        year = mYm[1].str();
                    }
                    break;
                }
            }
        }
    }

    if (title.empty()) {
        log("[Netflix Resolver] Could not identify title online for ID " + nid + ".");
        return "";
    }

    // ── Source 3: IMDb Suggestion Verification for Official Title & Year ────────
    auto [imdbTitle, imdbYear] = FetchImdbMetadata(title);
    if (!imdbTitle.empty()) {
        if (year.empty()) {
            year = imdbYear;
        }
        std::string lowerImdb = imdbTitle;
        std::string lowerTitle = title;
        std::transform(lowerImdb.begin(), lowerImdb.end(), lowerImdb.begin(), ::tolower);
        std::transform(lowerTitle.begin(), lowerTitle.end(), lowerTitle.begin(), ::tolower);
        if (lowerImdb == lowerTitle) {
            title = imdbTitle;
        }
    }

    // ── Source 4: Wikipedia Fallback for Year ───────────────────────────────────
    if (year.empty()) {
        year = FetchWikipediaYear(title);
    }

    // ── Assemble Final Output: "Movie Title (Year)" or "Series SxxExx - Title (Year)"
    std::regex hasYearReg("\\(\\s*(?:19\\d{2}|20\\d{2})\\s*\\)");
    bool hasYear = std::regex_search(title, hasYearReg);

    std::string finalName = title;
    if (!episodeTag.empty() && title.find(episodeTag) == std::string::npos) {
        finalName += " " + episodeTag;
    }
    if (!year.empty() && !hasYear) {
        finalName += " (" + year + ")";
    }

    finalName = SanitizeFilename(finalName);
    {
        std::lock_guard<std::mutex> lock(s_cacheMutex);
        s_netflixCache[nid] = finalName;
    }

    log("[Netflix Resolver] Successfully identified: '" + finalName + "'");
    return finalName;
}

std::string NetflixResolver::ResolveOnlineImdbId(const std::string& title) {
    if (title.empty()) return "";

    std::string clean = title;
    std::regex regParen(R"(\s*\([^)]*\))");
    clean = std::regex_replace(clean, regParen, "");
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

    std::string epTag = ExtractEpisodeTag(customTitle);
    if (epTag.empty()) epTag = ExtractEpisodeTag(inputText);
    std::string epSuffix = epTag.empty() ? "" : ("_" + epTag);

    if (mode == "netflix_rename") {
        std::string nid = !netflixId.empty() ? netflixId : ExtractNetflixId(inputText);
        if (nid.empty()) nid = ExtractNetflixId(customTitle);

        if (!nid.empty()) {
            // Check if customTitle is an explicit custom title provided by user (not numeric, not generic)
            if (!customTitle.empty() && !IsGenericStreamName(customTitle) &&
                customTitle.find_first_not_of("0123456789") != std::string::npos &&
                customTitle.find("http") == std::string::npos &&
                customTitle != "OmniStream_Download" &&
                customTitle.find("OmniStream_") != 0) {
                log("[Netflix Rename] User custom title preserved: '" + customTitle + "'");
                return customTitle;
            }

            log("[Netflix Rename] Detected Netflix ID: " + nid);
            log("[Netflix Rename] Searching online for official movie/series title...");
            std::string resolved = ResolveOnlineTitle(nid, logCallback);
            if (!resolved.empty()) {
                log("[Netflix Rename] Successfully identified title: '" + resolved + "'");
                return resolved;
            } else {
                log("[Netflix Rename] Notice: Could not resolve title online. Using Netflix ID.");
                return nid + epSuffix;
            }
        }
        log("[Netflix Rename] Notice: No Netflix ID detected in source.");
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
