"""
OmniStream Pro v2.0.0 - Dependency Manager
Automatically detects and installs required streaming and multiplexing binaries
(N_m3u8DL-RE and FFmpeg) for high-speed multi-audio stream capture.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import ssl
import shutil
import zipfile
import urllib.request
from typing import Tuple, Optional, Callable

# Use stable releases for reliability — with dynamic fallback to latest
N_M3U8_URL = "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.6.0-beta/N_m3u8DL-RE_v0.6.0-beta_win-x64_20260629.zip"
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

# SSL context that works on fresh Windows installations without updated certificate stores
def _make_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _get_n_m3u8_url() -> str:
    """Try to fetch the latest N_m3u8DL-RE win-x64 download URL from GitHub API.
    Falls back to hardcoded URL if network or API is unavailable."""
    try:
        import json as _json
        req = urllib.request.Request(
            "https://api.github.com/repos/nilaoda/N_m3u8DL-RE/releases/latest",
            headers={"User-Agent": "OmniStreamPro/2.0"}
        )
        ctx = _make_ssl_ctx()
        with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
            data = _json.load(r)
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                if "win" in name and "x64" in name and name.endswith(".zip"):
                    return asset["browser_download_url"]
    except Exception:
        pass
    return N_M3U8_URL

def get_base_dir() -> str:
    """Return the base directory of the running app or executable."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_bin_dir() -> str:
    """Return the dedicated local or AppData bin directory for portable binaries."""
    local_bin = os.path.join(get_base_dir(), "bin")
    if not os.path.exists(local_bin):
        appdata_bin = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "OmniStreamPro",
            "bin"
        )
        try:
            os.makedirs(local_bin, exist_ok=True)
            return local_bin
        except Exception:
            os.makedirs(appdata_bin, exist_ok=True)
            return appdata_bin
    return local_bin

def find_binary(binary_name: str) -> Optional[str]:
    """Search for a binary across bundled, local, standard, and PATH locations."""
    # 1. PyInstaller _MEIPASS bundle check
    if hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, binary_name)
        if os.path.exists(p):
            return p
        p_bin = os.path.join(sys._MEIPASS, "bin", binary_name)
        if os.path.exists(p_bin):
            return p_bin

    # 2. Local application bin directory and user AppData
    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, binary_name),
        os.path.join(base_dir, "bin", binary_name),
        os.path.join(os.path.dirname(base_dir), "bin", binary_name),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "OmniStreamPro", "bin", binary_name)
    ]

    # 3. Known standard system locations
    if binary_name.lower().startswith("n_m3u8"):
        candidates.append(r"C:\tools\N_m3u8DL-RE.exe")
    elif binary_name.lower().startswith("ffmpeg"):
        candidates.extend([
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\tools\ffmpeg.exe"
        ])

    for c in candidates:
        if c and os.path.exists(c) and os.path.isfile(c):
            return os.path.abspath(c)

    # 4. Check system PATH
    which_p = shutil.which(binary_name)
    if which_p:
        return os.path.abspath(which_p)

    return None

def download_file_with_progress(
    url: str,
    dest_path: str,
    progress_callback: Optional[Callable[[float, str], None]] = None
):
    """Download a remote binary archive with percentage tracking."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )

    ctx = _make_ssl_ctx()
    with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
        total_size = resp.getheader("Content-Length")
        total_size = int(total_size) if total_size else 0
        downloaded = 0
        chunk_size = 128 * 1024  # 128 KB chunks for faster downloads

        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    pct = (downloaded / total_size * 100) if total_size > 0 else 0
                    mb_cur = downloaded / (1024 * 1024)
                    mb_tot = total_size / (1024 * 1024) if total_size > 0 else 0
                    progress_callback(pct, f"{mb_cur:.1f} MB / {mb_tot:.1f} MB ({pct:.0f}%)")

def ensure_dependencies(
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[str, str]:
    """
    Ensure N_m3u8DL-RE and FFmpeg exist.
    If missing, automatically downloads and extracts them into local bin.
    Returns: (n_m3u8_path, ffmpeg_path)
    """
    def log(msg: str):
        if status_callback:
            status_callback(msg)
        else:
            print(msg, flush=True)

    bin_dir = get_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)

    n_m3u8_path = find_binary("N_m3u8DL-RE.exe")
    ffmpeg_path = find_binary("ffmpeg.exe")

    if not n_m3u8_path:
        log("[Setup] N_m3u8DL-RE not found. Downloading automatically...")
        zip_path = os.path.join(bin_dir, "nm3u8_dl.zip")
        try:
            dl_url = _get_n_m3u8_url()
            log(f"[Setup] Source: {dl_url.split('/')[-1]}")
            download_file_with_progress(
                dl_url, zip_path,
                lambda pct, txt: progress_callback(pct, f"Downloading N_m3u8DL-RE: {txt}") if progress_callback else None
            )
            log("[Setup] Extracting N_m3u8DL-RE...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Search for the exe anywhere in the zip (handles nested dirs)
                for file_info in zip_ref.infolist():
                    if file_info.filename.lower().endswith("n_m3u8dl-re.exe"):
                        file_info.filename = "N_m3u8DL-RE.exe"
                        zip_ref.extract(file_info, bin_dir)
                        break
            if os.path.exists(zip_path):
                os.remove(zip_path)
            n_m3u8_path = os.path.join(bin_dir, "N_m3u8DL-RE.exe")
            if not os.path.exists(n_m3u8_path):
                raise RuntimeError("N_m3u8DL-RE.exe not found in the downloaded archive.")
            log("[Setup] N_m3u8DL-RE installed successfully.")
        except Exception as e:
            log(f"[Setup Error] Failed to download N_m3u8DL-RE: {e}")
            raise RuntimeError(f"Could not auto-download N_m3u8DL-RE: {e}")

    if not ffmpeg_path:
        log("[Setup] FFmpeg not found. Downloading automatically...")
        zip_path = os.path.join(bin_dir, "ffmpeg_dl.zip")
        try:
            download_file_with_progress(
                FFMPEG_URL, zip_path,
                lambda pct, txt: progress_callback(pct, f"Downloading FFmpeg: {txt}") if progress_callback else None
            )
            log("[Setup] Extracting FFmpeg...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # FFmpeg zip has nested dirs like ffmpeg-master.../bin/ffmpeg.exe
                for file_info in zip_ref.infolist():
                    fname = file_info.filename.lower().replace("\\", "/")
                    if fname.endswith("/ffmpeg.exe") or fname == "ffmpeg.exe":
                        file_info.filename = "ffmpeg.exe"
                        zip_ref.extract(file_info, bin_dir)
                        break
            if os.path.exists(zip_path):
                os.remove(zip_path)
            ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
            if not os.path.exists(ffmpeg_path):
                raise RuntimeError("ffmpeg.exe not found in the downloaded archive.")
            log("[Setup] FFmpeg installed successfully.")
        except Exception as e:
            log(f"[Setup Error] Failed to download FFmpeg: {e}")
            raise RuntimeError(f"Could not auto-download FFmpeg: {e}")

    return n_m3u8_path, ffmpeg_path

if __name__ == "__main__":
    n, f = ensure_dependencies(print)
    print("Dependencies verified:", n, f)
