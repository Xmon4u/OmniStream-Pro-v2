"""
OmniStream Pro v2.0.0 - Release Builder
Builds the standalone executable (.exe), Setup Installer (.exe), and packages the Chrome Extension (.zip)
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import shutil
import zipfile
import subprocess

ROOT_DIR      = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR   = os.path.join(ROOT_DIR, "desktop")
EXTENSION_DIR = os.path.join(ROOT_DIR, "extension")
RELEASE_DIR   = os.path.join(ROOT_DIR, "release_output")

VERSION = "v2.2.0"
EXE_NAME = "OmniStream_Pro.exe"
ZIP_NAME = f"OmniStream-Pro-Chrome-Extension-{VERSION}.zip"

def package_extension(zip_path: str):
    print(f"\n[1/3] Packaging Chrome Extension into {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for foldername, _, filenames in os.walk(EXTENSION_DIR):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, EXTENSION_DIR)
                zf.write(filepath, arcname)
    size_kb = os.path.getsize(zip_path) / 1024
    print(f"  [OK] Extension package created: {size_kb:.1f} KB")

def build_executable():
    print(f"\n[2/3] Compiling {EXE_NAME} via PyInstaller...")
    build_script = os.path.join(DESKTOP_DIR, "build_exe.py")
    res = subprocess.run([sys.executable, build_script], cwd=DESKTOP_DIR)
    if res.returncode != 0:
        raise RuntimeError("Desktop PyInstaller build failed.")
    dist_exe = os.path.join(DESKTOP_DIR, "dist", EXE_NAME)
    if not os.path.exists(dist_exe):
        raise FileNotFoundError(f"Expected compiled executable at {dist_exe}")
    return dist_exe

def build_uninstaller():
    print(f"\n[3/5] Compiling native uninstaller (uninstall.exe)...")
    build_script = os.path.join(DESKTOP_DIR, "build_uninstaller.py")
    res = subprocess.run([sys.executable, build_script], cwd=DESKTOP_DIR)
    if res.returncode != 0:
        raise RuntimeError("Uninstaller compilation failed.")
    dist_uninst = os.path.join(DESKTOP_DIR, "uninstall.exe")
    if not os.path.exists(dist_uninst):
        raise FileNotFoundError(f"Expected uninstaller at {dist_uninst}")
    release_uninst = os.path.join(RELEASE_DIR, "uninstall.exe")
    shutil.copy2(dist_uninst, release_uninst)
    return release_uninst

def build_installer():
    print(f"\n[4/5] Compiling Windows Setup Installer (OmniStream_Pro_Setup.exe)...")
    build_script = os.path.join(ROOT_DIR, "build_installer.py")
    res = subprocess.run([sys.executable, build_script], cwd=ROOT_DIR)
    if res.returncode != 0:
        raise RuntimeError("Installer PyInstaller build failed.")
    dist_setup = os.path.join(RELEASE_DIR, "OmniStream_Pro_Setup.exe")
    if not os.path.exists(dist_setup):
        raise FileNotFoundError(f"Expected compiled installer at {dist_setup}")
    return dist_setup

def main():
    print("=" * 65)
    print(f"  OmniStream Pro {VERSION} - Automated Release Builder")
    print("=" * 65)

    os.makedirs(RELEASE_DIR, exist_ok=True)

    # 1. Package extension
    ext_zip_path = os.path.join(RELEASE_DIR, ZIP_NAME)
    package_extension(ext_zip_path)

    # 2. Compile desktop portable exe
    dist_exe_path = build_executable()
    release_exe_path = os.path.join(RELEASE_DIR, EXE_NAME)
    try:
        subprocess.run(["taskkill", "/F", "/IM", EXE_NAME], capture_output=True, creationflags=0x08000000)
    except Exception:
        pass
    import time
    for _ in range(5):
        try:
            shutil.copy2(dist_exe_path, release_exe_path)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        shutil.copy2(dist_exe_path, release_exe_path)
    size_mb = os.path.getsize(release_exe_path) / (1024 * 1024)
    print(f"\n[2/5] Copied {EXE_NAME} to release folder ({size_mb:.2f} MB).")

    # 3. Compile native uninstaller
    uninst_path = build_uninstaller()

    # 4. Compile Windows Setup Installer
    setup_path = build_installer()

    # 5. Copy downloader engine binary (N_m3u8DL-RE.exe)
    dl_engine_src = os.path.join(DESKTOP_DIR, "bin", "N_m3u8DL-RE.exe")
    dl_engine_dst = os.path.join(RELEASE_DIR, "N_m3u8DL-RE.exe")
    if os.path.exists(dl_engine_src):
        shutil.copy2(dl_engine_src, dl_engine_dst)
        print(f"\n[5/5] Copied Downloader engine (N_m3u8DL-RE.exe) to release folder.")

    print("\n" + "=" * 65)
    print(f"[SUCCESS] All {VERSION} release assets prepared:")
    print(f"  1. Windows Installer EXE : {setup_path}")
    print(f"  2. Portable Desktop App  : {release_exe_path}")
    print(f"  3. Downloader Engine EXE : {dl_engine_dst}")
    print(f"  4. Native Uninstaller    : {uninst_path}")
    print(f"  5. Chrome Extension Zip  : {ext_zip_path}")
    print("=" * 65)

if __name__ == "__main__":
    main()
