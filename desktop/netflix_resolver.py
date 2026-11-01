"""
OmniStream Pro v2.3 - Netflix Title Resolver & Intelligent Auto-Renamer
Identifies Netflix IDs from stream URLs, cURLs, headers, or filenames,
looks up the official movie/series name and release year online via multi-layer
metadata sources (Netflix Title Page, IMDb, DuckDuckGo, Wikipedia), and safely
renames completed downloads without overwriting existing files.

Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import re
import html
import json
import urllib.request
import urllib.parse
import http.client
from typing import Optional, Callable, Dict, Any, Tuple

# Valid Windows filename characters only (strip \ / : * ? " < > |)
_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')


def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for Windows and Unix filesystems."""
    if not name:
        return ""
    cleaned = _INVALID_FILENAME_CHARS.sub("", name).strip()
    cleaned = re.sub(r'\s+', " ", cleaned)
    # Windows doesn't allow trailing dots or spaces
    cleaned = cleaned.rstrip(". ")
    return cleaned


# Global in-memory cache to prevent redundant network lookups
_RESOLVED_CACHE = {}


def extract_netflix_id(text: str) -> Optional[str]:
    """
    Extract a 6-10 digit Netflix ID from URLs, referers, filenames, or cURL commands.
    Examples:
      - 'https://www.netflix.com/watch/81902147' -> '81902147'
      - 'https://www.netflix.com/title/81902147' -> '81902147'
      - '81902147.mp4' -> '81902147'
      - 'OmniStream_81902147' -> '81902147'
      - '-H "Referer: https://www.netflix.com/watch/81902147"' -> '81902147'
      - 'movieid=81902147' -> '81902147'
    """
    if not text:
        return None

    raw = str(text)

    # 1. Netflix URL patterns: /watch/81902147 or /title/81902147 (with optional region prefix)
    url_m = re.search(
        r'netflix\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:watch|title)/(\d{6,10})',
        raw, re.IGNORECASE
    )
    if url_m:
        return url_m.group(1)

    # 2. Query / header parameter patterns: movieid=81902147, titleid=81902147, etc.
    param_m = re.search(
        r'(?:movieid|titleid|viewable_id|netflix_id|netflixid|trackid)[=:_\-](\d{6,10})',
        raw, re.IGNORECASE
    )
    if param_m:
        return param_m.group(1)

    # 3. Filename patterns: 'OmniStream_81902147', '81902147.mp4', '81902147_1.mp4'
    fn_m = re.search(
        r'(?:OmniStream[_\-]|\b)(\d{6,10})(?:_\d+|\.\w+)?\b',
        raw, re.IGNORECASE
    )
    if fn_m:
        return fn_m.group(1)

    # 4. Standalone 6-10 digit number
    standalone_m = re.search(r'\b(\d{6,10})\b', raw)
    if standalone_m:
        return standalone_m.group(1)

    return None


def fetch_imdb_metadata(title: str) -> Optional[dict]:
    """
    Query IMDb's public suggestion endpoint to verify title and get official release year.
    Returns dict with 'title' and 'year' if found.
    """
    try:
        clean = re.sub(r'\(.*?\)', '', title).strip()
        slug = urllib.parse.quote(clean.lower().replace(" ", "_"))
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{slug}.json"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            entries = data.get("d", [])
            for entry in entries:
                t = entry.get("l")
                y = entry.get("y")
                q = (entry.get("q") or "").lower()
                # Accept movies, TV series, mini-series, etc.
                if t and y and (q in ("feature", "tv series", "tv mini-series", "tv movie", "video", "") or not q):
                    return {"title": t, "year": str(y)}
    except Exception:
        pass
    return None


