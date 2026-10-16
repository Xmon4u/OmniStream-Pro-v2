"""
OmniStream Pro v2.0.0 - Windows Installer (.exe) Compiler
Compiles installer.py into OmniStream_Pro_Setup.exe using PyInstaller.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import subprocess
import shutil

ROOT_DIR    = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR = os.path.join(ROOT_DIR, "desktop")
EXT_DIR     = os.path.join(ROOT_DIR, "extension")
ICON_PATH   = os.path.join(DESKTOP_DIR, "app_icon.ico")
SETUP_NAME  = "OmniStream_Pro_Setup"

def build():
    print("=" * 65)
    print(f"Compiling {SETUP_NAME}.exe (OmniStream Pro v2.0.0 Windows Installer)...")
    print("=" * 65)

    add_data_args = [
        "--add-data", f"{DESKTOP_DIR};desktop",
        "--add-data", f"{EXT_DIR};extension",
        "--add-data", f"{ICON_PATH};.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", SETUP_NAME,
        "--icon", ICON_PATH,
        "--paths", DESKTOP_DIR,
        "--hidden-import", "extension_manager",
        "--hidden-import", "webbrowser",
        "--hidden-import", "glob",
        "--hidden-import", "json",
        "--hidden-import", "shutil",
        "--hidden-import", "subprocess",
        "--hidden-import", "winreg",
        "--hidden-import", "http.server",
        "--hidden-import", "socketserver",
        "--collect-all", "customtkinter",
        *add_data_args,
        "installer.py",
    ]

    res = subprocess.run(cmd, cwd=ROOT_DIR)
    if res.returncode != 0:
        print("[Error] Failed to build installer executable!")
        return False

    dist_exe = os.path.join(ROOT_DIR, "dist", f"{SETUP_NAME}.exe")
    if os.path.exists(dist_exe):
        release_out = os.path.join(ROOT_DIR, "release_output")
        os.makedirs(release_out, exist_ok=True)
        shutil.copy2(dist_exe, os.path.join(release_out, f"{SETUP_NAME}.exe"))
        size_mb = os.path.getsize(dist_exe) / (1024 * 1024)
        print("=" * 65)
        print(f"[SUCCESS] {SETUP_NAME}.exe created successfully ({size_mb:.2f} MB)!")
        print("=" * 65)
        return True

    return False

if __name__ == "__main__":
    build()
