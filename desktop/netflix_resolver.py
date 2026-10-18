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
from typing import Optional, Callable

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
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            try:
                raw_bytes = resp.read()
            except http.client.IncompleteRead as e:
                raw_bytes = e.partial
            page = raw_bytes.decode("utf-8", errors="ignore")

        # ── Step A: Get the show/movie title from <h1> ───────────────────────
        h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.I)
        if h1_m:
            cand = _clean_scraped_title(h1_m.group(1))
            if cand:
                title = cand

        # ── Step B: Detect if the original nid is an episode in embedded JSON ─
        # Netflix's SSR page embeds JSON like:
        # "videoId":81948683,"number":1,"runtimeSec":...,"title":"La Dolce Emily"
        # We look for nid in the page and extract surrounding season/episode data.
        if nid in page:
            idx = page.find(nid)
            forward = page[idx: min(len(page), idx + 800)]
            back = page[max(0, idx - 2500): idx]

            # Extract episode number from forward JSON
            ep_num_m = re.search(r'"number":\s*(\d+)', forward)
            ep_num = int(ep_num_m.group(1)) if ep_num_m else None

            # Extract episode title from forward JSON ("title":"La Dolce Emily")
            ep_title = ""
            ep_title_m = re.search(r'"title":\s*"([^"]+)"', forward)
            if ep_title_m:
                raw_ep = ep_title_m.group(1)
                # Decode unicode escapes like \x20 → space
                try:
                    raw_ep = raw_ep.encode().decode("unicode-escape")
                except Exception:
                    pass
                raw_ep = raw_ep.replace("\\x20", " ").replace('\\"', '"').strip()
                if raw_ep and not re.match(r'^Season\s*\d+$', raw_ep, re.I):
                    ep_title = sanitize_filename(raw_ep)

            # Look backwards for the season number in "Season\\x204" or "Season 4"
            s_nums = re.findall(r'Season(?:\\x20|\s)+(\d+)', back)
            season_num = int(s_nums[-1]) if s_nums else None

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
