"""
OmniStream Pro v2.1.0 - Windows Installer (.exe) Compiler
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

# Files the installer copies into AppData (source modules + icons).
DESKTOP_FILES = [
    "main_gui.py",
    "core_engine.py",
    "bridge_server.py",
    "setup_dependencies.py",
    "extension_manager.py",
    "ui_icons.py",
    "window_chrome.py",
    "app_icon.ico",
    "app_icon.png",
]


def _clean_stage():
    if os.path.isdir(STAGE_DIR):
        shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(STAGE_DIR, exist_ok=True)


def _stage_payload():
    """Build a clean payload tree without nested PyInstaller artifacts."""
    _clean_stage()

    stage_desktop = os.path.join(STAGE_DIR, "desktop")
    os.makedirs(stage_desktop, exist_ok=True)

    for name in DESKTOP_FILES:
        src = os.path.join(DESKTOP_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(stage_desktop, name))

    # Tools (ffmpeg / downloader) — required at install time.
    src_bin = os.path.join(DESKTOP_DIR, "bin")
    if os.path.isdir(src_bin):
        shutil.copytree(src_bin, os.path.join(stage_desktop, "bin"))

    # Prefer freshly built portable exe from release_output, else desktop/dist.
    portable_candidates = [
        os.path.join(RELEASE_DIR, "OmniStream_Pro.exe"),
        os.path.join(DESKTOP_DIR, "dist", "OmniStream_Pro.exe"),
    ]
    portable = next((p for p in portable_candidates if os.path.isfile(p)), None)
    if not portable:
        raise FileNotFoundError(
            "OmniStream_Pro.exe not found. Build the portable exe before the installer."
        )
    # Keep under desktop/ so installer.py candidate paths keep working.
    shutil.copy2(portable, os.path.join(stage_desktop, "OmniStream_Pro.exe"))

    # Chrome extension sources
    shutil.copytree(EXT_DIR, os.path.join(STAGE_DIR, "extension"))

    # Icon at payload root (also referenced as --add-data)
    if os.path.isfile(ICON_PATH):
        shutil.copy2(ICON_PATH, os.path.join(STAGE_DIR, "app_icon.ico"))

    return stage_desktop


def build():
    print("=" * 65)
    print(f"Compiling {SETUP_NAME}.exe (OmniStream Pro v2.1.0 Windows Installer)...")
    print("=" * 65)

    stage_desktop = _stage_payload()
    stage_ext = os.path.join(STAGE_DIR, "extension")
    stage_icon = os.path.join(STAGE_DIR, "app_icon.ico")

    add_data_args = [
        "--add-data", f"{stage_desktop};desktop",
        "--add-data", f"{stage_ext};extension",
        "--add-data", f"{stage_icon};.",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", SETUP_NAME,
        "--icon", ICON_PATH,
        "--paths", stage_desktop,
        "--paths", DESKTOP_DIR,
        "--hidden-import", "extension_manager",
        "--hidden-import", "ui_icons",
        "--hidden-import", "window_chrome",
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
