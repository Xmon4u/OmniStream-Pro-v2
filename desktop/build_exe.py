"""
OmniStream Pro v2.0.0 - PyInstaller Standalone Windows Executable Builder
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import subprocess
import shutil

DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH   = os.path.join(DESKTOP_DIR, "app_icon.ico")
EXE_NAME    = "OmniStream_Pro"

def build():
    print("=" * 65)
    print(f"Building {EXE_NAME}.exe (OmniStream Pro v2.1.0 Standalone Executable)...")
    print("=" * 65)

    add_data_args = [
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'core_engine.py')};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'setup_dependencies.py')};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'bridge_server.py')};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'extension_manager.py')};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'ui_icons.py')};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'window_chrome.py')};.",
        "--add-data", f"{ICON_PATH};.",
        "--add-data", f"{os.path.join(DESKTOP_DIR, 'app_icon.png')};.",
    ]

    ext_dir = os.path.join(os.path.dirname(DESKTOP_DIR), "extension")
    if os.path.exists(ext_dir):
        add_data_args.extend(["--add-data", f"{ext_dir};extension"])

    bin_dir = os.path.join(DESKTOP_DIR, "bin")
    if os.path.exists(bin_dir):
        add_data_args.extend(["--add-data", f"{bin_dir};bin"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", EXE_NAME,
        "--icon", ICON_PATH,
        "--hidden-import", "ui_icons",
        "--hidden-import", "window_chrome",
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
        "main_gui.py",
    ]

    result = subprocess.run(cmd, cwd=DESKTOP_DIR)
    if result.returncode != 0:
        print("[Error] PyInstaller build failed!")
        return False

    dist_exe = os.path.join(DESKTOP_DIR, "dist", EXE_NAME + ".exe")
    if os.path.exists(dist_exe):
        size_mb = os.path.getsize(dist_exe) / (1024 * 1024)
        print("=" * 65)
        print(f"[SUCCESS] {EXE_NAME}.exe compiled successfully!")
        print(f"  Distribution: {dist_exe}")
        print(f"  File Size   : {size_mb:.2f} MB")
        print("=" * 65)
        return True

    print("[Error] Executable not found after build.")
    return False

if __name__ == "__main__":
    build()