def fetch_wikipedia_year(title: str) -> Optional[str]:
    """Fallback search on Wikipedia API for release year."""
    try:
        clean = re.sub(r'\(.*?\)', '', title).strip()
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean)}&utf8=&format=json"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "OmniStreamPro/2.2"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("query", {}).get("search", [])[:3]:
                snippet = item.get("snippet", "")
                years = re.findall(r'\b(19\d{2}|20\d{2})\b', snippet)
                if years:
                    return years[0]
    except Exception:
        pass
    return None


def _clean_scraped_title(raw_title: str) -> str:
    """Normalize and clean raw title string scraped from web pages or search engines."""
    t = html.unescape(raw_title).strip()
    t = re.sub(r'<[^>]+>', '', t).strip()
    # Strip common Netflix title wrappers
    t = re.sub(r'^Watch\s+', '', t, flags=re.I).strip()
    t = re.sub(r'\s*\|\s*Netflix.*$', '', t, flags=re.I).strip()
    t = re.sub(r'\s*-\s*Netflix.*$', '', t, flags=re.I).strip()
    t = re.sub(r'\s*\|\s*Official Site.*$', '', t, flags=re.I).strip()
    # Remove help center or generic page false positives
    lower = t.lower()
    generic_phrases = (
        "netflix", "sign in", "sign up", "sign-in", "sign-up", "login", "tv code",
        "home", "browse", "watch tv shows online", "watch movies online",
        "help center", "customer service", "account", "terms of use", "privacy statement",
        "how to keep your account", "reset your password", "page not found", "error", "404"
    )
    if any(p in lower for p in generic_phrases):
        return ""
    return sanitize_filename(t)


