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
import webbrowser
import subprocess
from typing import Dict, Any

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

def is_extension_installed() -> bool:
    """
    Check if the Chrome extension is installed.
    Checks:
    1. Persistent settings.json state.
    2. Active Chrome/Edge/Brave User Data Preferences profiles.
    """
    settings = load_settings()
    if settings.get("extension_installed", False):
        return True

    # Check browser preference files for omnistream extension
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return False

    browser_data_roots = [
        os.path.join(local_appdata, "Google", "Chrome", "User Data"),
        os.path.join(local_appdata, "Microsoft", "Edge", "User Data"),
        os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "User Data"),
    ]

    for root in browser_data_roots:
        if not os.path.isdir(root):
            continue
        pref_pattern = os.path.join(root, "*", "Preferences")
        for pref_file in glob.glob(pref_pattern):
            try:
                with open(pref_file, "r", encoding="utf-8", errors="ignore") as f:
                    pref_data = json.load(f)
                ext_settings = pref_data.get("extensions", {}).get("settings", {})
                for ext_id, ext_info in ext_settings.items():
                    name = str(ext_info.get("manifest", {}).get("name", "")).lower()
                    path = str(ext_info.get("path", "")).lower()
                    if "omnistream" in name or "omnistream" in path:
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
    manifest_target = os.path.join(dest_dir, "manifest.json")

    # Locate source extension directory
    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, "extension"),
        os.path.join(os.path.dirname(base_dir), "extension"),
        os.path.join(base_dir, "..", "extension"),
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

def open_chrome_extensions():
    """Open Google Chrome directly to the extensions management page."""
    chrome_paths = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google\\Chrome\\Application\\chrome.exe")
    ]
    for p in chrome_paths:
        if os.path.isfile(p):
            try:
                subprocess.Popen([p, "chrome://extensions"])
                return True
            except Exception:
                pass
    webbrowser.open("chrome://extensions")
    return True

def open_extension_folder():
    """Open Windows Explorer to the unpacked extension folder."""
    dest = get_deployed_extension_dir()
    if os.path.isdir(dest):
        os.startfile(dest)
