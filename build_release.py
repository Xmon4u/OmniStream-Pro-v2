"""
OmniStream Pro v2.6.0 - Release Builder
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

VERSION = "v2.6.0"
EXE_NAME = "OmniStream_Pro.exe"
ZIP_NAME = f"OmniStream-Pro-Chrome-Extension-{VERSION}.zip"

TEST_RELEASE_DIR = os.path.join(os.path.dirname(ROOT_DIR), f"OmniStream_Pro_{VERSION}_Test_Release")

def package_extension(zip_path: str):
    print(f"\n[1/5] Packaging Chrome Extension into {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for foldername, _, filenames in os.walk(EXTENSION_DIR):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, EXTENSION_DIR)
                zf.write(filepath, arcname)
    size_kb = os.path.getsize(zip_path) / 1024
    print(f"  [OK] Extension package created: {size_kb:.1f} KB")

def build_executable():
    print(f"\n[2/5] Compiling {EXE_NAME} via PyInstaller...")
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

def clean_dir(d: str):
    """Safely delete all existing files in directory."""
    if os.path.exists(d):
        for fname in os.listdir(d):
            fpath = os.path.join(d, fname)
            try:
                if os.path.isfile(fpath) or os.path.islink(fpath):
                    os.remove(fpath)
                elif os.path.isdir(fpath):
                    shutil.rmtree(fpath, ignore_errors=True)
            except Exception as e:
                print(f"  [Notice] Could not remove old file {fname}: {e}")
    else:
        os.makedirs(d, exist_ok=True)

def main():
    print("=" * 65)
    print(f"  OmniStream Pro {VERSION} - Automated Release Builder")
    print("=" * 65)

    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/IM", EXE_NAME], capture_output=True, creationflags=0x08000000)
            subprocess.run(["taskkill", "/F", "/IM", "OmniStream_Pro_Setup.exe"], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass

    # Clean old release outputs
    print("\n[Cleaning] Wiping old build files...")
    clean_dir(RELEASE_DIR)
    clean_dir(TEST_RELEASE_DIR)

    # 1. Package extension
    ext_zip_path = os.path.join(RELEASE_DIR, ZIP_NAME)
    package_extension(ext_zip_path)

    # 2. Compile desktop portable exe
    dist_exe_path = build_executable()
    release_exe_path = os.path.join(RELEASE_DIR, EXE_NAME)
    shutil.copy2(dist_exe_path, release_exe_path)
    size_mb = os.path.getsize(release_exe_path) / (1024 * 1024)
    print(f"\n[2/5] Copied {EXE_NAME} to release folder ({size_mb:.2f} MB).")

    # 3. Compile native uninstaller
    uninst_path = build_uninstaller()

    # 4. Compile Windows Setup Installer
    setup_path = build_installer()

    # 5. Copy downloader engine binary (N_m3u8DL-RE.exe)
    dl_engine_src = os.path.join(DESKTOP_DIR, "bin", "N_m3u8DL-RE.exe")
    if not os.path.exists(dl_engine_src):
        appdata_bin = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OmniStreamPro", "bin", "N_m3u8DL-RE.exe")
        if os.path.exists(appdata_bin):
            dl_engine_src = appdata_bin
        else:
            which_bin = shutil.which("N_m3u8DL-RE.exe")
            if which_bin:
                dl_engine_src = which_bin

    dl_engine_dst = os.path.join(RELEASE_DIR, "N_m3u8DL-RE.exe")
    if os.path.exists(dl_engine_src):
        shutil.copy2(dl_engine_src, dl_engine_dst)
        os.makedirs(os.path.join(DESKTOP_DIR, "bin"), exist_ok=True)
        desktop_bin_path = os.path.join(DESKTOP_DIR, "bin", "N_m3u8DL-RE.exe")
        if not os.path.exists(desktop_bin_path):
            try:
                shutil.copy2(dl_engine_src, desktop_bin_path)
            except Exception:
                pass
        print(f"\n[5/5] Copied Downloader engine (N_m3u8DL-RE.exe) to release folder.")

    # Copy all assets to TEST_RELEASE_DIR
    os.makedirs(TEST_RELEASE_DIR, exist_ok=True)
    print(f"\n[Sync] Copying all freshly built assets to {TEST_RELEASE_DIR}...")
    assets = [
        ("OmniStream_Pro_Setup.exe", setup_path),
        (EXE_NAME, release_exe_path),
        (ZIP_NAME, ext_zip_path),
        ("N_m3u8DL-RE.exe", dl_engine_dst),
        ("uninstall.exe", uninst_path),
    ]
    for name, src in assets:
        if os.path.exists(src):
            dst = os.path.join(TEST_RELEASE_DIR, name)
            shutil.copy2(src, dst)
            sz = os.path.getsize(dst)
            sz_str = f"{sz/(1024*1024):.1f} MB" if sz > 1024*1024 else f"{sz/1024:.0f} KB"
            print(f"  -> {name} ({sz_str})")
        else:
            print(f"  -> {name} (Skipped, file not found: {src})")

    # Generate TESTING_GUIDE.txt
    guide_content = f"""================================================================================
  OmniStream Pro {VERSION} — Fresh Pre-Release Test Package
================================================================================

Files in this folder (All freshly built with recent fixes):
1. OmniStream_Pro_Setup.exe                   — Full Windows Installer
2. OmniStream_Pro.exe                         — Standalone Portable Application
3. {ZIP_NAME}  — Chrome Extension Package
4. N_m3u8DL-RE.exe                            — Downloader Engine Binary
5. uninstall.exe                              — Native Uninstaller

Verified Fixes in this Build:
-----------------------------
1. Window Maximize & Fullscreen ("Not Responding" Freeze Fixed):
   - Eliminated infinite configure loop and Win32 WNDPROC deadlock.
   - Window now cleanly maximizes across the full work area with instant response.
   - Flattens corners when maximized, cleanly restores rounded borders when unmaximized.

2. Full View Queue Manager & UI Expansion (User Requested):
   - Added 'Full View ↗' button right next to 'Clear All' in the queue toolbar.
   - One-click transition to full-screen queue page with massive scrollable area for dozens of downloads.
   - Prominent '← Back to Dashboard' button (and Escape key) to return immediately to the main screen.
   - Top dashboard cards compacted, increasing normal view queue height by 2.5x.

3. Complete Thread-Safety & Performance:
   - All background threads (downloads, auto-setup, heartbeats) now dispatch safely through main thread queue.
   - Zero Tcl/Tk thread contention or modal blocking.

4. Download Engine & Safety:
   - Relative tracks correctly resolved via --base-url.
   - Safe intermediate file cleanup: never touches user Desktop files.
   - Immediate sub-process termination (taskkill) on Stop/Cancel.

5. Multi-Track Resilience & Accurate Error Diagnosis:
   - Concurrency tuned to 16 threads per stream to avoid CDN rate-limiting/socket exhaustion.
   - Segment retry count increased to 15 with 30s timeout for robust network recovery.
   - Progress lines (e.g. '401/403 segs' or '403 KB/s') isolated so they never falsely trigger 'HTTP 401/403 Forbidden'.
   - Downloader errors faithfully reported with exact failure details.
"""
    with open(os.path.join(TEST_RELEASE_DIR, "TESTING_GUIDE.txt"), "w", encoding="utf-8") as f:
        f.write(guide_content)

    print("\n" + "=" * 65)
    print(f"[SUCCESS] All {VERSION} release assets prepared fresh in:")
    print(f"  -> {RELEASE_DIR}")
    print(f"  -> {TEST_RELEASE_DIR}")
    print("=" * 65)

if __name__ == "__main__":
    main()
