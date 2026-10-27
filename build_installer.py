"""
OmniStream Pro v2.6.0 - Windows Installer (.exe) Compiler
Compiles installer.py into OmniStream_Pro_Setup.exe using PyInstaller.

IMPORTANT: Never bundle desktop/dist or desktop/build. Nested PyInstaller
archives corrupt / confuse the outer PKG cookie and produce:
  "Could not load PyInstaller's embedded PKG archive"
"""

import os
import sys
import shutil
import subprocess

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR = os.path.join(ROOT_DIR, "desktop")
EXT_DIR = os.path.join(ROOT_DIR, "extension")
RELEASE_DIR = os.path.join(ROOT_DIR, "release_output")
ICON_PATH = os.path.join(DESKTOP_DIR, "app_icon.ico")
SETUP_NAME = "OmniStream_Pro_Setup"
STAGE_DIR = os.path.join(ROOT_DIR, "_installer_stage")

# Files the installer copies into AppData (source modules + icons + uninstaller).
DESKTOP_FILES = [
    "main_gui.py",
    "core_engine.py",
    "bridge_server.py",
    "netflix_resolver.py",
    "setup_dependencies.py",
    "extension_manager.py",
    "ui_icons.py",
    "window_chrome.py",
    "app_icon.ico",
    "app_icon.png",
    "uninstall.exe",
]


def _clean_stage():
    if os.path.isdir(STAGE_DIR):
        shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(STAGE_DIR, exist_ok=True)


def _ensure_uninstaller():
    uninst_exe = os.path.join(DESKTOP_DIR, "uninstall.exe")
    if not os.path.isfile(uninst_exe):
        build_script = os.path.join(DESKTOP_DIR, "build_uninstaller.py")
        if os.path.isfile(build_script):
            subprocess.run([sys.executable, build_script], cwd=DESKTOP_DIR, check=True)


def _stage_payload():
    """Build a clean payload tree with deployed C++ Native Application."""
    _clean_stage()
    _ensure_uninstaller()

    stage_cpp = os.path.join(STAGE_DIR, "cpp_app")
    os.makedirs(stage_cpp, exist_ok=True)

    # 1. Copy deployed C++ application binaries & Qt runtime
    cpp_rel = os.path.join(ROOT_DIR, "C++", "vs_project", "Release")
    if not os.path.isdir(cpp_rel):
        cpp_rel = os.path.join(ROOT_DIR, "c++ projects", "vs_project", "Release")
    if os.path.isdir(cpp_rel):
        for item in os.listdir(cpp_rel):
            if item.endswith(".pdb") or item.endswith(".obj") or item.endswith(".tlog") or item.endswith(".log"):
                continue
            s = os.path.join(cpp_rel, item)
            d = os.path.join(stage_cpp, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

    # 2. Add Downloader tools (N_m3u8DL-RE.exe, ffmpeg.exe)
    for tool in ["N_m3u8DL-RE.exe", "ffmpeg.exe"]:
        cand_list = [
            os.path.join(DESKTOP_DIR, "bin", tool),
            os.path.join(ROOT_DIR, "release_output", tool),
            os.path.join(ROOT_DIR, "Release Test", tool),
            shutil.which(tool) or "",
        ]
        for c in cand_list:
            if c and os.path.isfile(c):
                shutil.copy2(c, os.path.join(stage_cpp, tool))
                break

    # 3. Add uninstaller and icons into stage_cpp
    uninst_src = os.path.join(DESKTOP_DIR, "uninstall.exe")
    if os.path.isfile(uninst_src):
        shutil.copy2(uninst_src, os.path.join(stage_cpp, "uninstall.exe"))

    if os.path.isfile(ICON_PATH):
        shutil.copy2(ICON_PATH, os.path.join(stage_cpp, "app_icon.ico"))
        shutil.copy2(ICON_PATH, os.path.join(STAGE_DIR, "app_icon.ico"))

    png_icon = os.path.join(DESKTOP_DIR, "app_icon.png")
    if os.path.isfile(png_icon):
        shutil.copy2(png_icon, os.path.join(stage_cpp, "app_icon.png"))

    # Also keep a minimal desktop/ folder with extension_manager, ui_icons, window_chrome so installer UI runs
    stage_desktop = os.path.join(STAGE_DIR, "desktop")
    os.makedirs(stage_desktop, exist_ok=True)
    for m in ["extension_manager.py", "ui_icons.py", "window_chrome.py", "app_icon.png", "app_icon.ico"]:
        src = os.path.join(DESKTOP_DIR, m)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(stage_desktop, m))

    # Chrome extension sources
    shutil.copytree(EXT_DIR, os.path.join(STAGE_DIR, "extension"))

    return stage_cpp, stage_desktop


def build():
    print("=" * 65)
    print(f"Compiling {SETUP_NAME}.exe (OmniStream Pro v2.6.0 C++ Windows Installer)...")
    print("=" * 65)

    stage_cpp, stage_desktop = _stage_payload()
    stage_ext = os.path.join(STAGE_DIR, "extension")
    stage_icon = os.path.join(STAGE_DIR, "app_icon.ico")

    add_data_args = [
        "--add-data", f"{stage_cpp};cpp_app",
        "--add-data", f"{stage_desktop};desktop",
        "--add-data", f"{stage_ext};extension",
        "--add-data", f"{stage_icon};.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", SETUP_NAME,
        "--icon", ICON_PATH,
        "--paths", stage_desktop,
        "--paths", DESKTOP_DIR,
        "--hidden-import", "extension_manager",
        "--hidden-import", "ui_icons",
        "--hidden-import", "window_chrome",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "webbrowser",
        "--hidden-import", "glob",
        "--hidden-import", "json",
        "--hidden-import", "shutil",
        "--hidden-import", "subprocess",
        "--hidden-import", "winreg",
        "--hidden-import", "http.server",
        "--hidden-import", "socketserver",
        "--collect-all", "customtkinter",
        "--collect-all", "PIL",
        *add_data_args,
        "installer.py",
    ]

    res = subprocess.run(cmd, cwd=ROOT_DIR)
    if res.returncode != 0:
        print("[Error] Failed to build installer executable!")
        return False

    dist_exe = os.path.join(ROOT_DIR, "dist", f"{SETUP_NAME}.exe")
    if not os.path.exists(dist_exe):
        print("[Error] Installer exe not found after build.")
        return False

    # Verify PyInstaller PKG cookie is present (bootloader needs this).
    magic = b"MEI\x0c\x0b\x0a\x0b\x0e"
    data = open(dist_exe, "rb").read()
    if magic not in data:
        print("[Error] Built Setup.exe is missing the PyInstaller PKG cookie.")
        print("        Refusing to publish a broken installer.")
        return False

    release_out = os.path.join(ROOT_DIR, "release_output")
    os.makedirs(release_out, exist_ok=True)
    out_path = os.path.join(release_out, f"{SETUP_NAME}.exe")
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", f"{SETUP_NAME}.exe"], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
    import time
    for _ in range(5):
        try:
            shutil.copy2(dist_exe, out_path)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        shutil.copy2(dist_exe, out_path)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print("=" * 65)
    print(f"[SUCCESS] {SETUP_NAME}.exe created successfully ({size_mb:.2f} MB)!")
    print(f"  PKG cookie: OK")
    print(f"  Output    : {out_path}")
    print("=" * 65)

    # Cleanup staging (keep dist/ for debugging if needed)
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    return True


if __name__ == "__main__":
    ok = build()
    sys.exit(0 if ok else 1)
