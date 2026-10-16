"""
OmniStream Pro - Extension Detection & Management Module
Handles Chrome extension deployment, installation checks, and persistent state.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
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
    """Mark the extension as installed so the user is never asked again."""
    settings = load_settings()
    settings["extension_installed"] = True
    save_settings(settings)

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
    return None

def is_extension_installed() -> bool:
    """
    Check if the Chrome extension is installed.
    Checks:
    1. Persistent settings.json state.
    2. Active Chrome/Edge/Brave User Data Preferences AND Secure Preferences profiles.
    3. Auto-repairs extension folder if Chrome expected it at an older path.
    """
    settings = load_settings()
    if settings.get("extension_installed", False):
        return True

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return False

    browser_data_roots = [
        os.path.join(local_appdata, "Google", "Chrome", "User Data"),
        os.path.join(local_appdata, "Microsoft", "Edge", "User Data"),
        os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data"),
    ]

    deployed_dir = deploy_extension_files()

    for root in browser_data_roots:
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
                        name = str(ext_info.get("manifest", {}).get("name", "")).lower()
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
                            return True
                except Exception:
                    continue

    return False

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

    return dest_dir

def copy_path_to_clipboard(text: str = "") -> bool:
    """Copy text (or deployed extension path) to Windows clipboard."""
    if not text:
        text = get_deployed_extension_dir()
    try:
        # Use PowerShell to set clipboard reliably without external dependencies
        cmd = f"Set-Clipboard -Value '{text}'"
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], creationflags=0x08000000, timeout=4)
        return True
    except Exception:
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return True
        except Exception:
            return False

def launch_browser_with_extension() -> bool:
    """
    Launch Chrome/Edge directly with --load-extension flag.
    This enables 1-click automatic extension loading without manual developer mode clicks!
    """
    ext_dir = deploy_extension_files()
    browser_exe = get_browser_executable()
    if browser_exe and os.path.isfile(browser_exe):
        try:
            subprocess.Popen([browser_exe, f"--load-extension={ext_dir}", "chrome://extensions"])
            mark_extension_installed()
            return True
        except Exception:
            pass
    return False

def open_chrome_extensions() -> bool:
    """Open Google Chrome directly to the extensions management page and copy path."""
    copy_path_to_clipboard()
    browser_exe = get_browser_executable()
    if browser_exe and os.path.isfile(browser_exe):
        try:
            subprocess.Popen([browser_exe, "chrome://extensions"])
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
        subprocess.Popen(["cmd.exe", "/c", "start", "chrome://extensions"])
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
            subprocess.Popen(["explorer.exe", dest])
        except Exception:
            os.startfile(dest)
