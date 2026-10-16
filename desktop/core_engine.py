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


def _parse_progress_line(line: str) -> Optional[Dict[str, Any]]:
    """Extract percent / speed / ETA from N_m3u8DL-RE or similar console output."""
    pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
    if not pct_match:
        return None
    pct = max(0.0, min(100.0, float(pct_match.group(1))))

    speed = None
    speed_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(K|M|G)?B(?:ps|/s|·s)?",
        line,
        re.IGNORECASE,
    )
    if speed_match:
        val = float(speed_match.group(1))
        unit = (speed_match.group(2) or "").upper()
        mult = {"K": 1 / 1024, "M": 1.0, "G": 1024}.get(unit, 1 / (1024 * 1024))
        speed = val * mult  # MB/s

    eta_sec = None
    eta_match = re.search(r"(?:ETA|Left|Remain(?:ing)?)\s*[:=]?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", line, re.I)
    if eta_match:
        parts = [int(x) for x in eta_match.groups() if x is not None]
        if len(parts) == 3:
            eta_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            eta_sec = parts[0] * 60 + parts[1]
    else:
        # N_m3u8DL-RE often prints bare mm:ss / hh:mm:ss near the end of the line
        time_match = re.search(r"(?:^|[\s|])(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s|$)", line)
        if time_match and pct < 100:
            parts = [int(x) for x in time_match.groups() if x is not None]
            if len(parts) == 3:
                eta_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                eta_sec = parts[0] * 60 + parts[1]

    return {"pct": pct, "speed": speed, "eta_sec": eta_sec, "raw": line}


def _build_progress_message(pct: float, speed: Optional[float], eta_sec: Optional[float], fallback: str = "") -> str:
    left = max(0.0, 100.0 - pct)
    parts = [f"{pct:.0f}% done", f"{left:.0f}% left"]
    if eta_sec is not None:
        parts.append(f"~{_format_eta(eta_sec)} left")
    if speed is not None and speed > 0:
        parts.append(f"{speed:.1f} MB/s")
    elif fallback:
        snippet = fallback.strip()
        if len(snippet) > 48:
            snippet = snippet[:45] + "…"
        if snippet and "%" not in snippet:
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
        _keywords = (
            "Vid ", "Aud ", "INFO", "WARN", "ERROR", "Exception",
            "Mux", "Merging", "Done", "Fail", "success", "stream",
        )

        if progress_callback:
            progress_callback(0.0, "Starting stream download…  ·  0% done  ·  100% left")

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

                parsed = _parse_progress_line(line)
                now = time.time()
                if parsed and progress_callback and (now - last_progress_update > 0.15):
                    pct = parsed["pct"]
                    last_pct = max(last_pct, pct)
                    eta_sec = parsed.get("eta_sec")
                    speed = parsed.get("speed")
                    if eta_sec is None and last_pct > 1.0:
                        elapsed = max(0.001, now - progress_started)
                        eta_sec = (elapsed / last_pct) * (100.0 - last_pct)
                    msg = _build_progress_message(last_pct, speed, eta_sec, fallback=line)
                    progress_callback(last_pct, msg)
                    last_progress_update = now

                if any(k in line for k in _keywords):
                    # Avoid flooding the log with CR progress spam
                    if not parsed or any(k in line for k in ("INFO", "WARN", "ERROR", "Mux", "Merging", "Done")):
                        log(f"  {line}")

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
