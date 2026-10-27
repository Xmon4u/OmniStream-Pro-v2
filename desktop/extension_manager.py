"""
OmniStream Pro - Extension Detection & Management Module
Handles Chrome extension deployment, installation checks, and persistent state.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import time
import glob
import json
import shutil
try:
    import webbrowser
except ImportError:
    webbrowser = None
import subprocess
from typing import Dict, Any, Optional

APP_DIR_NAME = "OmniStreamPro"

def get_creation_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows, 0 on other platforms."""
    return 0x08000000 if sys.platform == "win32" else 0


# ──────────────────────────────────────────────────────────────────────────────
# Core Path Helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_base_dir() -> str:
    """Return runtime base directory (handling PyInstaller bundle)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_app_data_dir() -> str:
    """Return persistent local AppData directory for OmniStream Pro."""
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    app_dir = os.path.join(base, APP_DIR_NAME)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

def get_deployed_extension_dir() -> str:
    """Return persistent directory where the Chrome extension is unpacked."""
    ext_dir = os.path.join(get_app_data_dir(), "extension")
    os.makedirs(ext_dir, exist_ok=True)
    return ext_dir

def get_app_browser_profile_dir() -> str:
    """Profile owned by OmniStream, used when the user's browser is already open."""
    return os.path.join(get_app_data_dir(), "ChromeProfile")

def get_settings_file() -> str:
    return os.path.join(get_app_data_dir(), "settings.json")

def load_settings() -> Dict[str, Any]:
    path = get_settings_file()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"extension_installed": False, "first_run_complete": False}

def save_settings(data: Dict[str, Any]):
    path = get_settings_file()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def mark_extension_installed():
    """Remember that the extension has talked to the desktop app."""
    settings = load_settings()
    settings["extension_installed"] = True
    save_settings(settings)