def resolve_netflix_title(
    netflix_id: str,
    log_callback: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    Identify and resolve the accurate movie or series name and release year for a given Netflix ID.
    Returns format: "Movie Title (Year)" (e.g. "Sonic the Hedgehog 3 (2024)")
    or None if identification failed.
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    nid = str(netflix_id).strip()
    if not nid or not nid.isdigit():
        return None

    if nid in _RESOLVED_CACHE:
        cached = _RESOLVED_CACHE[nid]
        _log(f"  [Netflix Resolver] Using cached title for ID {nid}: '{cached}'")
        return cached

    _log(f"  [Netflix Resolver] Querying metadata sources for Netflix ID: {nid}...")

    title: Optional[str] = None
    year: Optional[str] = None
    episode_tag: str = ""

    # ── Source 1: Direct Netflix Title Page via Googlebot Crawl Headers ─────────
    # NOTE: Episode IDs (e.g. 81948683) redirect to the show page.
    # The embedded JSON on the show page contains the videoId with full episode metadata.
    try:
        url = f"https://www.netflix.com/title/{nid}"
        page = ""

        # Prefer curl.exe for lightning fast HTTP/2 retrieval and bypass urllib SSL handshake delays
        try:
            import subprocess
            curl_res = subprocess.run(
                ["curl.exe", "-s", "-L", "--max-time", "4",
                 "-A", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                 "-H", "Accept-Language: en-US,en;q=0.9", url],
                capture_output=True, text=True, errors="ignore"
            )
            if curl_res.returncode == 0 and curl_res.stdout:
                page = curl_res.stdout
        except Exception:
            page = ""

        if not page:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            })
            with urllib.request.urlopen(req, timeout=4) as resp:
                try:
                    raw_bytes = resp.read()
                except http.client.IncompleteRead as e:
                    raw_bytes = e.partial
                page = raw_bytes.decode("utf-8", errors="ignore")

        # Unescape literal \x20, \x27 etc. in embedded JSON
        page = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), page)

        # ── Step A: Get the show/movie title from <h1> ───────────────────────
        h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.I)
        if h1_m:
            cand = _clean_scraped_title(h1_m.group(1))
            if cand:
                title = cand

        # ── Step B: Detect if the original nid is an episode in embedded JSON ─
        # Find the videoId JSON occurrence for accurate season/episode metadata
        m_vid = re.search(r'"videoId"\s*:\s*' + re.escape(nid), page)
        idx = m_vid.start() if m_vid else (page.find(nid) if nid in page else -1)

        if idx != -1:
            forward = page[idx: min(len(page), idx + 800)]
            back = page[max(0, idx - 15000): idx]

            # Extract episode number from forward JSON
            ep_num_m = re.search(r'"number"\s*:\s*(\d+)', forward)
            ep_num = int(ep_num_m.group(1)) if ep_num_m else None

            # Extract episode title from forward JSON ("title":"Chapter One...")
            ep_title = ""
            ep_title_m = re.search(r'"title"\s*:\s*"([^"]+)"', forward)
            if ep_title_m:
                raw_ep = ep_title_m.group(1).replace('\\"', '"').strip()
                raw_ep = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), raw_ep)
                if raw_ep and not re.match(r'^Season\s*\d+$', raw_ep, re.I):
                    ep_title = sanitize_filename(raw_ep)

            # Look backwards for the season number:
            # 1. Direct text e.g. "Season 2"
            s_nums = re.findall(r'Season\s+(\d+)', back)
            season_num = int(s_nums[-1]) if s_nums else None

            # 2. Modern Netflix GraphQL edges structure: count SeasonEdge before this episode
            if not season_num:
                seasons_start = back.rfind('"seasons"')
                if seasons_start != -1:
                    edges = re.findall(r'SeasonEdge', back[seasons_start:])
                    if edges:
                        season_num = len(edges)

            if season_num and ep_num:
                if ep_title:
                    episode_tag = f"S{season_num:02d}E{ep_num:02d} - {ep_title}"
                else:
                    episode_tag = f"S{season_num:02d}E{ep_num:02d}"
            elif ep_num and ep_title:
                episode_tag = f"E{ep_num:02d} - {ep_title}"
        else:
            # ── Step B fallback: parse <title> tag for Season/Episode ─────────
            title_tag_m = re.search(r'<title>(.*?)</title>', page, re.I)
            if title_tag_m:
                raw_tag = html.unescape(title_tag_m.group(1))
                ep_m = re.search(r'(?:Season|Part)\s*(\d+).*?(?:Episode|Chapter)\s*(\d+)', raw_tag, re.I)
                if ep_m:
                    season_num = int(ep_m.group(1))
                    ep_num = int(ep_m.group(2))
                    episode_tag = f"S{season_num:02d}E{ep_num:02d}"
                else:
                    s_only = re.search(r'(?:Season|Part)\s*(\d+)', raw_tag, re.I)
                    if s_only:
                        episode_tag = f"Season {s_only.group(1)}"

        # ── Step C: Extract year from metadata list near title ────────────────
        if title:
            idx = page.find(title)
            if idx != -1:
                window = page[idx:idx + 3000]
                year_m = re.search(r'<li[^>]*>\s*(19\d{2}|20\d{2})\s*</li>', window, re.I)
                if year_m:
                    year = year_m.group(1)
                else:
                    generic_ym = re.search(r'>\s*(19\d{2}|20\d{2})\s*<', window)
                    if generic_ym:
                        year = generic_ym.group(1)
    except Exception:
        pass

    # ── Source 2: DuckDuckGo Search ("{id} netflix") ──────────────────────────
    if not title:
        try:
            ddg_url = "https://lite.duckduckgo.com/lite/"
            data = urllib.parse.urlencode({"q": f"{nid} netflix"}).encode()
            req = urllib.request.Request(ddg_url, data=data, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            })
            with urllib.request.urlopen(req, timeout=6) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                # Look for link entries
                links = re.findall(r'class=[\'"]result-link[\'"][^>]*>(.*?)</a>', content, re.I)
                for l in links:
                    cleaned = _clean_scraped_title(l)
                    if cleaned:
                        # Must match movie/show format or have "Watch" or "Netflix" in context
                        if re.search(r'Watch\s+.*?\|\s*Netflix', l, re.I) or f"/{nid}" in content:
                            title = cleaned
                            ym = re.search(r'\b(19\d{2}|20\d{2})\b', l)
                            if ym:
                                year = ym.group(1)
                            break
        except Exception:
            pass

    if not title:
        _log(f"  [Netflix Resolver] Could not identify title online for ID {nid}.")
        return None

    # ── Source 3: IMDb Suggestion Verification for Official Title & Year ───────
    # Query IMDb to normalize casing and retrieve canonical release year
    imdb_meta = fetch_imdb_metadata(title)
    if imdb_meta:
        if not year:
            year = imdb_meta.get("year")
        # If IMDb title matches closely, prefer its clean canonical casing
        imdb_title = imdb_meta.get("title")
        if imdb_title and imdb_title.lower() == title.lower():
            title = imdb_title

    # ── Source 4: Wikipedia Fallback for Year ──────────────────────────────────
    if not year:
        year = fetch_wikipedia_year(title)

    # ── Assemble Final Output: "Movie Title (Year)" ─────────────────────────────
    # Check if year is already part of the title
    has_year = bool(re.search(r'\(\s*(?:19\d{2}|20\d{2})\s*\)', title))
    parts = [title]
    if episode_tag and episode_tag not in title:
        parts.append(episode_tag)
    if year and not has_year:
        parts.append(f"({year})")
    final_name = " ".join(parts)

    final_name = sanitize_filename(final_name)
    _RESOLVED_CACHE[nid] = final_name
    _log(f"  [Netflix Resolver] Successfully identified: '{final_name}'")
    return final_name


