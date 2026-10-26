"""
OmniStream Pro v2.6.0 - Multi-Mode Title Resolver (Netflix, IMDb, TMDB)
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
from typing import Optional, Callable, Tuple

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


def extract_imdb_id(text: str) -> Optional[str]:
    """
    Extract canonical IMDb ID (tt followed by 7-10 digits) from text, URLs or parameters.
    Examples:
      - 'https://www.imdb.com/title/tt18259086/' -> 'tt18259086'
      - 'imdb=tt18259086' -> 'tt18259086'
      - 'tt18259086.mp4' -> 'tt18259086'
    """
    if not text:
        return None
    m = re.search(r'\b(tt\d{7,10})\b', str(text), re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def extract_tmdb_id(text: str) -> Optional[str]:
    """
    Extract TMDB ID from text, URLs or parameters.
    Examples:
      - 'https://www.themoviedb.org/movie/939243' -> '939243'
      - 'https://www.themoviedb.org/tv/82596' -> '82596'
      - 'tmdb_id=939243' -> '939243'
      - 'tmdb-939243' -> '939243'
    """
    if not text:
        return None
    raw = str(text)
    m_url = re.search(r'themoviedb\.org/(?:movie|tv)/(\d+)', raw, re.IGNORECASE)
    if m_url:
        return m_url.group(1)
    m_param = re.search(r'(?:tmdb|tmdb_id|tmdbid)[=:_\-](\d+)', raw, re.IGNORECASE)
    if m_param:
        return m_param.group(1)
    return None


def clean_show_title(raw_title: str) -> Tuple[str, str]:
    """
    Separate base show/movie title and episode tag.
    Example:
      'Emily in Paris S04E01 - La Dolce Emily' -> ('Emily in Paris', 'S04E01')
      'Sonic the Hedgehog 3 (2024)' -> ('Sonic the Hedgehog 3', '')
    """
    if not raw_title:
        return "", ""
    t = re.sub(r'\(.*?\)', '', str(raw_title)).strip()
    ep_tag = ""
    # Match SxxExx
    m = re.search(r'\b(S\d{1,2}E\d{1,2})\b', t, re.IGNORECASE)
    if m:
        ep_tag = m.group(1).upper()
        t = t[:m.start()].strip()
    else:
        # Match Season X Episode Y
        m2 = re.search(r'\bSeason\s*(\d+)\s*(?:Episode|Chapter)\s*(\d+)\b', t, re.IGNORECASE)
        if m2:
            ep_tag = f"S{int(m2.group(1)):02d}E{int(m2.group(2)):02d}"
            t = t[:m2.start()].strip()
    return t.rstrip(" -:_"), ep_tag


def fetch_imdb_metadata(title: str, year: Optional[str] = None) -> Optional[dict]:
    """
    Query IMDb's public suggestion endpoint to verify title, get official release year and IMDb ID.
    Returns dict with 'title', 'year', 'imdb_id', and 'type' if found.
    """
    if not title:
        return None
    try:
        clean_title, _ = clean_show_title(title)
        if not clean_title:
            clean_title = title.strip()
        slug = urllib.parse.quote(clean_title.lower().replace(" ", "_"))
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{slug}.json"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            entries = data.get("d", [])

            # Pass 1: Exact title match + year match
            for entry in entries:
                t = entry.get("l", "")
                y = entry.get("y")
                imdb_id = entry.get("id", "")
                if not imdb_id.startswith("tt"):
                    continue
                if t.lower() == clean_title.lower():
                    if year and y and abs(int(y) - int(year)) <= 1:
                        return {"title": t, "year": str(y), "imdb_id": imdb_id, "type": entry.get("q", "")}

            # Pass 2: Exact title match (regardless of year, e.g. Dark)
            for entry in entries:
                t = entry.get("l", "")
                y = entry.get("y")
                imdb_id = entry.get("id", "")
                if not imdb_id.startswith("tt"):
                    continue
                if t.lower() == clean_title.lower():
                    return {"title": t, "year": str(y) if y else "", "imdb_id": imdb_id, "type": entry.get("q", "")}

            # Pass 3: Close title match with year match
            for entry in entries:
                t = entry.get("l", "")
                y = entry.get("y")
                q = (entry.get("q") or "").lower()
                imdb_id = entry.get("id", "")
                if not imdb_id.startswith("tt"):
                    continue
                if q in ("feature", "tv series", "tv mini-series", "tv movie", "video", "") or not q:
                    if year and y and abs(int(y) - int(year)) <= 1:
                        return {"title": t, "year": str(y), "imdb_id": imdb_id, "type": q}

            # Pass 4: Fallback to first valid feature / tv series tt entry
            for entry in entries:
                imdb_id = entry.get("id", "")
                q = (entry.get("q") or "").lower()
                if imdb_id.startswith("tt") and (q in ("feature", "tv series", "tv mini-series", "tv movie") or not q):
                    return {"title": entry.get("l", clean_title), "year": str(entry.get("y", "")), "imdb_id": imdb_id, "type": q}
    except Exception:
        pass
    return None


def fetch_tmdb_id_from_imdb(imdb_id: str) -> Optional[str]:
    """
    Query Wikidata SPARQL to map IMDb ID (P345) to TMDB Movie ID (P4947) or TV ID (P4983).
    Lightning fast and returns canonical IDs with 100% precision.
    """
    if not imdb_id or not imdb_id.startswith("tt"):
        return None
    try:
        query = f'''
        SELECT ?tmdb_m ?tmdb_tv WHERE {{
          ?item wdt:P345 "{imdb_id}".
          OPTIONAL {{ ?item wdt:P4947 ?tmdb_m. }}
          OPTIONAL {{ ?item wdt:P4983 ?tmdb_tv. }}
        }}
        '''
        url = "https://query.wikidata.org/sparql?query=" + urllib.parse.quote(query) + "&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "OmniStreamPro/2.5 (dev@omnistream.pro)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            bindings = data.get("results", {}).get("bindings", [])
            for b in bindings:
                if "tmdb_m" in b:
                    return b["tmdb_m"]["value"]
                if "tmdb_tv" in b:
                    return b["tmdb_tv"]["value"]
    except Exception:
        pass
    return None


def fetch_tmdb_id_fallback(title: str, year: Optional[str] = None) -> Optional[str]:
    """
    Search fallback via DuckDuckGo for TMDB ID.
    """
    if not title:
        return None
    try:
        clean_title, _ = clean_show_title(title)
        url = "https://lite.duckduckgo.com/lite/"
        q = f'"{clean_title}" {year or ""} site:themoviedb.org'
        data = urllib.parse.urlencode({"q": q}).encode()
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            m = re.findall(r'themoviedb\.org/(?:movie|tv)/(\d+)', content)
            if m:
                return m[0]
    except Exception:
        pass
    return None


def fetch_tmdb_id(
    imdb_id: Optional[str] = None,
    title: Optional[str] = None,
    year: Optional[str] = None
) -> Optional[str]:
    """
    Multi-layer TMDB ID resolution.
    1. Direct mapping via IMDb ID on Wikidata (most accurate).
    2. Fallback search on DuckDuckGo.
    """
    if imdb_id:
        tid = fetch_tmdb_id_from_imdb(imdb_id)
        if tid:
            return tid
    if title:
        return fetch_tmdb_id_fallback(title, year)
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


# Separate cache for unified media ID renames
_MEDIA_ID_CACHE = {}


def resolve_media_details(
    netflix_id: Optional[str] = None,
    title: Optional[str] = None,
    raw_input: Optional[str] = None,
    imdb_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> dict:
    """
    Comprehensive media metadata aggregator.
    Given any combination of Netflix ID, title, IMDb ID, or TMDB ID,
    resolves the full metadata:
    {
        "title": "Sonic the Hedgehog 3",
        "year": "2024",
        "episode_tag": "S01E01",
        "netflix_id": "81902147",
        "imdb_id": "tt18259086",
        "tmdb_id": "939243"
    }
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    # Extract clean IDs from any provided arguments
    clean_nf = extract_netflix_id(netflix_id) or extract_netflix_id(title) or extract_netflix_id(raw_input)
    clean_im = extract_imdb_id(imdb_id) or extract_imdb_id(netflix_id) or extract_imdb_id(title) or extract_imdb_id(raw_input)
    clean_tm = extract_tmdb_id(tmdb_id) or extract_tmdb_id(netflix_id) or extract_tmdb_id(title) or extract_tmdb_id(raw_input)

    # If a free-text title was passed in netflix_id or raw_input, preserve it as title
    if not clean_nf and not title:
        candidate_text = netflix_id or raw_input
        if candidate_text and not str(candidate_text).startswith("http"):
            title = candidate_text

    # Extract episode tag from any available text
    ep_from_input = ""
    for cand_str in (raw_input, title, netflix_id):
        if cand_str:
            _, ep = clean_show_title(str(cand_str))
            if ep:
                ep_from_input = ep
                break

    res = {
        "title": "",
        "year": "",
        "episode_tag": ep_from_input,
        "netflix_id": clean_nf,
        "imdb_id": clean_im,
        "tmdb_id": clean_tm
    }

    # Step 1: If netflix_id is present, resolve via Netflix Resolver
    if res["netflix_id"]:
        nid = res["netflix_id"]
        netflix_full = resolve_netflix_title(nid, log_callback=_log)
        if netflix_full:
            y_m = re.search(r'\((\d{4})\)', netflix_full)
            if y_m:
                res["year"] = y_m.group(1)
            clean_t, ep = clean_show_title(netflix_full)
            res["title"] = clean_t
            if ep:
                res["episode_tag"] = ep
            elif not res["episode_tag"]:
                m_ep = re.search(r'\b(S\d{1,2}E\d{1,2})\b', netflix_full, re.I)
                if m_ep:
                    res["episode_tag"] = m_ep.group(1).upper()

    # Step 2: If title is still missing, use given title or clean from input
    if not res["title"] and title:
        clean_t, ep = clean_show_title(title)
        res["title"] = clean_t
        if ep and not res["episode_tag"]:
            res["episode_tag"] = ep

    # Step 3: Resolve IMDb ID if missing
    if not res["imdb_id"] and res["title"]:
        _log(f"  [Media Resolver] Querying IMDb metadata for '{res['title']}'...")
        imdb_data = fetch_imdb_metadata(res["title"], res["year"])
        if imdb_data:
            res["imdb_id"] = imdb_data.get("imdb_id")
            if not res["year"] and imdb_data.get("year"):
                res["year"] = imdb_data.get("year")
            if imdb_data.get("title"):
                res["title"] = imdb_data["title"]

    # Step 4: Resolve TMDB ID if missing
    if not res["tmdb_id"]:
        if res["imdb_id"]:
            _log(f"  [Media Resolver] Mapping IMDb ID '{res['imdb_id']}' to TMDB ID via Wikidata...")
            res["tmdb_id"] = fetch_tmdb_id_from_imdb(res["imdb_id"])
        if not res["tmdb_id"] and res["title"]:
            _log(f"  [Media Resolver] Fallback querying TMDB ID for '{res['title']}'...")
            res["tmdb_id"] = fetch_tmdb_id_fallback(res["title"], res["year"])

    return res