def note_extension_heartbeat():
    """Record a live ping from the browser extension."""
    path = os.path.join(get_app_data_dir(), "extension_heartbeat.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time()}, f)
    except Exception:
        pass
    mark_extension_installed()

def extension_heartbeat_time() -> float:
    """Unix time of the last extension ping, or 0 if it has never connected."""
    path = os.path.join(get_app_data_dir(), "extension_heartbeat.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return float(data.get("ts", 0))
    except Exception:
        return 0.0

def extension_is_live(max_age: float = 75.0) -> bool:
    """True only when the extension has reached the desktop bridge recently."""
    ts = extension_heartbeat_time()
    return ts > 0 and (time.time() - ts) <= max_age

def get_or_create_bridge_token() -> str:
    """Return persistent random authentication token for localhost bridge communication."""
    token_file = os.path.join(get_app_data_dir(), "bridge_token.txt")
    try:
        if os.path.isfile(token_file):
            with open(token_file, "r", encoding="utf-8") as f:
                tok = f.read().strip()
                if len(tok) >= 32:
                    return tok
    except Exception:
        pass
    import secrets
    tok = secrets.token_hex(24)
    try:
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(tok)
    except Exception:
        pass
    return tok

def write_extension_bridge_token() -> str:
    """Write bridge_token.json into deployed extension folder and local extension folders for pairing."""
    token = get_or_create_bridge_token()
    token_data = json.dumps({"token": token, "port": 28795}, indent=2)

    targets = [
        os.path.join(get_deployed_extension_dir(), "bridge_token.json")
    ]
    base_dir = get_base_dir()
    for cand in [
        os.path.join(base_dir, "extension", "bridge_token.json"),
        os.path.join(os.path.dirname(base_dir), "extension", "bridge_token.json"),
    ]:
        cand_dir = os.path.dirname(cand)
        if os.path.isdir(cand_dir) and os.path.isfile(os.path.join(cand_dir, "manifest.json")):
            targets.append(cand)

    for target in targets:
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(token_data)
        except Exception:
            pass
    return token

# ──────────────────────────────────────────────────────────────────────────────
# Browser Detection
# ──────────────────────────────────────────────────────────────────────────────

def get_browser_executable() -> Optional[str]:
    """Find installed Chrome, Edge, or Brave executable on Windows."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

    candidates = [
        # Google Chrome
        os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe"),
        # Microsoft Edge
        os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        # Brave Browser
        os.path.join(prog_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]

    for p in candidates:
        if os.path.isfile(p):
            return os.path.abspath(p)

    try:
        import winreg
        for exe_name in ("chrome.exe", "msedge.exe", "brave.exe"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}") as key:
                    value, _ = winreg.QueryValueEx(key, "")
                    if value and os.path.isfile(value):
                        return os.path.abspath(value)
            except OSError:
                continue
    except Exception:
        pass
    return None

def get_browser_user_data_roots() -> list:
    """Return all possible browser User Data directories."""
    local = os.environ.get("LOCALAPPDATA", "")
    return [
        os.path.join(local, "Google", "Chrome", "User Data"),
        os.path.join(local, "Microsoft", "Edge", "User Data"),
        os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
    ]

def is_browser_running(browser_exe: Optional[str] = None) -> bool:
    """Check whether the chosen browser process is already running."""
    image = os.path.basename(browser_exe).lower() if browser_exe else "chrome.exe"
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}"],
            capture_output=True, text=True, timeout=3, creationflags=get_creation_flags()
        )
        return image in result.stdout.lower()
    except Exception:
        return False

def is_chrome_running() -> bool:
    """Check if Chrome, Edge, or Brave is currently running."""
    for image in ("chrome.exe", "msedge.exe", "brave.exe"):
        if is_browser_running(image):
            return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Extension State Cache
# ──────────────────────────────────────────────────────────────────────────────

_last_ext_check_time = 0.0
_last_ext_check_result = False

def is_extension_installed() -> bool:
    """
    Check if the Chrome extension is installed.
    Cached with TTL to avoid redundant disk I/O on UI polling loops.
    """
    global _last_ext_check_time, _last_ext_check_result
    now = time.time()
    if (now - _last_ext_check_time) < 2.0:
        return _last_ext_check_result

    _last_ext_check_time = now
    # A saved flag is not proof. Chrome often ignores injected Preferences,
    # so only a live bridge ping or a real on-disk registration counts.
    if extension_is_live():
        _last_ext_check_result = True
        return True

    deployed_dir = get_deployed_extension_dir()

    for root in get_browser_user_data_roots() + [get_app_browser_profile_dir()]:
        if not os.path.isdir(root):
            continue
        for pref_file_name in ["Preferences", "Secure Preferences"]:
            pref_pattern = os.path.join(root, "*", pref_file_name)
            for pref_file in glob.glob(pref_pattern):
                try:
                    with open(pref_file, "r", encoding="utf-8", errors="ignore") as f:
                        pref_data = json.load(f)
                    ext_settings = pref_data.get("extensions", {}).get("settings", {})
                    for ext_id, ext_info in ext_settings.items():
                        manifest = ext_info.get("manifest", {})
                        if not isinstance(manifest, dict):
                            continue
                        # Ignore placeholder entries written into Preferences.
                        # Chrome only stores the full manifest after it actually loads the extension.
                        if "background" not in manifest and "action" not in manifest:
                            continue
                        name = str(manifest.get("name", "")).lower()
                        path = str(ext_info.get("path", "")).strip()
                        path_lo = path.lower()
                        if "omnistream" in name or "omnistream" in path_lo:
                            # If registered path does not exist on disk, auto-repair/restore it
                            if path and not os.path.exists(path) and os.path.exists(deployed_dir):
                                try:
                                    os.makedirs(os.path.dirname(path), exist_ok=True)
                                    shutil.copytree(deployed_dir, path, dirs_exist_ok=True)
                                except Exception:
                                    pass
                            mark_extension_installed()
                            _last_ext_check_result = True
                            return True
                except Exception:
                    continue

    _last_ext_check_result = False
    return False

def invalidate_extension_cache():
    """Force the next is_extension_installed() call to re-check disk."""
    global _last_ext_check_time, _last_ext_check_result
    _last_ext_check_time = 0.0
    _last_ext_check_result = False

# ──────────────────────────────────────────────────────────────────────────────
# Extension Deployment
# ──────────────────────────────────────────────────────────────────────────────

def deploy_extension_files() -> str:
    """
    Ensure the extension files are placed into the persistent AppData directory.
    Returns the path to the deployed extension directory.
    """
    dest_dir = get_deployed_extension_dir()

    # Locate source extension directory
    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, "extension"),
        os.path.join(os.path.dirname(base_dir), "extension"),
        os.path.join(base_dir, "..", "extension"),
        os.path.join(os.path.dirname(os.path.dirname(base_dir)), "omnistream_extension"),
        os.path.join(os.path.dirname(base_dir), "omnistream_extension"),
    ]

    src_dir = None
    for c in candidates:
        if os.path.isfile(os.path.join(c, "manifest.json")):
            src_dir = os.path.abspath(c)
            break

    if src_dir and src_dir != dest_dir:
        try:
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(dest_dir, item)
                if os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d, ignore_errors=True)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        except Exception:
            pass

    try:
        write_extension_bridge_token()
    except Exception:
        pass

    return dest_dir

# ──────────────────────────────────────────────────────────────────────────────
# Clipboard Utility
# ──────────────────────────────────────────────────────────────────────────────

def copy_path_to_clipboard(text: str = "") -> bool:
    """
    Copy text (or deployed extension path) to Windows clipboard instantly using Win32 API.
    Fully 64-bit safe with explicit ctypes argtypes and restypes to prevent pointer truncation.
    """
    if not text:
        text = get_deployed_extension_dir()
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                encoded = text.encode('utf-16le') + b'\x00\x00'
                h_mem = kernel32.GlobalAlloc(0x0042, len(encoded))  # GMEM_MOVEABLE | GMEM_ZEROINIT
                if h_mem:
                    p_mem = kernel32.GlobalLock(h_mem)
                    if p_mem:
                        ctypes.memmove(p_mem, encoded, len(encoded))
                        kernel32.GlobalUnlock(h_mem)
                        user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT = 13
            finally:
                user32.CloseClipboard()
            return True
    except Exception:
        pass

    # Safe fallback using subprocess without blocking GUI
    try:
        p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, creationflags=get_creation_flags())
        p.communicate(input=text.encode("utf-8"), timeout=1)
        return True
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Chrome Extension Injection via Preferences (Auto-Install)
# ──────────────────────────────────────────────────────────────────────────────

def _inject_extension_into_preferences(ext_dir: str) -> bool:
    """
    Attempt to directly inject extension entry into Chrome's Preferences file
    so it loads automatically without user interaction.
    This works when Chrome is CLOSED. Returns True if successful.
    """
    import hashlib

    success = False
    # Generate a stable fake extension ID from the path (Chrome expects specific format)
    ext_id_seed = hashlib.md5(ext_dir.encode()).hexdigest()[:32]
    # Chrome extension IDs are lowercase a-p (base-16 mapped to a-p)
    ext_id = "".join(chr(ord('a') + int(c, 16)) for c in ext_id_seed)

    for user_data_root in get_browser_user_data_roots():
        if not os.path.isdir(user_data_root):
            continue

        # Try all profiles: Default, Profile 1, Profile 2, ...
        profile_dirs = ["Default"] + [d for d in os.listdir(user_data_root)
                                       if d.startswith("Profile ") and
                                       os.path.isdir(os.path.join(user_data_root, d))]

        for profile in profile_dirs:
            pref_file = os.path.join(user_data_root, profile, "Preferences")
            if not os.path.exists(pref_file):
                continue
            try:
                with open(pref_file, "r", encoding="utf-8", errors="ignore") as f:
                    prefs = json.load(f)
            except Exception:
                continue

            try:
                if "extensions" not in prefs:
                    prefs["extensions"] = {}
                if "settings" not in prefs["extensions"]:
                    prefs["extensions"]["settings"] = {}

                settings = prefs["extensions"]["settings"]

                # Check if already injected (by path)
                already_there = any(
                    "omnistream" in str(v.get("manifest", {}).get("name", "")).lower() or
                    "omnistream" in str(v.get("path", "")).lower()
                    for v in settings.values()
                )
                if already_there:
                    success = True
                    continue

                # Inject extension entry
                settings[ext_id] = {
                    "path": ext_dir,
                    "state": 1,
                    "location": 4,  # LOAD (unpacked)
                    "manifest": {
                        "name": "OmniStream Pro - Stream Sniffer & Downloader",
                        "version": "2.0.0",
                        "manifest_version": 3
                    },
                    "active_permissions": {
                        "api": ["webRequest", "storage", "downloads", "activeTab", "scripting",
                                "clipboardWrite", "notifications"],
                        "explicit_host": ["<all_urls>"]
                    },
                    "granted_permissions": {
                        "api": ["webRequest", "storage", "downloads", "activeTab", "scripting",
                                "clipboardWrite", "notifications"],
                        "explicit_host": ["<all_urls>"]
                    },
                    "initial_keybindings_set": True,
                    "was_installed_by_default": False,
                    "was_installed_by_oem": False,
                    "install_time": str(int(time.time() * 1000000)),
                    "last_update_time": str(int(time.time() * 1000000)),
                    "from_bookmark": False,
                    "from_webstore": False,
                }

                with open(pref_file, "w", encoding="utf-8") as f:
                    json.dump(prefs, f, separators=(',', ':'))
                success = True
            except Exception:
                continue

    return success


def _write_external_extensions_json(ext_dir: str, ext_id: str) -> bool:
    """
    Write an ExternalExtensions JSON file into Chrome's User Data directories.
    Chrome periodically checks this and auto-installs listed extensions.
    """
    success = False
    ext_json_content = json.dumps({ext_id: {"external_crx": ext_dir, "external_version": "2.0.0"}})
    for user_data_root in get_browser_user_data_roots():
        if not os.path.isdir(user_data_root):
            continue
        ext_json_path = os.path.join(user_data_root, "External Extensions", f"{ext_id}.json")
        try:
            os.makedirs(os.path.dirname(ext_json_path), exist_ok=True)
            # Write a simple external_crx reference
            content = {
                "external_crx": ext_dir,
                "external_version": "2.0.0"
            }
            with open(ext_json_path, "w", encoding="utf-8") as f:
                json.dump(content, f)
            success = True
        except Exception:
            continue
    return success


def _register_external_extension_via_registry(ext_id: str, ext_dir: str) -> bool:
    """
    Register the extension via Windows Registry under Chrome's External Extensions key.
    Chrome reads this on startup and loads the extension automatically.
    This is the OFFICIAL Chrome-supported way to auto-install unpacked extensions.
    """
    try:
        import winreg
        reg_path = rf"Software\Google\Chrome\Extensions\{ext_id}"
        # Write to HKCU (user-level, no admin required)
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, reg_path,
                                  0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "path", 0, winreg.REG_SZ, ext_dir)
        winreg.SetValueEx(key, "version", 0, winreg.REG_SZ, "2.0.0")
        winreg.CloseKey(key)

        # Also try Edge's registry key
        try:
            edge_reg = rf"Software\Microsoft\Edge\Extensions\{ext_id}"
            edge_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, edge_reg,
                                           0, winreg.KEY_WRITE)
            winreg.SetValueEx(edge_key, "path", 0, winreg.REG_SZ, ext_dir)
            winreg.SetValueEx(edge_key, "version", 0, winreg.REG_SZ, "2.0.0")
            winreg.CloseKey(edge_key)
        except Exception:
            pass

        return True
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Browser Launch Strategies
# ──────────────────────────────────────────────────────────────────────────────

def _extensions_page_url(browser_exe: str) -> str:
    name = os.path.basename(browser_exe).lower()
    if "msedge" in name:
        return "edge://extensions"
    if "brave" in name:
        return "brave://extensions"
    return "chrome://extensions"

def _chrome_safe_path(path: str) -> str:
    """Chrome re-parses --load-extension on spaces, so prefer an 8.3 path."""
    path = os.path.abspath(path)
    if " " not in path:
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
        if n:
            return buf.value
    except Exception:
        pass
    return path

def _prepare_app_browser_profile(profile_dir: str) -> None:
    """Turn on developer mode in OmniStream's own browser profile before launch."""
    default_dir = os.path.join(profile_dir, "Default")
    os.makedirs(default_dir, exist_ok=True)
    first_run = os.path.join(profile_dir, "First Run")
    if not os.path.exists(first_run):
        try:
            open(first_run, "w", encoding="utf-8").close()
        except Exception:
            pass

    pref_path = os.path.join(default_dir, "Preferences")
    prefs: Dict[str, Any] = {}
    if os.path.isfile(pref_path):
        try:
            with open(pref_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                prefs = loaded
        except Exception:
            prefs = {}
    prefs.setdefault("extensions", {}).setdefault("ui", {})["developer_mode"] = True
    try:
        with open(pref_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f)
    except Exception:
        pass

    # This profile belongs to the app. Drop the old signature so developer mode sticks.
    secure = os.path.join(default_dir, "Secure Preferences")
    try:
        if os.path.isfile(secure):
            os.remove(secure)
    except Exception:
        pass

def _profile_processes(image_name: str, profile_dir: str) -> list:
    """Return PIDs of browser processes started with OmniStream's profile."""
    marker = os.path.normcase(os.path.abspath(profile_dir))
    try:
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='" + image_name + "'\" | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=8, creationflags=get_creation_flags()
        )
        raw = (result.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        rows = data if isinstance(data, list) else [data]
        pids = []
        for row in rows:
            cmd = os.path.normcase(str(row.get("CommandLine") or ""))
            pid = int(row.get("ProcessId") or 0)
            if pid > 0 and marker in cmd:
                pids.append(pid)
        return pids
    except Exception:
        return []

def _close_profile_processes(image_name: str, profile_dir: str) -> None:
    for pid in _profile_processes(image_name, profile_dir):
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=3, creationflags=get_creation_flags()
            )
        except Exception:
            pass

_CHROME_HOST_JS = r"""
const { spawn } = require('child_process');
const fs = require('fs');

const chrome = process.argv[2];
const extDir = process.argv[3];
const profile = process.argv[4];
const page = process.argv[5];
const resultPath = process.argv[6];

const args = [
  '--remote-debugging-pipe',
  '--enable-unsafe-extension-debugging',
  '--restore-last-session',
  '--no-first-run',
  '--no-default-browser-check',
  '--profile-directory=' + profile
];
if (process.argv[7]) args.push('--user-data-dir=' + process.argv[7]);
if (page) args.push(page);
const child = spawn(chrome, args, { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] });

let finished = false;
function writeResult(obj) {
  if (finished) return;
  finished = true;
  try { fs.writeFileSync(resultPath, JSON.stringify(obj)); } catch (e) {}
}

let buf = Buffer.alloc(0);
child.stdio[4].on('data', (chunk) => {
  buf = Buffer.concat([buf, chunk]);
  let idx;
  while ((idx = buf.indexOf(0)) !== -1) {
    const raw = buf.slice(0, idx).toString('utf8');
    buf = buf.slice(idx + 1);
    try {
      const msg = JSON.parse(raw);
      if (msg.id === 1) writeResult(msg);
    } catch (e) {}
  }
});
child.on('exit', (code) => {
  writeResult({ error: 'browser exited', code: code });
  process.exit(0);
});
child.stdio[3].on('error', () => {});
child.stdio[4].on('error', () => {});
child.stdio[3].write(JSON.stringify({
  id: 1,
  method: 'Extensions.loadUnpacked',
  params: { path: extDir }
}) + '\0');

process.stdin.resume();
process.stdin.on('end', () => {
  process.exit(0);
});
"""

_extension_host_proc = None
_last_launch_error = ""
_last_profile_label = ""

def get_last_launch_error() -> str:
    return _last_launch_error

def get_last_profile_label() -> str:
    return _last_profile_label

def _node_executable() -> Optional[str]:
    import shutil
    return shutil.which("node") or shutil.which("node.exe")

def _browser_user_data_dir(browser_exe: str) -> str:
    local = os.environ.get("LOCALAPPDATA", "")
    name = os.path.basename(browser_exe).lower()
    if "msedge" in name:
        return os.path.join(local, "Microsoft", "Edge", "User Data")
    if "brave" in name:
        return os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data")
    return os.path.join(local, "Google", "Chrome", "User Data")

def _real_browser_profile(browser_exe: str):
    """Return the account the user currently has open, plus any other open accounts."""
    user_data = _browser_user_data_dir(browser_exe)
    last_used = "Default"
    last_active = []
    names = {}
    state_path = os.path.join(user_data, "Local State")
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        profile = state.get("profile") or {}
        last_used = profile.get("last_used") or "Default"
        last_active = list(profile.get("last_active_profiles") or [])
        for key, info in (profile.get("info_cache") or {}).items():
            if isinstance(info, dict):
                names[key] = info.get("name") or key
    except Exception:
        pass
    if not os.path.isdir(os.path.join(user_data, last_used)):
        last_used = "Default"
    others = []
    for name in last_active:
        if name != last_used and os.path.isdir(os.path.join(user_data, name)):
            others.append(name)
    return user_data, last_used, names.get(last_used) or last_used, others

def _profile_has_our_extension(user_data: str, profile_dir: str) -> bool:
    pref_path = os.path.join(user_data, profile_dir, "Preferences")
    marker = os.path.normcase(os.path.abspath(get_deployed_extension_dir()))
    try:
        with open(pref_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False
    settings = (data.get("extensions") or {}).get("settings") or {}
    for info in settings.values():
        if not isinstance(info, dict):
            continue
        raw = str(info.get("path") or "")
        path = os.path.normcase(os.path.abspath(raw)) if raw else ""
        if marker and path.startswith(marker):
            disabled = info.get("disable_reasons") or []
            return info.get("state", 1) == 1 and not disabled
    return False

def _stop_extension_host() -> None:
    global _extension_host_proc
    proc = _extension_host_proc
    _extension_host_proc = None
    if proc is None or proc.poll() is not None:
        return
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:
        pass

_LOAD_UNPACKED_PS = r"""
param([string]$Folder)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Find-Window([string[]]$Needles) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $wins = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($win in $wins) {
        $name = ''
        try { $name = $win.Current.Name } catch { continue }
        foreach ($needle in $Needles) {
            if ($name -and $name.ToLower().Contains($needle.ToLower())) { return $win }
        }
    }
    return $null
}

function Find-Named($root, [string[]]$Needles) {
    if (-not $root) { return $null }
    $all = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($el in $all) {
        $name = ''
        try { $name = $el.Current.Name } catch { continue }
        if (-not $name) { continue }
        foreach ($needle in $Needles) {
            if ($name.ToLower().Contains($needle.ToLower())) { return $el }
        }
    }
    return $null
}

function Invoke-El($el) {
    $invoke = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $invoke.Invoke()
}

$ext = $null
$deadline = (Get-Date).AddSeconds(12)
while ((Get-Date) -lt $deadline -and -not $ext) {
    $ext = Find-Window @('Extensions')
    if (-not $ext) { Start-Sleep -Milliseconds 400 }
}
if (-not $ext) { Write-Output 'FAIL no extensions page'; exit 0 }

$load = Find-Named $ext @('Load unpacked')
if (-not $load) {
    $dev = Find-Named $ext @('Developer mode')
    if ($dev) {
        try {
            $toggle = $dev.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
            if ($toggle.Current.ToggleState -ne 'On') { $toggle.Toggle() }
        } catch {
            try { Invoke-El $dev } catch {}
        }
        Start-Sleep -Milliseconds 600
        $load = Find-Named $ext @('Load unpacked')
    }
}
if (-not $load) { Write-Output 'FAIL load button'; exit 0 }
Invoke-El $load
Write-Output 'CLICKED'
"""

def _window_text(hwnd) -> str:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    buf = ctypes.create_unicode_buffer(500)
    user32.GetWindowTextW(hwnd, buf, 500)
    return buf.value

def _window_class(hwnd) -> str:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    buf = ctypes.create_unicode_buffer(160)
    user32.GetClassNameW(hwnd, buf, 160)
    return buf.value

def _submit_extension_folder(ext_dir: str) -> bool:
    """Put the extension folder into Chrome's picker and press Select Folder."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_ulong]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulong]

    def find_dialog():
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_top(hwnd, _lparam):
            try:
                if user32.IsWindowVisible(hwnd):
                    title = _window_text(hwnd).lower()
                    if "extension directory" in title or "select" in title:
                        found.append(hwnd)
            except Exception:
                pass
            return True

        cb = enum_top
        user32.EnumWindows(cb, 0)
        return found[0] if found else None

    def click_hwnd(hwnd):
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        x = (rect.left + rect.right) // 2
        y = (rect.top + rect.bottom) // 2
        user32.SetCursorPos(x, y)
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def chord(vk):
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        user32.keybd_event(0x11, 0, 2, 0)

    deadline = time.time() + 12
    dialog = None
    while time.time() < deadline and not dialog:
        dialog = find_dialog()
        if not dialog:
            time.sleep(0.25)
    if not dialog:
        return False

    edits = []
    select_btn = None
    cancel_btn = None

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_child(hwnd, _lparam):
        nonlocal select_btn, cancel_btn
        cls = _window_class(hwnd)
        if cls == "Edit":
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            edits.append((rect.top, hwnd))
        elif cls == "Button":
            label = _window_text(hwnd).replace("&", "").strip().lower()
            if "select folder" in label or "select" in label:
                select_btn = hwnd
            elif label in ("cancel",):
                cancel_btn = hwnd
        return True

    user32.EnumChildWindows(dialog, enum_child, 0)
    if not edits:
        return False
    if select_btn is None and cancel_btn is not None:
        cancel_rect = wintypes.RECT()
        user32.GetWindowRect(cancel_btn, ctypes.byref(cancel_rect))
        buttons = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_buttons(hwnd, _lparam):
            if _window_class(hwnd) == "Button" and hwnd != cancel_btn:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                if abs(rect.top - cancel_rect.top) < 20 and rect.right <= cancel_rect.left + 8:
                    buttons.append((rect.right, hwnd))
            return True

        user32.EnumChildWindows(dialog, enum_buttons, 0)
        if buttons:
            buttons.sort()
            select_btn = buttons[-1][1]
    if select_btn is None:
        return False

    edits.sort()
    folder_edit = edits[-1][1]
    copy_path_to_clipboard(ext_dir)
    user32.SetForegroundWindow(dialog)
    time.sleep(0.15)
    click_hwnd(folder_edit)
    time.sleep(0.1)
    chord(0x41)
    time.sleep(0.05)
    chord(0x56)
    time.sleep(0.15)
    user32.SendMessageW(folder_edit, 0x000C, 0, ctypes.cast(ctypes.c_wchar_p(ext_dir), ctypes.c_void_p))
    time.sleep(0.15)
    click_hwnd(select_btn)
    deadline = time.time() + 6
    while time.time() < deadline:
        if not user32.IsWindow(dialog):
            return True
        time.sleep(0.2)
    return not user32.IsWindow(dialog)

def _install_into_open_profile(browser_exe: str, profile_dir: str, ext_dir: str) -> bool:
    """Open the extensions page in one profile and load the folder there.

    Other Chrome windows stay open. This does not close or restart the browser.
    """
    app_data = get_app_data_dir()
    subprocess.Popen(
        [browser_exe, f"--profile-directory={profile_dir}", "chrome://extensions"],
        cwd=app_data,
        creationflags=get_creation_flags(),
    )
    script_path = os.path.join(app_data, "load_unpacked.ps1")
    try:
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(_LOAD_UNPACKED_PS)
    except Exception:
        return False
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", script_path, "-Folder", ext_dir,
            ],
            cwd=app_data,
            capture_output=True, text=True, timeout=30, creationflags=get_creation_flags(),
        )
    except Exception:
        return False
    output = (result.stdout or "") + (result.stderr or "")
    if "CLICKED" not in output:
        return False
    return _submit_extension_folder(ext_dir)

def _launch_branded_chrome(browser_exe: str, ext_dir: str, restart_running: bool) -> str:
    """
    Install the unpacked extension into the Chrome profile the user is working in.

    Open profiles are left running. When Chrome is already open, the extension
    page is added only in that profile.
    """
    global _extension_host_proc, _last_launch_error, _last_profile_label
    image = os.path.basename(browser_exe)
    _close_profile_processes(image, get_app_browser_profile_dir())

    user_data, profile_dir, profile_label, _other_profiles = _real_browser_profile(browser_exe)
    _last_profile_label = profile_label
    if not os.path.isdir(user_data):
        _last_launch_error = "The Chrome profile folder was not found."
        return ""

    if _profile_has_our_extension(user_data, profile_dir):
        _last_launch_error = ""
        return "profile-ready"

    if is_browser_running(browser_exe) and not restart_running:
        _last_launch_error = (
            "Chrome is open. Click Extension to add it to the window you are using."
        )
        return ""

    if is_browser_running(browser_exe):
        if _install_into_open_profile(browser_exe, profile_dir, ext_dir):
            deadline = time.time() + 8
            while time.time() < deadline:
                if _profile_has_our_extension(user_data, profile_dir):
                    _last_launch_error = ""
                    return "profile"
                time.sleep(0.4)
        _last_launch_error = (
            "Chrome's extension page is open. Your other windows were left as they were."
        )
        return ""

    node = _node_executable()
    if not node:
        _last_launch_error = "Node.js was not found, so Chrome could not install the extension."
        return ""

    host_path = os.path.join(get_app_data_dir(), "chrome_extension_host.js")
    result_path = os.path.join(get_app_data_dir(), "extension_load_result.json")
    try:
        if os.path.isfile(result_path):
            os.remove(result_path)
    except Exception:
        pass
    try:
        with open(host_path, "w", encoding="utf-8") as handle:
            handle.write(_CHROME_HOST_JS)
    except Exception as exc:
        _last_launch_error = str(exc)
        return ""

    try:
        app_data = get_app_data_dir()
        _extension_host_proc = subprocess.Popen(
            [node, host_path, browser_exe, ext_dir, profile_dir, "", result_path, user_data],
            cwd=app_data,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=get_creation_flags(),
        )
    except Exception as exc:
        _last_launch_error = str(exc)
        _extension_host_proc = None
        return ""

    deadline = time.time() + 20
    loaded = False
    try:
        while time.time() < deadline:
            if os.path.isfile(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle)
                except Exception:
                    time.sleep(0.2)
                    continue
                result = payload.get("result") if isinstance(payload, dict) else None
                if isinstance(result, dict) and result.get("id"):
                    loaded = True
                    break
                err = payload.get("error") if isinstance(payload, dict) else payload
                _last_launch_error = str(err or "Chrome did not accept the extension.")
                return ""
            if _extension_host_proc.poll() is not None:
                _last_launch_error = "The Chrome extension host exited before the extension loaded."
                return ""
            time.sleep(0.25)
    finally:
        if _extension_host_proc:
            try:
                _extension_host_proc.terminate()
                _extension_host_proc.wait(timeout=0.5)
            except Exception:
                try:
                    _extension_host_proc.kill()
                except Exception:
                    pass

    if not loaded:
        _last_launch_error = "Timed out waiting for Chrome to load the extension."
        return ""

    _last_launch_error = ""
    return "profile"

def _browser_launch_args(browser_exe: str, ext_dir: str, user_data_dir: Optional[str] = None) -> list:
    args = [
        browser_exe,
        "--disable-features=DisableLoadExtensionCommandLineSwitch",
        f"--load-extension={_chrome_safe_path(ext_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if user_data_dir:
        args.append(f"--user-data-dir={user_data_dir}")
    args.append(_extensions_page_url(browser_exe))
    return args

def launch_browser_with_extension(restart_running: bool = True) -> str:
    """
    Load the extension into the browser account the user already uses.

    Returns 'profile', 'profile-ready', 'default', 'companion',
    'companion-existing', or '' if launch failed.
    Branded Chrome installs into the real profile. Edge, Brave, and Chromium
    still accept --load-extension.
    """
    global _last_launch_error
    ext_dir = deploy_extension_files()
    if not os.path.isfile(os.path.join(ext_dir, "manifest.json")):
        _last_launch_error = "Extension manifest.json was not found."
        return ""

    browser_exe = get_browser_executable()
    if not browser_exe or not os.path.isfile(browser_exe):
        _last_launch_error = "No supported browser was found."
        return ""

    if os.path.basename(browser_exe).lower() == "chrome.exe":
        return _launch_branded_chrome(browser_exe, ext_dir, restart_running)

    image = os.path.basename(browser_exe)
    app_data = get_app_data_dir()
    try:
        if not is_browser_running(browser_exe):
            subprocess.Popen(_browser_launch_args(browser_exe, ext_dir), cwd=app_data)
            return "default"

        profile = get_app_browser_profile_dir()
        os.makedirs(profile, exist_ok=True)
        if _profile_processes(image, profile):
            subprocess.Popen([
                browser_exe,
                f"--user-data-dir={profile}",
                _extensions_page_url(browser_exe),
            ], cwd=app_data)
            return "companion-existing"

        _prepare_app_browser_profile(profile)
        subprocess.Popen(_browser_launch_args(browser_exe, ext_dir, profile), cwd=app_data)
        return "companion"
    except Exception as exc:
        _last_launch_error = str(exc)
        return ""



def open_chrome_extensions() -> bool:
    """Open Google Chrome directly to the extensions management page and copy path."""
    copy_path_to_clipboard()
    browser_exe = get_browser_executable()
    app_data = get_app_data_dir()
    if browser_exe and os.path.isfile(browser_exe):
        try:
            subprocess.Popen([browser_exe, "chrome://extensions"], cwd=app_data)
            return True
        except Exception:
            pass
    if webbrowser:
        try:
            webbrowser.open("chrome://extensions")
            return True
        except Exception:
            pass
    try:
        subprocess.Popen(["cmd.exe", "/c", "start", "chrome://extensions"], cwd=app_data)
        return True
    except Exception:
        pass
    return True


def open_extension_folder():
    """Open Windows Explorer and highlight/show the unpacked extension folder."""
    dest = deploy_extension_files()
    if os.path.isdir(dest):
        try:
            # Highlight folder in explorer
            subprocess.Popen(["explorer.exe", dest], cwd=get_app_data_dir())
        except Exception:
            os.startfile(dest)
