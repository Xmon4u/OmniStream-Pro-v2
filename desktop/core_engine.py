"""
OmniStream Pro v2.3.0 - High Performance Multi-Stream Engine
Captures HLS (.m3u8), DASH (.mpd), and direct video/audio media streams.
Concurrent multi-audio track preservation and lossless MKV multiplexing via N_m3u8DL-RE and FFmpeg.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import re
import sys
import time
import shutil
import subprocess
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, Callable

from setup_dependencies import ensure_dependencies

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_SAVE_DIR = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Desktop")


def _format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


# Compiled regex for ANSI escape code stripping
_ANSI_RE = re.compile(r'\x1b(?:\[[0-9;]*[mGKHFJABCDEFGHILMSTsu]|\][^\x07]*(?:\x07|\x1b\\)|[0-9A-Za-z])')


def _strip_ansi(text: str) -> str:
    """Remove ANSI terminal escape sequences from a string."""
    return _ANSI_RE.sub('', text)


def _format_speed(speed_bps: Optional[float]) -> str:
    """Format speed in B/s to human-readable GB/s, MB/s, KB/s, or B/s string."""
    if speed_bps is None or speed_bps <= 0:
        return "0.0 MB/s"
    if speed_bps >= 1024 * 1024 * 1024:
        return f"{speed_bps / (1024 * 1024 * 1024):.2f} GB/s"
    elif speed_bps >= 1024 * 1024:
        return f"{speed_bps / (1024 * 1024):.1f} MB/s"
    elif speed_bps >= 1024:
        return f"{speed_bps / 1024:.0f} KB/s"
    return f"{speed_bps:.0f} B/s"


def _parse_progress_line(line: str) -> Optional[Dict[str, Any]]:
    """Extract percent / speed / ETA / size from N_m3u8DL-RE, yt-dlp, or console stream output."""
    clean = _strip_ansi(line).strip()
    if not clean:
        return None

    # Handle explicit muxing/merging stages
    cl_low = clean.lower()
    if any(k in cl_low for k in ("ffmpeg merging", "merging", "muxing")):
        return {
            "pct": 99.0,
            "status": "Muxing & finalizing...",
            "speed_bps": None,
            "speed": None,
            "eta_sec": 0,
            "size": None,
            "track": "main",
            "raw": clean,
        }

    pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', clean)
    if not pct_match:
        return None

    pct = max(0.0, min(100.0, float(pct_match.group(1))))

    # Segment count: e.g. 1/3 or 120/500
    seg_match = re.search(r'(\d+)\s*/\s*(\d+)', clean)
    seg_str = f"{seg_match.group(1)} / {seg_match.group(2)} segs" if seg_match else None

    # Size: e.g. 7.58MB/22.74MB or 1.25GB/5.20GB or of 150MiB
    size_str: Optional[str] = None
    # 1. Dual size pair: downloaded / total (strictly [KMGT]i?B, case-insensitive)
    sz_pair = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]i?B)\s*/\s*(\d+(?:\.\d+)?\s*[KMGT]i?B)', clean, re.IGNORECASE)
    if sz_pair:
        size_str = f"{sz_pair.group(1).strip()} / {sz_pair.group(2).strip()}"
    else:
        # 2. yt-dlp style: of 150.00MiB
        sz_of = re.search(r'of\s+~?(\d+(?:\.\d+)?\s*[KMGT]i?B)', clean, re.IGNORECASE)
        if sz_of:
            size_str = sz_of.group(1).strip()
        else:
            # 3. Single size (e.g. 23.85MB near 100%)
            post_pct_text = clean[pct_match.end():]
            sz_single = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]i?B)(?:\s*[-–]|\s*$)', post_pct_text, re.IGNORECASE)
            if sz_single and pct >= 95.0:
                size_str = sz_single.group(1).strip()

    if not size_str:
        size_str = seg_str

    # Speed: look AFTER percentage to avoid playlist bitrates (e.g. "6221 Kbps")
    speed_bps: Optional[float] = None
    post_pct = clean[pct_match.end():]
    speed_match = re.search(r'(?:[-~]?\s*)(\d+(?:\.\d+)?)\s*([KMGT]i?B(?:ps|/s)|Bps|B/s)', post_pct, re.IGNORECASE)
    if not speed_match:
        # Fallback: look for explicit "Speed: X" or "at X MB/s" anywhere in line
        speed_match = re.search(r'(?:speed:?\s*|at\s+)(\d+(?:\.\d+)?)\s*([KMGT]i?B(?:ps|/s)|Bps|B/s)', clean, re.IGNORECASE)

    if speed_match:
        val = float(speed_match.group(1))
        raw_unit = speed_match.group(2).upper().replace('IB', 'B').replace('PS', '/S')
        mult = {'B/S': 1, 'KB/S': 1024, 'MB/S': 1024**2, 'GB/S': 1024**3, 'TB/S': 1024**4}.get(raw_unit, 1024**2)
        speed_bps = val * mult

    # ETA: look in post_pct for HH:MM:SS, MM:SS, or ETA keywords
    eta_sec: Optional[float] = None
    eta_match = re.search(r'(?:ETA:?\s*|left\s*[:\-]?\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?', post_pct, re.IGNORECASE)
    if eta_match and pct < 99.5:
        g = [int(x) for x in eta_match.groups() if x is not None]
        if len(g) == 3:
            eta_sec = g[0] * 3600 + g[1] * 60 + g[2]
        elif len(g) == 2:
            eta_sec = g[0] * 60 + g[1]

    # Track classification
    track = "main"
    cl = clean.lower()
    if cl.startswith("vid") or "video" in cl[:14]:
        track = "vid"
    elif cl.startswith("aud") or "audio" in cl[:14]:
        track = "aud"
    elif cl.startswith("sub"):
        track = "sub"

    speed_mb = (speed_bps / (1024 * 1024)) if speed_bps is not None else None
    return {
        "pct": pct,
        "speed_bps": speed_bps,
        "speed": speed_mb,
        "eta_sec": eta_sec,
        "size": size_str,
        "track": track,
        "raw": clean,
    }


def _build_progress_message(
    pct: float,
    speed_bps: Optional[float] = None,
    eta_sec: Optional[float] = None,
    fallback: str = "",
    # Legacy compat: accept 'speed' as MB/s float
    speed: Optional[float] = None,
    size: Optional[str] = None,
) -> str:
    """Build a human-readable progress status string."""
    pct = max(0.0, min(100.0, pct))
    left = max(0.0, 100.0 - pct)

    # Normalise speed to BPS
    if speed_bps is None and speed is not None:
        speed_bps = speed * 1024 * 1024

    parts = [f"{pct:.1f}% done", f"{left:.1f}% left"]

    if speed_bps is not None and speed_bps > 0:
        parts.append(_format_speed(speed_bps))
    elif pct < 100.0:
        parts.append("0.0 MB/s")

    if eta_sec is not None and eta_sec >= 0:
        parts.append(f"ETA {_format_eta(eta_sec)}")
    elif fallback and any(k in fallback.lower() for k in ("mux", "merg")):
        parts.append(fallback)

    if size:
        parts.append(size)

    return "  ·  ".join(parts)


class OmniStreamEngine:
    def __init__(self):
        self.current_process: Optional[subprocess.Popen] = None
        self._is_aborted = False

    def abort(self):
        """Safely terminate any running download and multiplex process."""
        self._is_aborted = True
        if self.current_process and self.current_process.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)],
                        capture_output=True, creationflags=0x08000000
                    )
                self.current_process.terminate()
                time.sleep(0.3)
                if self.current_process.poll() is None:
                    self.current_process.kill()
            except Exception:
                pass

    @staticmethod
    def cleanup_intermediate_files(save_dir: str, save_name: str, final_file: str,
                                    log_callback=None) -> None:
        """Delete intermediate video/audio segment files after successful mux.

        N_m3u8DL-RE leaves behind per-track files like:
            <save_name>.mkv_video.mp4
            <save_name>_hin.m4a  /  <save_name>_eng.m4a
            <save_name>_audio_*.mp4  etc.
        We keep ONLY the final merged MKV and remove only known intermediate tracks
        belonging specifically to this download, never touching unrelated user files.
        """
        def _log(msg):
            if log_callback:
                log_callback(msg)

        if not final_file or not os.path.exists(final_file):
            return

        final_abs = os.path.abspath(final_file)
        removed = []
        errors = []

        stem = save_name.lower()

        # Specific intermediate filename patterns produced by N_m3u8DL-RE / ffmpeg
        known_intermediate_names = {
            f"{save_name}.video.mp4".lower(),
            f"{save_name}.video.mkv".lower(),
            f"{save_name}_video.mp4".lower(),
            f"{save_name}_video.mkv".lower(),
            f"{save_name}.mkv_video.mp4".lower(),
            f"{save_name}.mkv_video.mkv".lower(),
        }
        # If final output is MKV, a standalone raw video track with the exact stem may also exist
        if final_abs.lower().endswith(".mkv"):
            known_intermediate_names.add(f"{save_name}.mp4".lower())

        # Exact N_m3u8DL-RE audio & video track suffixes:
        # e.g. <save_name>_hin.m4a, <save_name>_eng.m4a, <save_name>_audio_0.m4a, <save_name>.mkv_audio_0.m4a
        track_suffix_re = re.compile(
            r"^" + re.escape(stem) + r"(?:\.mkv)?(?:_|\.)(?:[a-z]{2,4}|audio[_\d]*|video[_\d]*|sub[_\d]*)\.(?:m4a|aac|ts|mp4|mkv|srt|vtt)$",
            re.IGNORECASE
        )

        try:
            for fname in os.listdir(save_dir):
                fpath = os.path.abspath(os.path.join(save_dir, fname))
                if fpath == final_abs:
                    continue  # Never delete the final output

                base = fname.lower()

                # Strictly match only known N_m3u8DL-RE intermediate patterns
                is_intermediate = (
                    base in known_intermediate_names or
                    bool(track_suffix_re.match(base))
                )

                if is_intermediate:
                    try:
                        os.remove(fpath)
                        removed.append(fname)
                    except Exception as e:
                        errors.append(f"{fname}: {e}")
        except Exception as e:
            _log(f"  [Cleanup] Directory scan error: {e}")
            return

        # Remove the dedicated temp folder if present
        try:
            for entry in os.listdir(save_dir):
                if entry.startswith(".omnistream_tmp_"):
                    tmp_path = os.path.join(save_dir, entry)
                    if os.path.isdir(tmp_path):
                        shutil.rmtree(tmp_path, ignore_errors=True)
                        removed.append(entry + "/")
        except Exception:
            pass

        if removed:
            _log(f"  [Cleanup] Cleaned {len(removed)} intermediate track file(s).")
        if errors:
            _log(f"  [Cleanup] Notice: Could not remove {len(errors)} file(s).")

    @staticmethod
    def has_subtitle_tracks(filepath_or_content: str) -> bool:
        """Check if an M3U8 playlist or MPD manifest contains subtitle tracks."""
        if not filepath_or_content:
            return False
        content = filepath_or_content
        if os.path.exists(filepath_or_content):
            try:
                with open(filepath_or_content, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                return True
        elif filepath_or_content.startswith(("http://", "https://")):
            return True
        cl = content.lower()
        if "type=subtitles" in cl or "#ext-x-subtitles" in cl:
            return True
        if 'contenttype="text"' in cl or 'mimetype="text/vtt"' in cl or 'application/ttml+xml' in cl or '<subtitle' in cl:
            return True
        return False

    @staticmethod
    def parse_input(raw_text: str) -> Dict[str, Any]:
        """Extract stream URL, cookies, custom headers, referer, and origin from cURL or URL string."""
        text = str(raw_text).strip()
        url = ""
        headers: Dict[str, str] = {}

        if "curl" in text.lower():
            # Clean Windows cmd-style ^ quoting and escaped quotes
            cleaned = (
                text
                .replace('^"', '"')
                .replace('^&', '&')
                .replace('^^', '^')
                .replace('^ ', ' ')
            )
            cleaned = re.sub(r'\^(?=[^\n])', '', cleaned)

            # Match URL
            url_match = re.search(
                r'(?:--url|-u)?\s*["\']?(https?://[^\s"\'\\]+)["\']?',
                cleaned, re.IGNORECASE
            )
            if url_match:
                url = url_match.group(1).rstrip('"\'')

            # Match Headers
            header_matches = re.findall(r'-H\s+["\']([^"\']+)["\']', cleaned, re.IGNORECASE)
            for h in header_matches:
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            # Match -b or --cookie
            cookie_match = re.search(r'(?:-b|--cookie)\s+["\']([^"\']+)["\']', cleaned, re.IGNORECASE)
            if cookie_match and "cookie" not in headers:
                headers["cookie"] = cookie_match.group(1).strip()
        else:
            url_match = re.search(r'https?://[^\s"\']+', text)
            if url_match:
                url = url_match.group(0).rstrip('"\'')

        # Fallback defaults for popular stream CDNs if missing
        referer = headers.get("referer", "https://net52.cc/")
        user_agent = headers.get("user-agent", DEFAULT_UA)
        origin = headers.get("origin", "https://net52.cc")

        return {
            "url": url,
            "referer": referer,
            "user_agent": user_agent,
            "origin": origin,
            "headers": headers
        }

    def fetch_master_playlist(self, info: Dict[str, Any], temp_dir: str) -> str:
        """Download master playlist to local cache to verify access and guard against expiry."""
        url = info["url"]
        if not url:
            raise ValueError("No valid URL found in input.")

        os.makedirs(temp_dir, exist_ok=True)
        local_path = os.path.join(temp_dir, f"master_{int(time.time()*1000)}.m3u8")

        curl_cmd = [
            "curl.exe", "-s", "-L", url,
            "-H", f"Referer: {info['referer']}",
            "-H", f"Origin: {info['origin']}",
            "-H", f"User-Agent: {info['user_agent']}",
            "--connect-timeout", "5",
            "--max-time", "10",
            "-o", local_path,
        ]

        if "cookie" in info["headers"]:
            curl_cmd.extend(["-H", f"Cookie: {info['headers']['cookie']}"])

        # Forward all custom headers (Authorization, token, sec-ch-ua, etc.)
        skip_headers = {"referer", "origin", "user-agent", "cookie", "host", "content-length", "connection", "accept-encoding"}
        for h_name, h_val in info.get("headers", {}).items():
            if h_name.lower() not in skip_headers and h_val:
                curl_cmd.extend(["-H", f"{h_name}: {h_val}"])

        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        curl_proc = subprocess.Popen(
            curl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        self.current_process = curl_proc
        try:
            stdout, stderr = curl_proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                curl_proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"Connection timed out while fetching playlist: {url}")
        finally:
            self.current_process = None

        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        if curl_proc.returncode != 0 or not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise RuntimeError(f"Could not fetch playlist: {url}")

        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(600)

        if any(x in content for x in ["Only Valid Users", "403 Forbidden", "Access Denied"]) or \
           "<html" in content.lower():
            raise RuntimeError(
                "Session expired or access denied by remote host. Please copy a fresh stream link or cURL command."
            )

        # Normalize master playlist: make any relative stream / audio / subtitle URLs absolute
        # so each sub-stream resolves its segments against its own CDN host without global --base-url conflicts.
        try:
            with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            modified = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#EXT-X-MEDIA") and 'URI="' in stripped:
                    def _replace_uri(m):
                        sub_uri = m.group(1)
                        if not sub_uri.startswith(("http://", "https://")):
                            abs_sub = urllib.parse.urljoin(url, sub_uri)
                            return f'URI="{abs_sub}"'
                        return m.group(0)

                    new_line = re.sub(r'URI="([^"]+)"', _replace_uri, line)
                    if new_line != line:
                        modified = True
                    new_lines.append(new_line)
                elif stripped and not stripped.startswith("#"):
                    if not stripped.startswith(("http://", "https://")):
                        abs_stream = urllib.parse.urljoin(url, stripped)
                        new_lines.append(abs_stream + "\n")
                        modified = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            if modified:
                with open(local_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
        except Exception:
            pass

        return local_path

    def _download_direct_file(
        self,
        info: Dict[str, Any],
        output_path: str,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """High-speed streaming downloader for direct media files (MP4, MKV, WebM, MP3, etc.)."""
        url = info["url"]
        req = urllib.request.Request(url)
        req.add_header("User-Agent", info.get("user_agent", DEFAULT_UA))
        req.add_header("Referer", info.get("referer", ""))
        req.add_header("Origin", info.get("origin", ""))
        if "cookie" in info.get("headers", {}):
            req.add_header("Cookie", info["headers"]["cookie"])

        chunk_size = 1024 * 1024  # 1MB buffer for fast streaming
        downloaded = 0
        start_time = time.time()
        last_progress_time = 0.0

        with urllib.request.urlopen(req, timeout=30) as resp, open(output_path, "wb") as f:
            total_size = int(resp.getheader("Content-Length") or 0)
            while not self._is_aborted:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if progress_callback and (now - last_progress_time > 0.15):
                    elapsed = max(0.001, now - start_time)
                    speed_bps = downloaded / elapsed
                    if total_size > 0:
                        pct = downloaded / total_size * 100.0
                        remaining = max(0, total_size - downloaded)
                        eta_sec = (remaining / max(1, downloaded)) * elapsed
                        if total_size >= 1024 * 1024 * 1024:
                            size_str = f"{downloaded / (1024**3):.2f} GB / {total_size / (1024**3):.2f} GB"
                        else:
                            size_str = f"{downloaded / (1024**2):.1f} MB / {total_size / (1024**2):.1f} MB"
                        msg = _build_progress_message(pct, speed_bps=speed_bps, eta_sec=eta_sec, size=size_str)
                    else:
                        pct = min(95.0, 5.0 + (downloaded / (1024 * 1024)) * 2.0)
                        if downloaded >= 1024 * 1024 * 1024:
                            size_str = f"{downloaded / (1024**3):.2f} GB downloaded"
                        else:
                            size_str = f"{downloaded / (1024**2):.1f} MB downloaded"
                        msg = _build_progress_message(pct, speed_bps=speed_bps, size=size_str)
                    progress_callback(pct, msg)
                    last_progress_time = now

        if self._is_aborted:
            if os.path.exists(output_path):
                os.remove(output_path)
            raise RuntimeError("Download aborted by user.")

        return output_path

    def run_download(
        self,
        input_text: str,
        save_name: str = "",
        save_dir: str = DEFAULT_SAVE_DIR,
        resolution: str = "1080p",
        audio_choice: str = "all",
        include_subtitles: bool = True,
        sub_format: str = "SRT",
        sub_lang: str = "all",
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """Execute high-speed concurrent multi-audio stream capture and MKV muxing."""
        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        def log(msg: str):
            if log_callback:
                log_callback(msg)
            else:
                print(msg, flush=True)

        sep = "━" * 60
        log(sep)
        log("  OmniStream Pro v2.3.0  •  High-Speed Multi-Audio Engine")
        log(sep)

        # Step 1: Verify binaries
        log("[1/4] Checking required streaming binaries (N_m3u8DL-RE & FFmpeg)...")
        n_m3u8_path, ffmpeg_path = ensure_dependencies(
            status_callback=log,
            progress_callback=progress_callback,
        )

        # Step 2: Parse source
        log("[2/4] Parsing stream metadata...")
        info = self.parse_input(input_text)
        if not info["url"]:
            raise ValueError(
                "No valid stream URL detected. Paste a cURL command or direct stream URL."
            )

        url_clean = info['url'].split('?')[0]
        is_m3u8_or_mpd = (
            re.search(r'\.(m3u8|mpd)($|\?)', info["url"], re.IGNORECASE) or
            ("hls" in info["url"].lower() and "segment" not in info["url"].lower())
        )

        url_display = info['url'][:80] + ('...' if len(info['url']) > 80 else '')
        log(f"  Source   : {url_display}")
        log(f"  Referer  : {info['referer']}")

        # Auto-detect title if empty
        if not save_name:
            id_match = re.search(r'(\d{6,10})', info["url"])
            if id_match:
                save_name = f"OmniStream_{id_match.group(1)}"
            else:
                save_name = f"OmniStream_{int(time.time())}"

        # Clean filename and strip trailing stream extensions to prevent double extensions (e.g. .m3u8.mkv)
        save_name = re.sub(r'\.(m3u8|mpd|mp4|webm|mkv|m4v|ts)$', '', save_name, flags=re.IGNORECASE)
        save_name = re.sub(r'[\\/*?:"<>|]', "", save_name).strip()
        if not save_name:
            save_name = f"OmniStream_{int(time.time())}"

        # Determine container extension
        is_direct_mp4 = bool(re.search(r'\.(mp4|m4v)($|\?)', info["url"], re.IGNORECASE))
        target_ext = ".mp4" if (is_direct_mp4 and not is_m3u8_or_mpd) else ".mkv"

        # Auto-resolve duplicate file conflict
        base_name = save_name
        counter = 1
        while os.path.exists(os.path.join(save_dir, f"{save_name}{target_ext}")):
            save_name = f"{base_name}_{counter}"
            counter += 1

        target_file = os.path.join(save_dir, f"{save_name}{target_ext}")
        log(f"  Target   : {os.path.basename(target_file)}")
        log(f"  Location : {save_dir}")

        # If it's a direct non-playlist media file, use direct streaming downloader
        if not is_m3u8_or_mpd and is_direct_mp4:
            log("[3/4] Direct video stream detected — downloading media...")
            out = self._download_direct_file(info, target_file, log_callback, progress_callback)
            log(f"  [SUCCESS] Download completed: {out}")
            if progress_callback:
                progress_callback(100.0, "Download complete!")
            return out

        # Step 3: Fetch playlist (for HLS/DASH)
        log("[3/4] Fetching stream playlist...")
        temp_dir = os.path.join(save_dir, f".omnistream_tmp_{os.getpid()}_{int(time.time())}")
        playlist_downloaded = False
        try:
            target_source = self.fetch_master_playlist(info, temp_dir)
            log(f"  Playlist cached ({os.path.getsize(target_source):,} bytes).")
            playlist_downloaded = True
        except Exception as exc:
            if "aborted" in str(exc).lower():
                raise
            log(f"  Notice: Direct stream URL mode ({exc}).")
            target_source = info["url"]

        # Resolution mapping — matches resolution strings like '1920x1080', '1280x720', etc.
        res_map = {
            "best":  "best",
            "1080p": 'res="1080|1920":for=best',
            "720p":  'res="720|1280":for=best',
            "480p":  'res="480|854":for=best',
            "audio_only": "none",
        }
        video_sel = res_map.get(resolution, "best")

        # Audio track mapping
        audio_sel_map = {
            "all":   "all",
            "en_hi": "lang=eng,hin",
            "eng":   "lang=eng",
            "hin":   "lang=hin",
        }
        audio_sel = audio_sel_map.get(audio_choice, "all")

        # Build command for N_m3u8DL-RE
        cmd = [
            n_m3u8_path,
            target_source,
            "--auto-select",
            "-sv", video_sel,
            "-sa", audio_sel,
            "-mt",                  # concurrent multi-track downloads
            "--save-dir", save_dir,
            "--save-name", save_name,
            "-M", "format=mkv:muxer=ffmpeg",
            "--ffmpeg-binary-path", ffmpeg_path,
            "--thread-count", "32",
            "--download-retry-count", "3",
            "--http-request-timeout", "15",
            "--disable-update-check",
            "--no-log",
            "--check-segments-count", "false",
            "-H", f"Referer: {info['referer']}",
            "-H", f"Origin: {info['origin']}",
            "-H", f"User-Agent: {info['user_agent']}",
            "--no-ansi-color",
        ]

        # Embed subtitles into final MKV if requested
        if include_subtitles:
            has_subs = True
            if playlist_downloaded and os.path.exists(target_source):
                has_subs = self.has_subtitle_tracks(target_source)

            if has_subs:
                log("  Subtitles: Embedding subtitle tracks into final MKV container.")
                cmd.extend([
                    "--sub-format", sub_format.upper(),
                    "--auto-subtitle-fix",
                ])
                if sub_lang and sub_lang.lower() != "all":
                    cmd.extend(["-ss", f"lang={sub_lang}"])
                else:
                    cmd.extend(["-ss", "all"])
            else:
                log("  Notice: No subtitle tracks detected in stream playlist. Proceeding with video and all multi-audio tracks.")

        if "cookie" in info["headers"]:
            cmd.extend(["-H", f"Cookie: {info['headers']['cookie']}"])

        # Forward all custom headers to N_m3u8DL-RE
        skip_headers = {"referer", "origin", "user-agent", "cookie", "host", "content-length", "connection", "accept-encoding"}
        for h_name, h_val in info.get("headers", {}).items():
            if h_name.lower() not in skip_headers and h_val:
                cmd.extend(["-H", f"{h_name}: {h_val}"])

        log("[4/4] Starting concurrent download with 32 parallel threads...")
        log(sep)

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        # Binary + split on \r/\n: N_m3u8DL-RE refreshes progress with CR, not NL.
        # Run 100% silently in background without console window popup.
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        final_mkv = os.path.join(save_dir, f"{save_name}.mkv")
        last_progress_update = 0.0
        progress_started = time.time()
        last_pct = 0.0
        last_speed_bps: Optional[float] = None    # EMA-smoothed speed (B/s)
        last_eta_sec:   Optional[float] = None    # last known ETA
        track_progress: Dict[str, float] = {}     # per-track % for weighted avg
        recent_error_lines = []
        _keywords = (
            "Vid ", "Aud ", "INFO", "WARN", "ERROR", "Exception",
            "Mux", "Merging", "Done", "Fail", "success", "stream",
            "403", "401", "Forbidden", "Unauthorized",
        )

        if progress_callback:
            progress_callback(0.0, "Starting download…  ·  0.0% done  ·  100.0% left")

        # Regex to split on \r, \n, OR lookahead to new record boundary in continuous redirected output
        split_pat = re.compile(
            rb'[\r\n]+|(?<=[^\r\n])(?=(?:Vid |Aud |Sub |\[Progress\]|\[download\]|\d{2}:\d{2}:\d{2}\.\d{3}\s+(?:INFO|WARN|ERROR)))'
        )

        last_known_size: Optional[str] = None
        buf = b""
        while True:
            if self._is_aborted:
                log("[Aborted] Download cancelled by user.")
                break

            chunk = self.current_process.stdout.read(4096)
            if not chunk:
                break
            buf += chunk

            parts = split_pat.split(buf)
            if len(parts) > 1:
                completed_lines = parts[:-1]
                buf = parts[-1]
            else:
                completed_lines = []

            for raw_chunk in completed_lines:
                line = raw_chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                clean_line = _strip_ansi(line)

                cl_low = clean_line.lower()
                if any(w in cl_low for w in (
                    "error", "fail", "403", "401", "exception",
                    "forbidden", "unauthorized", "unhandled", "segment",
                )):
                    recent_error_lines.append(clean_line)
                    if len(recent_error_lines) > 10:
                        recent_error_lines.pop(0)

                parsed = _parse_progress_line(line)
                now = time.time()
                if parsed:
                    raw_pct   = parsed["pct"]
                    speed_bps = parsed.get("speed_bps")
                    eta_sec   = parsed.get("eta_sec")
                    track     = parsed.get("track", "main")

                    if parsed.get("size"):
                        # Keep best size (prefer MB/GB size over segs)
                        if "segs" not in parsed["size"] or not last_known_size or "segs" in last_known_size:
                            last_known_size = parsed["size"]

                    # Multi-track progress tracking
                    if track == "vid":
                        track_progress["vid"] = raw_pct
                    elif track == "aud":
                        existing = {k: v for k, v in track_progress.items() if k.startswith("aud")}
                        if existing:
                            closest = min(existing, key=lambda k: abs(existing[k] - raw_pct))
                            track_progress[closest] = raw_pct
                        else:
                            track_progress["aud_0"] = raw_pct
                    else:
                        track_progress["main"] = raw_pct

                    # Video track is the primary payload (>90% of file size).
                    # Audio tracks are tiny and finish quickly; they must not cause overall progress to falsely jump to 99%.
                    aud_vals = [v for k, v in track_progress.items() if k.startswith("aud")]
                    aud_avg = sum(aud_vals) / len(aud_vals) if aud_vals else 0.0

                    if "vid" in track_progress:
                        vid_pct = track_progress["vid"]
                        avg_pct = vid_pct * 0.90 + aud_avg * 0.10
                    elif "main" in track_progress:
                        avg_pct = track_progress["main"]
                    else:
                        # Only audio streams reported so far; keep progress at a modest early percentage
                        avg_pct = min(10.0, aud_avg * 0.10)

                    # Cap at 99.0% until file is fully written and verified
                    last_pct = max(last_pct, min(99.0, avg_pct))

                    if speed_bps and speed_bps > 0:
                        last_speed_bps = (
                            speed_bps if last_speed_bps is None
                            else 0.3 * speed_bps + 0.7 * last_speed_bps
                        )

                    if eta_sec is not None:
                        last_eta_sec = eta_sec
                    elif last_pct > 0.5:
                        elapsed = max(0.001, now - progress_started)
                        last_eta_sec = (elapsed / last_pct) * (100.0 - last_pct)

                    if progress_callback and (now - last_progress_update >= 0.10):
                        msg = _build_progress_message(
                            last_pct,
                            speed_bps=last_speed_bps,
                            eta_sec=last_eta_sec,
                            size=last_known_size,
                            fallback=parsed.get("status", "")
                        )
                        progress_callback(last_pct, msg)
                        last_progress_update = now

                if any(k in clean_line for k in _keywords):
                    if not parsed or any(k in clean_line for k in
                                        ("INFO", "WARN", "ERROR", "Mux", "Merging", "Done", "403", "401", "Fail")):
                        log(f"  {clean_line}")

        if buf.strip():
            leftover = buf.decode("utf-8", errors="replace").strip()
            parsed_leftover = _parse_progress_line(leftover)
            if parsed_leftover and progress_callback:
                msg = _build_progress_message(
                    max(last_pct, parsed_leftover["pct"]),
                    speed_bps=last_speed_bps,
                    eta_sec=0,
                    size=last_known_size,
                    fallback=parsed_leftover.get("status", "")
                )
                progress_callback(max(last_pct, parsed_leftover["pct"]), msg)
            elif leftover and any(k in leftover for k in _keywords):
                log(f"  {leftover}")

        self.current_process.stdout.close()
        self.current_process.wait()

        # Clean cache
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        rc = self.current_process.returncode

        if os.path.exists(final_mkv) and os.path.getsize(final_mkv) > 0:
            size_mb = os.path.getsize(final_mkv) / (1024 * 1024)
            log(sep)
            log("  [SUCCESS] All audio & video tracks downloaded & muxed!")
            log(f"  File : {final_mkv}")
            log(f"  Size : {size_mb:.2f} MB")
            log(sep)
            # ── Auto-cleanup: remove intermediate files, keep only the final MKV
            log("  [Cleanup] Removing intermediate segment files...")
            self.cleanup_intermediate_files(
                save_dir=save_dir,
                save_name=save_name,
                final_file=final_mkv,
                log_callback=log,
            )
            if progress_callback:
                progress_callback(100.0, "Download and mux complete!")
            return final_mkv
        else:
            err_reason = ""
            fix_hint = "If the session or token expired, please open the video again in Chrome and capture a fresh link via the OmniStream extension."
            if recent_error_lines:
                combined = " ".join(recent_error_lines).lower()
                if "403" in combined or "forbidden" in combined or "unauthorized" in combined:
                    err_reason = "Remote stream token expired (HTTP 403 Forbidden)."
                    fix_hint = "Your stream token has expired. Please re-open the video in Chrome, wait for it to start playing, then capture the link again via the OmniStream extension."
                elif "first segment" in combined or "download first" in combined:
                    # N_m3u8DL-RE: 'Download first segment failed'
                    err_reason = recent_error_lines[-1]
                    fix_hint = (
                        "The stream server rejected the first segment download. This usually means:\n"
                        "  • The stream URL or DRM tokens have expired — re-open the video in Chrome and re-capture.\n"
                        "  • Or the stream uses per-session authentication that has timed out."
                    )
                elif "unhandled exception" in combined:
                    err_reason = recent_error_lines[-1]
                    fix_hint = "An internal downloader error occurred. Try re-capturing the stream link from Chrome."
                else:
                    err_reason = recent_error_lines[-1]

            reason_str = f" Reason: {err_reason}" if err_reason else ""
            raise RuntimeError(
                f"Download failed (exit code {rc}).{reason_str}\n\n{fix_hint}"
            )

    def run_subtitle_download(
        self,
        input_text: str,
        save_name: str = "",
        save_dir: str = DEFAULT_SAVE_DIR,
        sub_format: str = "SRT",
        sub_lang: str = "all",
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> list:
        """Download only subtitle tracks from an HLS/DASH stream using N_m3u8DL-RE --sub-only.

        Args:
            input_text: cURL command or direct M3U8/MPD URL.
            save_name:  Base filename (without extension). Auto-detected if empty.
            save_dir:   Destination folder for subtitle files.
            sub_format: 'SRT' or 'VTT' (default SRT).
            sub_lang:   'all' to grab every language, or a BCP-47 lang code e.g. 'eng', 'hin'.
            log_callback: Optional function called with log lines.
            progress_callback: Optional function called with (pct, message).

        Returns:
            List of absolute paths of saved subtitle files.
        """
        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        def log(msg: str):
            if log_callback:
                log_callback(msg)
            else:
                print(msg, flush=True)

        sep = "━" * 60
        log(sep)
        log("  OmniStream Pro  •  Subtitle-Only Download Engine")
        log(sep)

        # Step 1: Verify binaries
        log("[1/4] Checking required streaming binaries (N_m3u8DL-RE & FFmpeg)...")
        n_m3u8_path, ffmpeg_path = ensure_dependencies(
            status_callback=log,
            progress_callback=progress_callback,
        )

        # Step 2: Parse source
        log("[2/4] Parsing stream metadata...")
        info = self.parse_input(input_text)
        if not info["url"]:
            raise ValueError("No valid stream URL detected. Paste a cURL command or direct M3U8 link.")

        url_display = info["url"][:80] + ("..." if len(info["url"]) > 80 else "")
        log(f"  Source   : {url_display}")
        log(f"  Format   : {sub_format.upper()}")
        log(f"  Language : {sub_lang if sub_lang != 'all' else 'All Available'}")

        # Auto-detect title if empty
        if not save_name:
            id_match = re.search(r"(\d{6,10})", info["url"])
            save_name = f"OmniStream_{id_match.group(1)}" if id_match else f"OmniStream_{int(time.time())}"

        save_name = re.sub(r"\.(m3u8|mpd|mp4|webm|mkv|m4v|ts)$", "", save_name, flags=re.IGNORECASE)
        save_name = re.sub(r'[\\/*?:"<>|]', "", save_name).strip()
        if not save_name:
            save_name = f"OmniStream_{int(time.time())}"

        log(f"  Filename : {save_name}")
        log(f"  Location : {save_dir}")

        # Step 3: Fetch playlist
        log("[3/4] Fetching stream playlist to locate subtitle tracks...")
        temp_dir = os.path.join(save_dir, f".omnistream_tmp_{os.getpid()}_{int(time.time())}")
        playlist_downloaded = False
        try:
            target_source = self.fetch_master_playlist(info, temp_dir)
            log(f"  Playlist cached ({os.path.getsize(target_source):,} bytes).")
            playlist_downloaded = True
        except Exception as exc:
            if "aborted" in str(exc).lower():
                raise
            log(f"  Notice: Direct stream URL mode ({exc}).")
            target_source = info["url"]

        # Pre-check if stream actually contains any subtitle tracks
        if playlist_downloaded and os.path.exists(target_source):
            if not self.has_subtitle_tracks(target_source):
                log("  Notice: No subtitle tracks found in this stream playlist.")
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                raise RuntimeError(
                    "No subtitle tracks were found in this stream.\n\n"
                    "This stream provides video and audio, but does not contain any embedded subtitle tracks in its playlist."
                )

        if progress_callback:
            progress_callback(5.0, "Fetching subtitle tracks…  ·  0% done  ·  100% left")

        # Step 4: Build N_m3u8DL-RE command — subtitle only
        cmd = [
            n_m3u8_path,
            target_source,
            "--sub-only",                           # Download only subtitle tracks
            "--sub-format", sub_format.upper(),     # SRT or VTT
            "--auto-subtitle-fix",                  # Auto-fix subtitle timing issues
            "--save-dir", save_dir,
            "--save-name", save_name,
            "--thread-count", "16",
            "--download-retry-count", "3",
            "--http-request-timeout", "15",
            "--disable-update-check",
            "--no-log",
            "-H", f"Referer: {info['referer']}",
            "-H", f"Origin: {info['origin']}",
            "-H", f"User-Agent: {info['user_agent']}",
            "--no-ansi-color",
        ]

        # Language filter: if not 'all', use -ss lang=<code>
        if sub_lang and sub_lang.lower() != "all":
            cmd.extend(["-ss", f"lang={sub_lang}"])
        else:
            cmd.extend(["-ss", "all"])

        if "cookie" in info["headers"]:
            cmd.extend(["-H", f"Cookie: {info['headers']['cookie']}"])

        skip_headers = {"referer", "origin", "user-agent", "cookie", "host", "content-length", "connection", "accept-encoding"}
        for h_name, h_val in info.get("headers", {}).items():
            if h_name.lower() not in skip_headers and h_val:
                cmd.extend(["-H", f"{h_name}: {h_val}"])

        log("[4/4] Downloading subtitle tracks (no video/audio)...")
        log(sep)

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        split_pat = re.compile(
            rb'[\r\n]+|(?<=[^\r\n])(?=(?:Sub |Vid |Aud |\[Progress\]|\[download\]|\d{2}:\d{2}:\d{2}\.\d{3}\s+(?:INFO|WARN|ERROR)))'
        )

        recent_error_lines = []
        last_pct = 0.0
        last_progress_update = 0.0
        buf = b""

        while True:
            if self._is_aborted:
                log("[Aborted] Subtitle download cancelled by user.")
                break

            chunk = self.current_process.stdout.read(4096)
            if not chunk:
                break
            buf += chunk

            parts = split_pat.split(buf)
            if len(parts) > 1:
                completed_lines, buf = parts[:-1], parts[-1]
            else:
                completed_lines = []

            for raw_chunk in completed_lines:
                line = raw_chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                clean_line = _strip_ansi(line)
                cl_low = clean_line.lower()

                if any(w in cl_low for w in ("error", "fail", "403", "401", "exception", "forbidden", "unhandled", "segment")):
                    recent_error_lines.append(clean_line)
                    if len(recent_error_lines) > 10:
                        recent_error_lines.pop(0)

                parsed = _parse_progress_line(line)
                now = time.time()
                if parsed:
                    raw_pct = parsed["pct"]
                    last_pct = max(last_pct, raw_pct)
                    if progress_callback and (now - last_progress_update >= 0.15):
                        msg = _build_progress_message(
                            last_pct,
                            speed_bps=parsed.get("speed_bps"),
                            eta_sec=parsed.get("eta_sec"),
                            size=parsed.get("size"),
                            fallback=parsed.get("status", ""),
                        )
                        progress_callback(last_pct, msg)
                        last_progress_update = now

                if any(k in clean_line for k in ("Sub ", "INFO", "WARN", "ERROR", "Done", "Fail", "success")):
                    log(f"  {clean_line}")

        self.current_process.stdout.close()
        self.current_process.wait()

        # Clean temp dir
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

        if self._is_aborted:
            raise RuntimeError("Operation aborted by user.")

        rc = self.current_process.returncode

        # Collect subtitle files saved by N_m3u8DL-RE
        ext = f".{sub_format.lower()}"
        saved_subs = []
        try:
            stem_lower = save_name.lower()
            for fname in os.listdir(save_dir):
                if fname.lower().endswith(ext) and stem_lower in fname.lower():
                    saved_subs.append(os.path.join(save_dir, fname))
        except Exception:
            pass

        if saved_subs:
            log(sep)
            log(f"  [SUCCESS] {len(saved_subs)} subtitle file(s) saved!")
            for sp in saved_subs:
                log(f"    {os.path.basename(sp)}")
            log(sep)
            if progress_callback:
                progress_callback(100.0, f"Subtitles saved: {len(saved_subs)} file(s)")
            return saved_subs

        # If no files found, check for error
        err_reason = ""
        if recent_error_lines:
            combined = " ".join(recent_error_lines).lower()
            if "no stream found" in combined or "no subtitle" in combined:
                err_reason = "No subtitle tracks found in this stream."
            elif "403" in combined or "forbidden" in combined:
                err_reason = "Remote stream token expired (HTTP 403 Forbidden)."
            elif "first segment" in combined:
                err_reason = "The stream server rejected the first segment. Try re-capturing a fresh link."
            else:
                err_reason = "No subtitle tracks found in this stream."

        if rc == 0 and not saved_subs:
            raise RuntimeError(
                "No subtitle tracks found in this stream.\n\n"
                "Subtitle download completed but no subtitle files were found in the stream."
            )

        if not saved_subs:
            raise RuntimeError(
                f"No subtitle tracks were found in this stream.\n\n"
                f"{err_reason}\n\n"
                "This stream does not contain embedded subtitles in its playlist."
            )


# Backward-compatibility alias
DownloadEngine = OmniStreamEngine