def get_non_conflicting_path(directory: str, filename_with_ext: str) -> str:
    """
    Ensure the target filename does not overwrite an existing file.
    If 'Sonic the Hedgehog 3 (2024).mp4' exists, returns
    'Sonic the Hedgehog 3 (2024) (1).mp4', etc.
    """
    dest_path = os.path.join(directory, filename_with_ext)
    if not os.path.exists(dest_path):
        return dest_path

    stem, ext = os.path.splitext(filename_with_ext)
    counter = 1
    while True:
        candidate_name = f"{stem} ({counter}){ext}"
        candidate_path = os.path.join(directory, candidate_name)
        if not os.path.exists(candidate_path):
            return candidate_path
        counter += 1


# ── Universal Media Metadata & Multi-Mode Filename Resolution ──────────────────
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "dca854d2a94fad34e4218bbea9a79231")
_TMDB_CACHE: Dict[str, Any] = {}
_MEDIA_META_CACHE: Dict[str, dict] = {}


def _tmdb_api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    """Execute a safe, cached GET request against TMDb v3 API."""
    if not TMDB_API_KEY:
        return None
    cache_key = f"{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
    if cache_key in _TMDB_CACHE:
        return _TMDB_CACHE[cache_key]

    p = {"api_key": TMDB_API_KEY}
    if params:
        p.update(params)
    url = f"https://api.themoviedb.org/3{endpoint}?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _TMDB_CACHE[cache_key] = data
            return data
    except Exception:
        return None


def extract_imdb_id(text: str) -> Optional[str]:
    """Extract an IMDb ID (e.g. 'tt1375666' or 'tt4593122') from text, URLs or parameters."""
    if not text:
        return None
    m = re.search(r'\b(tt\d{7,10})\b', str(text), re.IGNORECASE)
    return m.group(1).lower() if m else None


def extract_tmdb_id(text: str) -> Optional[Tuple[str, str]]:
    """Extract TMDb ID and media type ('movie' or 'tv') from URL or query text if present."""
    if not text:
        return None
    raw = str(text)
    m = re.search(r'themoviedb\.org/(movie|tv)/(\d+)', raw, re.IGNORECASE)
    if m:
        return m.group(2), m.group(1).lower()
    m2 = re.search(r'tmdb(?:_id)?[:=](\d+)', raw, re.IGNORECASE)
    if m2:
        return m2.group(1), "unknown"
    return None


