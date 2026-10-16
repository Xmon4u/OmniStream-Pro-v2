"""
OmniStream Pro v2.0.0 - High Performance Multi-Stream Engine
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
    """Format speed in B/s to human-readable KB/s or MB/s string."""
    if speed_bps is None or speed_bps <= 0:
        return ""
    if speed_bps >= 1024 * 1024:
        return f"{speed_bps / (1024*1024):.1f} MB/s"
    elif speed_bps >= 1024:
        return f"{speed_bps / 1024:.0f} KB/s"
    return f"{speed_bps:.0f} B/s"


def _parse_progress_line(line: str) -> Optional[Dict[str, Any]]:
    """Extract percent / speed / ETA from N_m3u8DL-RE or similar console output.

    N_m3u8DL-RE progress line examples:
      Vid  [============>   ] 58.2%  12.4 MB/s  ETA: 0:01:23
      Aud  [====>           ] 23.0%  8.1 MB/s  ETA: 0:02:41
      [Progress] 45%  |  10.5 MB/s  |  00:01:30
      Downloading: 67.3%  Speed: 15.2 MB/s  ETA: 0:00:45
    """
    # Strip ANSI escape codes first
    clean = _strip_ansi(line)

    # Must contain a percentage
    pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', clean)
    if not pct_match:
        return None

    pct = max(0.0, min(100.0, float(pct_match.group(1))))

    # ── Speed parsing (handles KB/s, MB/s, GB/s, KiB/s, MiB/s) ──────────────
    speed_bps: Optional[float] = None
    # Pattern: number + optional space + unit
    speed_match = re.search(
        r'(\d+(?:\.\d+)?)\s*([KMGT]i?B)(?:/s|ps|\s+/\s*s)',
        clean, re.IGNORECASE
    )
    if speed_match:
        val = float(speed_match.group(1))
        unit = speed_match.group(2).upper().replace('IB', 'B')  # KiB -> KB
        multipliers = {'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
        speed_bps = val * multipliers.get(unit, 1024**2)
    else:
        # Fallback: bare number + B/s / KB/s / MB/s without slash
        speed_match2 = re.search(
            r'(\d+(?:\.\d+)?)\s*(K|M|G)?B/?s',
            clean, re.IGNORECASE
        )
        if speed_match2:
            val = float(speed_match2.group(1))
            unit = (speed_match2.group(2) or '').upper()
            mult = {'K': 1024, 'M': 1024**2, 'G': 1024**3}.get(unit, 1)
            speed_bps = val * mult

    # ── ETA parsing ───────────────────────────────────────────────────────────
    eta_sec: Optional[float] = None

    # Format: ETA: H:MM:SS or ETA: MM:SS or ETA: 0:MM:SS
    eta_match = re.search(
        r'(?:ETA|Left|Remain(?:ing)?|Time(?:left|\s+left)?)'  # keyword
        r'\s*[:\-]?\s*'                                        # separator
        r'(\d{1,2}):(\d{2})(?::(\d{2}))?',                   # H:MM:SS or MM:SS
        clean, re.IGNORECASE
    )
    if eta_match:
        g = [int(x) for x in eta_match.groups() if x is not None]
        if len(g) == 3:
            eta_sec = g[0] * 3600 + g[1] * 60 + g[2]
        elif len(g) == 2:
            eta_sec = g[0] * 60 + g[1]
    else:
        # Bare time near end of line (N_m3u8DL-RE style: "| 00:01:23 |")
        time_match = re.search(
            r'(?:[|\s])\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:[|\s]|$)',
            clean
        )
        if time_match and pct < 99.5:
            g = [int(x) for x in time_match.groups() if x is not None]
            if len(g) == 3:
                eta_sec = g[0] * 3600 + g[1] * 60 + g[2]
            elif len(g) == 2:
                eta_sec = g[0] * 60 + g[1]

    speed_mb = (speed_bps / (1024 * 1024)) if speed_bps is not None else None
    return {"pct": pct, "speed_bps": speed_bps, "speed": speed_mb, "eta_sec": eta_sec, "raw": clean}


def _build_progress_message(
    pct: float,
    speed_bps: Optional[float] = None,
    eta_sec: Optional[float] = None,
    fallback: str = "",
    # Legacy compat: accept 'speed' as MB/s float
    speed: Optional[float] = None,
) -> str:
    """Build a human-readable progress status string."""
    pct = max(0.0, min(100.0, pct))
    left = max(0.0, 100.0 - pct)

    # Normalise speed to BPS
    if speed_bps is None and speed is not None:
        speed_bps = speed * 1024 * 1024  # legacy: was in MB/s

    parts = [f"{pct:.1f}% done", f"{left:.1f}% left"]

    if eta_sec is not None and eta_sec >= 0:
        parts.append(f"ETA {_format_eta(eta_sec)}")

    if speed_bps is not None and speed_bps > 0:
        parts.append(_format_speed(speed_bps))
    elif fallback:
        snippet = fallback.strip()
        if len(snippet) > 60:
            snippet = snippet[:57] + "…"
        # Only append if it adds useful info
        if snippet and "%" not in snippet and ":" not in snippet:
            parts.append(snippet)

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
                self.current_process.terminate()
                time.sleep(0.4)
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
        We keep ONLY the final merged MKV and remove everything else that
        matches the save_name prefix and is NOT the final_file.
        """
        def _log(msg):
            if log_callback:
                log_callback(msg)

        if not final_file or not os.path.exists(final_file):
            return

        final_abs = os.path.abspath(final_file)
        removed = []
        errors = []

        # Patterns produced by N_m3u8DL-RE for intermediate tracks
        intermediate_patterns = [
            # video-only tracks before mux
            f"{save_name}.video.mp4",
            f"{save_name}.video.mkv",
            f"{save_name}_video.mp4",
            f"{save_name}_video.mkv",
            f"{save_name}.mp4",        # raw video stream (non-muxed)
        ]

        try:
            for fname in os.listdir(save_dir):
                fpath = os.path.abspath(os.path.join(save_dir, fname))
                if fpath == final_abs:
                    continue  # Never delete the final output

                base = fname.lower()
                stem = save_name.lower()

                # Skip if name doesn't start with our save_name
                if not base.startswith(stem):
                    continue

                # Remove intermediate audio/video segment files
                is_intermediate = (
                    base in [p.lower() for p in intermediate_patterns] or
                    # Audio track files: name_lang.m4a / name_lang.aac / name_audio_N.*
                    any(base.endswith(ext) for ext in (".m4a", ".aac", ".ts", ".mp4"))
                    and ("audio" in base or "_hin" in base or "_eng" in base
                         or "_jpn" in base or "_spa" in base or "_por" in base
                         or "_ara" in base or "_tel" in base or "_tam" in base
                         or "_kan" in base or "_mal" in base or "_ben" in base
                         or base.endswith(".ts")
                    ) or
                    # Catch-all: any .mp4 / .m4a / .ts / .aac with our prefix
                    # but NOT our final mkv
                    (
                        base.startswith(stem) and
                        base != os.path.basename(final_abs).lower() and
                        any(base.endswith(ext) for ext in (".mp4", ".m4a", ".aac", ".ts"))
                    )
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

        # Also remove the .omnistream_tmp_* temp folder if present
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
            _log(f"  [Cleanup] Removed {len(removed)} intermediate file(s): {', '.join(removed[:5])}{'...' if len(removed) > 5 else ''}")
        if errors:
            _log(f"  [Cleanup] Could not delete: {', '.join(errors[:3])}")

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
            "--max-time", "25",
            "-o", local_path,
        ]

        if "cookie" in info["headers"]:
            curl_cmd.extend(["-H", f"Cookie: {info['headers']['cookie']}"])

        # Forward all custom headers (Authorization, token, sec-ch-ua, etc.)
        skip_headers = {"referer", "origin", "user-agent", "cookie", "host", "content-length", "connection", "accept-encoding"}
        for h_name, h_val in info.get("headers", {}).items():
            if h_name.lower() not in skip_headers and h_val:
                curl_cmd.extend(["-H", f"{h_name}: {h_val}"])

        res = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0 or not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            raise RuntimeError(f"Could not fetch playlist: {url}")

        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(600)

        if any(x in content for x in ["Only Valid Users", "403 Forbidden", "Access Denied"]) or \
           "<html" in content.lower():
            raise RuntimeError(
                "Session expired or access denied by remote host. Please copy a fresh stream link or cURL command."
            )

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

        chunk_size = 128 * 1024
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
                if progress_callback and (now - last_progress_time > 0.2):
                    elapsed = max(0.001, now - start_time)
                    speed_mb = (downloaded / (1024 * 1024)) / elapsed
                    if total_size > 0:
                        pct = downloaded / total_size * 100.0
                        remaining = max(0, total_size - downloaded)
                        eta_sec = (remaining / max(1, downloaded)) * elapsed
                        msg = _build_progress_message(pct, speed_mb, eta_sec)
                        msg += f"  ·  {downloaded / (1024 * 1024):.1f}/{total_size / (1024 * 1024):.1f} MB"
                    else:
                        pct = min(95.0, 5.0 + (downloaded / (1024 * 1024)) * 2.0)
                        msg = (
                            f"Downloading…  {downloaded / (1024 * 1024):.1f} MB  ·  "
                            f"{speed_mb:.1f} MB/s  ·  size unknown"
                        )
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
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """Execute high-speed concurrent multi-audio stream capture and MKV muxing."""
        self._is_aborted = False

        def log(msg: str):
            if log_callback:
                log_callback(msg)
            else:
                print(msg, flush=True)

        sep = "━" * 60
        log(sep)
        log("  OmniStream Pro v2.0.0  •  High-Speed Multi-Audio Engine")
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

        # Clean filename
        save_name = re.sub(r'[\\/*?:"<>|]', "", save_name).strip().replace(" ", "_")
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
        try:
            target_source = self.fetch_master_playlist(info, temp_dir)
            log(f"  Playlist cached ({os.path.getsize(target_source):,} bytes).")
        except Exception as exc:
            log(f"  Notice: Direct stream URL mode ({exc}).")
            target_source = info["url"]

        # Resolution mapping
        res_map = {
            "best":  "best",
            "1080p": "res=1080p",
            "720p":  "res=720p",
            "480p":  "res=480p",
            "audio_only": "none",
        }
        video_sel = res_map.get(resolution, "res=1080p")

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
            "--thread-count", "16",
            "--download-retry-count", "10",
            "--check-segments-count", "false",
            "-H", f"Referer: {info['referer']}",
            "-H", f"Origin: {info['origin']}",
            "-H", f"User-Agent: {info['user_agent']}",
            "--no-ansi-color",
        ]

        if "cookie" in info["headers"]:
            cmd.extend(["-H", f"Cookie: {info['headers']['cookie']}"])

        # Forward all custom headers to N_m3u8DL-RE
        skip_headers = {"referer", "origin", "user-agent", "cookie", "host", "content-length", "connection", "accept-encoding"}
        for h_name, h_val in info.get("headers", {}).items():
            if h_name.lower() not in skip_headers and h_val:
                cmd.extend(["-H", f"{h_name}: {h_val}"])

        log("[4/4] Starting concurrent download with 16 parallel threads...")
        log(sep)

        # Binary + split on \r/\n: N_m3u8DL-RE refreshes progress with CR, not NL.
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )

        final_mkv = os.path.join(save_dir, f"{save_name}.mkv")
        last_progress_update = 0.0
        progress_started = time.time()
        last_pct = 0.0
        last_speed_bps: Optional[float] = None    # EMA-smoothed speed (B/s)
        last_eta_sec:   Optional[float] = None    # last known ETA
        track_progress: Dict[str, float] = {}     # per-track % for weighted avg
        _keywords = (
            "Vid ", "Aud ", "INFO", "WARN", "ERROR", "Exception",
            "Mux", "Merging", "Done", "Fail", "success", "stream",
        )

        if progress_callback:
            progress_callback(0.0, "Starting download…  ·  0.0% done  ·  100.0% left")

        buf = b""
        while True:
            if self._is_aborted:
                log("[Aborted] Download cancelled by user.")
                break

            chunk = self.current_process.stdout.read(256)
            if not chunk:
                break
            buf += chunk

            while True:
                i_n = buf.find(b"\n")
                i_r = buf.find(b"\r")
                if i_n < 0 and i_r < 0:
                    break
                if i_n < 0:
                    idx = i_r
                elif i_r < 0:
                    idx = i_n
                else:
                    idx = min(i_n, i_r)

                raw_line = buf[:idx]
                buf = buf[idx + 1:]
                # Swallow LF that follows CR (CRLF)
                if raw_line.endswith(b"\r"):
                    raw_line = raw_line[:-1]
                if buf.startswith(b"\n"):
                    buf = buf[1:]

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                # Strip ANSI for logging / keyword matching
                clean_line = _strip_ansi(line)

                parsed = _parse_progress_line(line)
                now = time.time()
                if parsed and progress_callback and (now - last_progress_update > 0.12):
                    raw_pct   = parsed["pct"]
                    speed_bps = parsed.get("speed_bps")
                    eta_sec   = parsed.get("eta_sec")

                    # ── Multi-track weighted average ───────────────────────────
                    cl = clean_line.lower()
                    if cl.startswith("vid") or "video" in cl[:14]:
                        track_progress["vid"] = raw_pct
                    elif cl.startswith("aud") or "audio" in cl[:14]:
                        # Find closest existing aud bucket or create new one
                        existing = {k: v for k, v in track_progress.items()
                                    if k.startswith("aud")}
                        if existing:
                            closest = min(existing, key=lambda k: abs(existing[k] - raw_pct))
                            track_progress[closest] = raw_pct
                        else:
                            track_progress["aud_0"] = raw_pct
                    else:
                        track_progress["main"] = raw_pct

                    if len(track_progress) >= 2:
                        vid_pct  = track_progress.get("vid", 0.0)
                        aud_vals = [v for k, v in track_progress.items()
                                    if k.startswith("aud")]
                        aud_avg  = sum(aud_vals) / len(aud_vals) if aud_vals else 0.0
                        avg_pct  = vid_pct * 0.60 + aud_avg * 0.40
                    else:
                        avg_pct = raw_pct

                    last_pct = max(last_pct, avg_pct)

                    # ── EMA speed smoothing (alpha=0.25) ──────────────────────
                    if speed_bps and speed_bps > 0:
                        last_speed_bps = (
                            speed_bps if last_speed_bps is None
                            else 0.25 * speed_bps + 0.75 * last_speed_bps
                        )

                    # ── ETA: use reported value or calculate from elapsed ──────
                    if eta_sec is not None:
                        last_eta_sec = eta_sec
                    elif last_pct > 1.0:
                        elapsed = max(0.001, now - progress_started)
                        last_eta_sec = (elapsed / last_pct) * (100.0 - last_pct)

                    msg = _build_progress_message(
                        last_pct,
                        speed_bps=last_speed_bps,
                        eta_sec=last_eta_sec,
                    )
                    progress_callback(last_pct, msg)
                    last_progress_update = now

                if any(k in clean_line for k in _keywords):
                    # Avoid flooding the log with CR progress spam
                    if not parsed or any(k in clean_line for k in
                                        ("INFO", "WARN", "ERROR", "Mux", "Merging", "Done")):
                        log(f"  {clean_line}")

        if buf.strip():
            leftover = buf.decode("utf-8", errors="replace").strip()
            if leftover and any(k in leftover for k in _keywords):
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
            raise RuntimeError(
                f"Download failed (exit code {rc}). "
                "Check the terminal log above for details. "
                "If the session expired, copy and paste a fresh stream URL or cURL command."
            )

# Backward-compatibility alias
DownloadEngine = OmniStreamEngine