def resolve_media_id_rename(
    mode: str,
    netflix_id: Optional[str] = None,
    title: Optional[str] = None,
    raw_input: Optional[str] = None,
    imdb_id: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    """
    Unified ID Rename Resolver.
    Returns the exact target filename stem (without extension) according to the selected mode:
      - 'netflix_rename' : returns Netflix ID (e.g. '81902147' or '81902147_S01E01')
      - 'tmdb_rename'    : returns TMDB ID (e.g. '939243' or '939243_S01E01')
      - 'imdb_rename'    : returns IMDb ID (e.g. 'tt18259086' or 'tt18259086_S01E01')
    Returns None if identification fails so original filename is preserved.
    """
    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    cache_key = (mode, str(netflix_id or ""), str(title or ""), str(imdb_id or ""), str(tmdb_id or ""))
    if cache_key in _MEDIA_ID_CACHE:
        cached = _MEDIA_ID_CACHE[cache_key]
        _log(f"  [Media Resolver] Using cached ID rename for mode '{mode}': '{cached}'")
        return cached

    ep_suffix = ""

    if mode == "netflix_rename":
        nid = extract_netflix_id(netflix_id) or extract_netflix_id(title) or extract_netflix_id(raw_input)
        if nid:
            details = resolve_media_details(netflix_id=nid, title=title, raw_input=raw_input, log_callback=_log)
            if details and details.get("episode_tag"):
                ep_suffix = f"_{details['episode_tag']}"
            result = f"{nid}{ep_suffix}"
            _MEDIA_ID_CACHE[cache_key] = result
            _log(f"  [Netflix Rename] Resolved Netflix ID: '{result}'")
            return result

    elif mode == "imdb_rename":
        direct_imdb = extract_imdb_id(imdb_id) or extract_imdb_id(netflix_id) or extract_imdb_id(title) or extract_imdb_id(raw_input)
        if direct_imdb:
            details = resolve_media_details(title=title, raw_input=raw_input, imdb_id=direct_imdb, log_callback=_log)
            if details and details.get("episode_tag"):
                ep_suffix = f"_{details['episode_tag']}"
            result = f"{direct_imdb.lower()}{ep_suffix}"
            _MEDIA_ID_CACHE[cache_key] = result
            _log(f"  [IMDb Rename] Using extracted IMDb ID: '{result}'")
            return result

        details = resolve_media_details(netflix_id=netflix_id, title=title, raw_input=raw_input, log_callback=_log)
        if details and details.get("imdb_id"):
            if details.get("episode_tag"):
                ep_suffix = f"_{details['episode_tag']}"
            result = f"{details['imdb_id']}{ep_suffix}"
            _MEDIA_ID_CACHE[cache_key] = result
            _log(f"  [IMDb Rename] Successfully resolved IMDb ID: '{result}' (Movie: {details.get('title')})")
            return result

    elif mode == "tmdb_rename":
        direct_tmdb = extract_tmdb_id(tmdb_id) or extract_tmdb_id(netflix_id) or extract_tmdb_id(title) or extract_tmdb_id(raw_input)
        if direct_tmdb:
            details = resolve_media_details(title=title, raw_input=raw_input, tmdb_id=direct_tmdb, log_callback=_log)
            if details and details.get("episode_tag"):
                ep_suffix = f"_{details['episode_tag']}"
            result = f"{direct_tmdb}{ep_suffix}"
            _MEDIA_ID_CACHE[cache_key] = result
            _log(f"  [TMDB Rename] Using extracted TMDB ID: '{result}'")
            return result

        details = resolve_media_details(netflix_id=netflix_id, title=title, raw_input=raw_input, log_callback=_log)
        if details and details.get("tmdb_id"):
            if details.get("episode_tag"):
                ep_suffix = f"_{details['episode_tag']}"
            result = f"{details['tmdb_id']}{ep_suffix}"
            _MEDIA_ID_CACHE[cache_key] = result
            _log(f"  [TMDB Rename] Successfully resolved TMDB ID: '{result}' (Movie: {details.get('title')})")
            return result

    _log(f"  [Media Resolver] Notice: Could not resolve target ID for mode '{mode}'.")
    return None



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