def extract_season_episode(text: str) -> Optional[Tuple[str, int, int]]:
    """
    Extract Show Title, Season Number and Episode Number from titles/filenames.
    Supports formats:
      - 'Stranger Things S01E02'
      - 'Stranger.Things.S01E02.1080p.WEBRip'
      - 'Breaking Bad 1x02'
      - 'Show Season 1 Episode 2'
      - 'Show S01E02 - Episode Title (Year)'
    """
    if not text:
        return None
    raw = str(text)
    patterns = [
        r'^(.*?)[._\s-]+[sS](\d{1,2})[._\s-]*[eE](\d{1,3})(?:[._\s-]+(.*?))?$',
        r'^(.*?)[._\s-]+(\d{1,2})x(\d{1,3})(?:[._\s-]+(.*?))?$',
        r'^(.*?)[._\s-]+[sS]eason[._\s-]+(\d{1,2})[._\s-]+[eE]pisode[._\s-]+(\d{1,3})(?:[._\s-]+(.*?))?$',
    ]
    for p in patterns:
        m = re.match(p, raw.strip(), re.IGNORECASE)
        if m:
            clean_title = m.group(1).replace(".", " ").replace("_", " ").strip()
            # Clean common release and resolution tags
            clean_title = re.sub(
                r'\b(1080p|720p|480p|2160p|4k|web-dl|webrip|bluray|x264|x265|hevc|aac|h\.264|h\.265)\b.*$',
                '', clean_title, flags=re.IGNORECASE
            ).strip()
            clean_title = re.sub(r'\s*\(\s*(19\d{2}|20\d{2})\s*\)\s*', '', clean_title).strip()
            return clean_title, int(m.group(2)), int(m.group(3))
    return None


