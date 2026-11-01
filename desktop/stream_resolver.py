"""
OmniStream Pro v2.6.0 - Lazy Stream Resolver
Resolves video streaming URLs (M3U8 / MPD / MP4) from movie/series watch and detail pages
just-in-time before download execution (Strict FIFO Serial Auto Mode).
Supports direct HTML/iframe extraction and browser-assisted extension bridge resolution.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import re
import sys
import time
import urllib.parse
import subprocess
import threading
from typing import Optional, Tuple, Dict, Any, Callable

STREAM_EXT_REGEX = re.compile(r'https?://[^\s"\'<>\\]+?\.(?:m3u8|mp4|mpd)[^\s"\'<>\\]*', re.IGNORECASE)
IFRAME_SRC_REGEX = re.compile(r'<iframe[^>]+?src=["\'](https?://[^"\']+)["\']', re.IGNORECASE)
PLAYER_SRC_REGEX = re.compile(r'(?:file|source|src|data-src|videoUrl)\s*[:=]\s*["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']', re.IGNORECASE)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


class LazyStreamResolver:
    """Performs just-in-time stream URL extraction for queued movie/series items."""

    def __init__(self, app_ref=None):
        self.app_ref = app_ref
        self._resolution_events: Dict[str, threading.Event] = {}
        self._resolved_cache: Dict[str, Dict[str, Any]] = {}

    def notify_resolved_from_bridge(self, item_id: str, url: str, headers: Optional[Dict[str, str]] = None, curl: Optional[str] = None):
        """Called by bridge server when Chrome extension sniffs the stream for a background tab."""
        self._resolved_cache[item_id] = {
            "url": url,
            "headers": headers or {},
            "curl": curl or ""
        }
        ev = self._resolution_events.get(item_id)
        if ev:
            ev.set()

    def resolve(
        self,
        page_url: str,
        item_id: str = "",
        title: str = "",
        log_callback: Optional[Callable[[str], None]] = None,
        timeout_sec: int = 25
    ) -> Tuple[Optional[str], Dict[str, str]]:
        """
        Resolve streaming URL from a movie details/watch page.
        1. Checks if page_url is already a direct stream.
        2. Tries direct HTTP / curl / regex extraction of M3U8/MP4 or embed iframes.
        3. If protected (e.g. Cloudflare Turnstile), delegates to Chrome Extension via bridge.
        """
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        if not page_url:
            return None, {}

        # 1. Is page_url already a direct stream?
        lo = page_url.lower().split("?")[0]
        if lo.endswith((".m3u8", ".mpd", ".mp4", ".mkv", ".webm")):
            return page_url, {}

        log(f"  [Resolver] Resolving stream for '{title or page_url}'...")

        # 2. Direct HTTP / curl inspection
        stream_url, headers = self._direct_resolve(page_url, log)
        if stream_url:
            log(f"  [Resolver] Direct extraction found stream: {stream_url[:70]}...")
            return stream_url, headers

        # 3. Extension-Assisted Resolution (Delegated to active Chrome tab)
        if self.app_ref and item_id:
            log("  [Resolver] Page requires browser execution / Cloudflare bypass; delegating to Chrome Extension...")
            stream_url, headers = self._extension_resolve(item_id, page_url, timeout_sec, log)
            if stream_url:
                log(f"  [Resolver] Chrome Extension captured stream: {stream_url[:70]}...")
                return stream_url, headers

        log("  [Resolver] Notice: Stream could not be automatically resolved.")
        return None, {}

    def _fetch_html(self, url: str, referer: str = "") -> Optional[str]:
        """Fetch HTML content using system curl.exe to avoid basic Cloudflare / TLS fingerprint blocks."""
        cmd = [
            "curl.exe", "-s", "-L",
            "--connect-timeout", "6",
            "--max-time", "12",
            "-H", f"User-Agent: {DEFAULT_USER_AGENT}",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "-H", "Accept-Language: en-US,en;q=0.9",
        ]
        if referer:
            cmd.extend(["-H", f"Referer: {referer}"])
        cmd.append(url)

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=14,
                startupinfo=startupinfo,
                creationflags=creationflags
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass
        return None

    def _direct_resolve(self, page_url: str, log_cb: Callable[[str], None]) -> Tuple[Optional[str], Dict[str, str]]:
        """Search page HTML and potential iframe embeds for stream sources."""
        html = self._fetch_html(page_url)
        if not html:
            return None, {}

        # Look for direct stream links inside HTML
        m_stream = PLAYER_SRC_REGEX.search(html)
        if m_stream:
            return m_stream.group(1), {"referer": page_url}

        all_streams = STREAM_EXT_REGEX.findall(html)
        for s in all_streams:
            if not any(ign in s.lower() for ign in ("preview", "trailer", "sample", "logo", "ad.")):
                return s, {"referer": page_url}

        # Look for iframe embed players
        iframes = IFRAME_SRC_REGEX.findall(html)
        for ifr_url in iframes:
            if any(ign in ifr_url.lower() for ign in ("facebook", "twitter", "disqus", "google", "analytics")):
                continue
            abs_ifr = urllib.parse.urljoin(page_url, ifr_url)
            log_cb(f"  [Resolver] Probing embed player: {abs_ifr[:60]}...")
            ifr_html = self._fetch_html(abs_ifr, referer=page_url)
            if ifr_html:
                m_ifr_stream = PLAYER_SRC_REGEX.search(ifr_html)
                if m_ifr_stream:
                    return m_ifr_stream.group(1), {"referer": abs_ifr}

                ifr_streams = STREAM_EXT_REGEX.findall(ifr_html)
                for s in ifr_streams:
                    if not any(ign in s.lower() for ign in ("preview", "trailer", "sample")):
                        return s, {"referer": abs_ifr}

        return None, {}

    def _extension_resolve(
        self,
        item_id: str,
        page_url: str,
        timeout_sec: int,
        log_cb: Callable[[str], None]
    ) -> Tuple[Optional[str], Dict[str, str]]:
        """Request Chrome Extension to open a background tab and sniff the stream."""
        ev = threading.Event()
        self._resolution_events[item_id] = ev

        # Broadcast task to bridge
        if hasattr(self.app_ref, "pending_resolution_task"):
            self.app_ref.pending_resolution_task = {
                "id": item_id,
                "page_url": page_url
            }

        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            if ev.wait(timeout=1.0):
                break
            # Check if cache was filled
            if item_id in self._resolved_cache:
                break

        # Cleanup pending task
        if hasattr(self.app_ref, "pending_resolution_task"):
            if self.app_ref.pending_resolution_task and self.app_ref.pending_resolution_task.get("id") == item_id:
                self.app_ref.pending_resolution_task = None

        self._resolution_events.pop(item_id, None)
        cached = self._resolved_cache.pop(item_id, None)
        if cached and cached.get("url"):
            return cached["url"], cached.get("headers", {})

        return None, {}

