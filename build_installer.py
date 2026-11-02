"""
OmniStream Pro v2.6.0 - Windows Installer (.exe) Compiler
Compiles installer.py into OmniStream_Pro_Setup.exe and OmniStreamPro-Setup.exe using PyInstaller.
Bundles the Native C++20 Core, Qt6 runtimes, streaming binaries (FFmpeg & N_m3u8DL-RE),
browser extension, and dedicated native uninstaller into a single standalone installer.
"""

import os
import sys
import shutil
import subprocess

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_BUILD_DIR = os.path.join(ROOT_DIR, "C++ Projects", "desktop", "build")
CPP_BIN_DIR = os.path.join(ROOT_DIR, "C++ Projects", "desktop", "bin")
DESKTOP_DIR = os.path.join(ROOT_DIR, "desktop")
EXT_DIR = os.path.join(ROOT_DIR, "extension")
RELEASE_DIR = os.path.join(ROOT_DIR, "release_output")
ICON_PATH = os.path.join(DESKTOP_DIR, "app_icon.ico")
SETUP_NAME = "OmniStream_Pro_Setup"
STAGE_DIR = os.path.join(ROOT_DIR, "_installer_stage")

# Helper Python modules for the installer's browser setup engine
PYTHON_HELPER_FILES = [
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

def _ensure_uninstaller():
    uninst_exe = os.path.join(DESKTOP_DIR, "uninstall.exe")
    build_script = os.path.join(DESKTOP_DIR, "build_uninstaller.py")
    if os.path.isfile(build_script):
        subprocess.run([sys.executable, build_script], cwd=DESKTOP_DIR, check=True)
    return uninst_exe

def _stage_payload():
    """Build a comprehensive payload tree containing Native C++20 core, Qt6 DLLs, tools, and extension."""
    _clean_stage()
    uninst_exe = _ensure_uninstaller()

    stage_desktop = os.path.join(STAGE_DIR, "desktop")
    os.makedirs(stage_desktop, exist_ok=True)

    # 1. Stage C++ Release binaries, Qt6 DLLs, and Qt plugins
    if os.path.isdir(CPP_BUILD_DIR):
        for item in os.listdir(CPP_BUILD_DIR):
            if item.endswith((".obj", ".pdb", ".ilk", ".exp", ".lib", ".ninja", ".ninja_log", ".ninja_deps", ".txt", ".cmake")):
                continue
            src = os.path.join(CPP_BUILD_DIR, item)
            dst = os.path.join(stage_desktop, item)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src) and not item.startswith("."):
                shutil.copytree(src, dst, dirs_exist_ok=True)

    # Ensure OmniStreamPro.exe and OmniStream_Pro.exe both exist in payload
    cpp_exe = os.path.join(CPP_BUILD_DIR, "OmniStreamPro.exe")
    if os.path.isfile(cpp_exe):
        shutil.copy2(cpp_exe, os.path.join(stage_desktop, "OmniStreamPro.exe"))
        shutil.copy2(cpp_exe, os.path.join(stage_desktop, "OmniStream_Pro.exe"))

    # 2. Stage streaming binaries (FFmpeg & N_m3u8DL-RE)
    stage_bin = os.path.join(stage_desktop, "bin")
    os.makedirs(stage_bin, exist_ok=True)

    tools = ["ffmpeg.exe", "N_m3u8DL-RE.exe"]
    for t in tools:
        # Search candidate locations: C++ bin, build/bin, desktop/bin
        cands = [
            os.path.join(CPP_BIN_DIR, t),
            os.path.join(CPP_BUILD_DIR, "bin", t),
            os.path.join(DESKTOP_DIR, "bin", t),
        ]
        found = next((p for p in cands if os.path.isfile(p)), None)
        if found:
            shutil.copy2(found, os.path.join(stage_bin, t))

    # 3. Stage native uninstaller
    if os.path.isfile(uninst_exe):
        shutil.copy2(uninst_exe, os.path.join(stage_desktop, "uninstall.exe"))
        shutil.copy2(uninst_exe, os.path.join(stage_desktop, "OmniStreamPro-Uninstaller.exe"))

    # 4. Stage helper python modules and icons
    for name in PYTHON_HELPER_FILES:
        src = os.path.join(DESKTOP_DIR, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(stage_desktop, name))

    # 5. Chrome extension sources
    shutil.copytree(EXT_DIR, os.path.join(STAGE_DIR, "extension"), dirs_exist_ok=True)

    # 6. Icon at payload root
    if os.path.isfile(ICON_PATH):
        shutil.copy2(ICON_PATH, os.path.join(STAGE_DIR, "app_icon.ico"))

    return stage_desktop


def build():
    print("=" * 65)
    print(f"Compiling {SETUP_NAME}.exe (OmniStream Pro v2.6.0 Windows Installer)...")
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

    out_path_p1 = os.path.join(release_out, "01_OmniStream_Pro_Setup.exe")
    shutil.copy2(out_path, out_path_p1)

    out_path_alt = os.path.join(release_out, "OmniStreamPro-Setup.exe")
    shutil.copy2(out_path, out_path_alt)

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print("=" * 65)
    print(f"[SUCCESS] {SETUP_NAME}.exe created successfully ({size_mb:.2f} MB)!")
    print(f"  PKG cookie: OK")
    print(f"  Output    : {out_path}")
    print(f"  Alias     : {out_path_alt}")
    print("=" * 65)

    # Cleanup staging (keep dist/ for debugging if needed)
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    return True


if __name__ == "__main__":
    ok = build()
    sys.exit(0 if ok else 1)