def resolve_media_metadata(
    raw_input: str = "",
    custom_title: str = "",
    netflix_id: str = "",
    log_callback: Optional[Callable[[str], None]] = None
) -> dict:
    """
    Universal media resolver that accurately detects Movie vs TV Series,
    fetches canonical Titles, release Years, Season/Episode numbers,
    IMDb IDs, and TMDb IDs (including episode-level TMDb IDs for TV Series).
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    combined_input = f"{custom_title} {raw_input}".strip()
    cache_key = f"{netflix_id}|{custom_title}|{raw_input}"
    if cache_key in _MEDIA_META_CACHE:
        return _MEDIA_META_CACHE[cache_key]

    meta = {
        "media_type": "movie",
        "title": sanitize_filename(custom_title) or "Video",
        "year": "",
        "season": None,
        "episode": None,
        "episode_title": "",
        "imdb_id": "",
        "tmdb_id": "",
        "tmdb_show_id": "",
        "netflix_id": netflix_id or "",
    }

    # 1. Check for Netflix ID in parameters, title or input
    detected_nid = netflix_id or extract_netflix_id(custom_title) or extract_netflix_id(raw_input)
    if detected_nid:
        meta["netflix_id"] = detected_nid
        _log(f"  [Metadata] Identified Netflix ID: {detected_nid}")
        nf_title = resolve_netflix_title(detected_nid, log_callback=log_callback)
        if nf_title:
            meta["title"] = nf_title
            # Check if resolved title indicates a TV season/episode
            se_nf = extract_season_episode(nf_title)
            if se_nf:
                meta["media_type"] = "tv"
                meta["title"] = se_nf[0]
                meta["season"] = se_nf[1]
                meta["episode"] = se_nf[2]

            # Extract year from (YYYY)
            ym = re.search(r'\(\s*(19\d{2}|20\d{2})\s*\)', nf_title)
            if ym:
                meta["year"] = ym.group(1)

    # 2. Check for explicit IMDb ID (e.g. tt1375666 or tt4593122)
    imdb_id = extract_imdb_id(custom_title) or extract_imdb_id(raw_input)
    if imdb_id:
        meta["imdb_id"] = imdb_id
        _log(f"  [Metadata] Querying TMDb for IMDb ID: {imdb_id}...")
        find_res = _tmdb_api_get(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        if find_res:
            ep_results = find_res.get("tv_episode_results", [])
            movie_results = find_res.get("movie_results", [])
            tv_results = find_res.get("tv_results", [])

            if ep_results:
                ep = ep_results[0]
                meta["media_type"] = "tv"
                meta["season"] = ep.get("season_number")
                meta["episode"] = ep.get("episode_number")
                meta["episode_title"] = ep.get("name") or ""
                meta["tmdb_id"] = str(ep.get("id"))  # Precise Episode TMDb ID
                meta["tmdb_show_id"] = str(ep.get("show_id"))
                if ep.get("show_id"):
                    show_data = _tmdb_api_get(f"/tv/{ep['show_id']}")
                    if show_data:
                        meta["title"] = show_data.get("name") or meta["title"]
                        meta["year"] = (show_data.get("first_air_date") or "")[:4]
                _MEDIA_META_CACHE[cache_key] = meta
                return meta
            elif movie_results:
                mov = movie_results[0]
                meta["media_type"] = "movie"
                meta["title"] = mov.get("title") or meta["title"]
                meta["year"] = (mov.get("release_date") or "")[:4]
                meta["tmdb_id"] = str(mov.get("id"))
                _MEDIA_META_CACHE[cache_key] = meta
                return meta

    # 3. Check for Season/Episode pattern in custom_title or input
    se_info = extract_season_episode(custom_title) or extract_season_episode(raw_input)
    if se_info:
        show_name, s_num, e_num = se_info
        meta["media_type"] = "tv"
        meta["title"] = show_name
        meta["season"] = s_num
        meta["episode"] = e_num
        _log(f"  [Metadata] Detected TV Series: '{show_name}' S{s_num:02d}E{e_num:02d}")

        # Query TMDb for the TV Show and Episode details
        search_tv = _tmdb_api_get("/search/tv", {"query": show_name})
        if search_tv and search_tv.get("results"):
            show = search_tv["results"][0]
            show_id = show["id"]
            meta["title"] = show.get("name") or show_name
            meta["year"] = (show.get("first_air_date") or "")[:4]
            meta["tmdb_show_id"] = str(show_id)

            # Query exact Episode details for Episode TMDb ID
            ep_data = _tmdb_api_get(f"/tv/{show_id}/season/{s_num}/episode/{e_num}")
            if ep_data:
                meta["tmdb_id"] = str(ep_data.get("id"))  # Precise Episode TMDb ID
                meta["episode_title"] = ep_data.get("name") or ""

            # Query Episode external IDs for Episode IMDb ID
            ext_data = _tmdb_api_get(f"/tv/{show_id}/season/{s_num}/episode/{e_num}/external_ids")
            if ext_data and ext_data.get("imdb_id"):
                meta["imdb_id"] = ext_data["imdb_id"]
        _MEDIA_META_CACHE[cache_key] = meta
        return meta

    # 4. Check TMDb search for Movie (or fallback TV) by Title
    search_query = custom_title.strip()
    if not search_query and meta.get("title") and meta["title"] not in ("Video", "OmniStream"):
        search_query = meta["title"]

    if search_query and not search_query.isdigit():
        clean_search = re.sub(r'\s*\(\s*(19\d{2}|20\d{2})\s*\)\s*', '', search_query).strip()
        clean_search = re.sub(r'\b(1080p|720p|480p|2160p|4k|web-dl|webrip|bluray|x264|x265|hevc|aac)\b.*$', '', clean_search, flags=re.I).strip()
        
        # Check Movie search
        s_mov = _tmdb_api_get("/search/movie", {"query": clean_search})
        if s_mov and s_mov.get("results"):
            mov = s_mov["results"][0]
            meta["media_type"] = "movie"
            meta["title"] = mov.get("title") or clean_search
            meta["year"] = (mov.get("release_date") or "")[:4]
            meta["tmdb_id"] = str(mov.get("id"))
            ext = _tmdb_api_get(f"/movie/{mov['id']}/external_ids")
            if ext and ext.get("imdb_id"):
                meta["imdb_id"] = ext["imdb_id"]
            _MEDIA_META_CACHE[cache_key] = meta
            return meta

        # Fallback: TV Search if no movie found
        s_tv = _tmdb_api_get("/search/tv", {"query": clean_search})
        if s_tv and s_tv.get("results"):
            show = s_tv["results"][0]
            meta["media_type"] = "tv"
            meta["title"] = show.get("name") or clean_search
            meta["year"] = (show.get("first_air_date") or "")[:4]
            meta["tmdb_show_id"] = str(show.get("id"))
            meta["tmdb_id"] = str(show.get("id"))
            ext = _tmdb_api_get(f"/tv/{show['id']}/external_ids")
            if ext and ext.get("imdb_id"):
                meta["imdb_id"] = ext["imdb_id"]

    _MEDIA_META_CACHE[cache_key] = meta
    return meta


def generate_mode_filename(meta: dict, mode: str, fallback_title: str = "") -> str:
    """
    Generate the precise target filename for any given mode according to user specifications.
    
    Modes:
      1. title_only:
         - Movie: Clean Title without any ID.
         - TV Series: Show Title S01E02 without any ID.
      2. imdb:
         - Movie: Only IMDb ID (e.g. tt1375666).
         - TV Series: Only Episode IMDb ID (e.g. tt4593122). No title.
      3. tmdb:
         - Movie: Only TMDb ID (e.g. 27205).
         - TV Series: 'S01E02 123456' where 123456 is the Episode TMDb ID (never parent show ID).
      4. title_id:
         - Movie: 'Title (Year) [ID]'
         - TV Series: 'Show S01E02 [ID]'
      5. netflix_rename:
         - Canonical Netflix title e.g. 'Movie (Year)' or 'Show S01E02 - Title (Year)'
      6. normal / sub_merge:
         - Keeps original custom title or stream filename.
    """
    m = str(mode).lower().replace("✓", "").strip()
    is_tv = meta.get("media_type") == "tv" or (meta.get("season") is not None and meta.get("episode") is not None)
    clean_title = sanitize_filename(meta.get("title") or fallback_title or "Video")
    # Clean any accidental trailing extensions
    clean_title = re.sub(r'\.(m3u8|mpd|mp4|mkv|webm)$', '', clean_title, flags=re.IGNORECASE).strip()

    # 1. Title Only Mode
    # Use only the movie or series title for the file name. Do not append IDs.
    if "title_only" in m or m == "title only":
        if is_tv and meta.get("season") is not None and meta.get("episode") is not None:
            fn = f"{clean_title} S{meta['season']:02d}E{meta['episode']:02d}"
        else:
            fn = clean_title
        return sanitize_filename(fn)

    # 2. IMDb Mode
    # For movies, name file using IMDb ID only.
    # For TV series, use the IMDb ID of the specific episode.
    # Do not append any other title text.
    elif "imdb" in m:
        imdb_id = meta.get("imdb_id")
        if imdb_id:
            return sanitize_filename(imdb_id)
        # Fallback if IMDb ID not resolved
        if is_tv and meta.get("season") is not None and meta.get("episode") is not None:
            return sanitize_filename(f"{clean_title} S{meta['season']:02d}E{meta['episode']:02d}")
        return clean_title

    # 3. TMDb Mode
    # For movies, name file using TMDb ID only.
    # For TV series, file name format: S01E02 123456
    # Where S01 = Season 1, E02 = Episode 2, and 123456 = specific episode TMDb ID.
    # Uses correct episode TMDb ID for each episode.
    # Avoids assigning parent series TMDb ID to episodes.
    elif "tmdb" in m:
        tmdb_ep_or_mov_id = meta.get("tmdb_id")
        if is_tv:
            s_num = meta.get("season") if meta.get("season") is not None else 1
            e_num = meta.get("episode") if meta.get("episode") is not None else 1
            tag = f"S{s_num:02d}E{e_num:02d}"
            if tmdb_ep_or_mov_id:
                fn = f"{tag} {tmdb_ep_or_mov_id}"
            else:
                fn = tag
            return sanitize_filename(fn)
        else:
            if tmdb_ep_or_mov_id:
                return sanitize_filename(tmdb_ep_or_mov_id)
            return clean_title

    # 4. Title + ID Mode
    elif "title_id" in m or "title + id" in m or "title_and_id" in m:
        id_part = meta.get("netflix_id") or meta.get("tmdb_id") or meta.get("imdb_id") or ""
        if is_tv and meta.get("season") is not None and meta.get("episode") is not None:
            base = f"{clean_title} S{meta['season']:02d}E{meta['episode']:02d}"
        else:
            year_part = f" ({meta['year']})" if meta.get("year") else ""
            base = f"{clean_title}{year_part}"
        fn = f"{base} [{id_part}]" if id_part else base
        return sanitize_filename(fn)

    # 5. Netflix Mode
    elif "netflix" in m:
        if is_tv and meta.get("season") is not None and meta.get("episode") is not None:
            s_str = f"S{meta['season']:02d}E{meta['episode']:02d}"
            ep_title = f" - {meta['episode_title']}" if meta.get("episode_title") else ""
            y_str = f" ({meta['year']})" if meta.get("year") else ""
            fn = f"{clean_title} {s_str}{ep_title}{y_str}".strip()
        else:
            y_str = f" ({meta['year']})" if meta.get("year") else ""
            fn = f"{clean_title}{y_str}".strip()
        return sanitize_filename(fn)

    # 6. Normal / Sub Merge / default
    return sanitize_filename(fallback_title or clean_title)


def resolve_target_filename(
    input_text: str = "",
    custom_title: str = "",
    mode: str = "normal",
    netflix_id: str = "",
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[str, dict]:
    """
    Unified entry point to resolve media metadata and generate the final filename for any mode.
    Returns (target_filename, metadata_dict).
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    m = str(mode).lower().replace("✓", "").strip()
    if m in ("normal", "sub_merge") and custom_title and custom_title.lower() not in ("video", "player"):
        meta = {"media_type": "unknown", "title": custom_title}
        return sanitize_filename(custom_title), meta

    meta = resolve_media_metadata(
        raw_input=input_text,
        custom_title=custom_title,
        netflix_id=netflix_id,
        log_callback=log_callback
    )

    final_name = generate_mode_filename(meta, mode=m, fallback_title=custom_title or "Video")
    return final_name, meta


def get_smart_organized_path(save_dir: str, metadata: dict, filename: str) -> str:
    """
    Computes organized folder path based on media type:
    - TV Shows: <save_dir>/TV Shows/<Show Title>/Season <XX>/<filename>
    - Movies:   <save_dir>/Movies/<Movie Title> (<Year>)/<filename>
    """
    if not metadata:
        return os.path.join(save_dir, filename)

    is_tv = metadata.get("is_tv") or metadata.get("media_type") == "tv" or bool(metadata.get("season"))
    raw_title = metadata.get("show_title") or metadata.get("title") or "Unknown"
    clean_title = sanitize_filename(raw_title)

    if is_tv:
        season = metadata.get("season") or 1
        subfolder = os.path.join(save_dir, "TV Shows", clean_title, f"Season {season:02d}")
    else:
        year = metadata.get("year")
        folder_name = f"{clean_title} ({year})" if year else clean_title
        subfolder = os.path.join(save_dir, "Movies", folder_name)

    os.makedirs(subfolder, exist_ok=True)
    return os.path.join(subfolder, filename)


