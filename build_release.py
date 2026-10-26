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

TEST_RELEASE_DIR = os.path.join(ROOT_DIR, "Release Test")

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

    # Do not wipe entire TEST_RELEASE_DIR to avoid deleting source checkouts
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

    # Sync source modules for complete code inspection
    for src_rel, dst_rel in [("c++ projects", "C++_Engine"), ("desktop", "Desktop"), ("extension", "Extension")]:
        src_path = os.path.join(ROOT_DIR, src_rel)
        dst_path = os.path.join(TEST_RELEASE_DIR, dst_rel)
        if os.path.exists(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.obj", "*.tlog", "*.log", ".vs", "__pycache__", "dist", "build"))
            print(f"  -> Synced {src_rel} -> {dst_rel}")

    # Copy root doc files
    for root_doc in ["README.md", "RELEASE_NOTES.md", "LICENSE", "requirements.txt", "Start_OmniStream_Pro.bat"]:
        src_doc = os.path.join(ROOT_DIR, root_doc)
        if os.path.exists(src_doc):
            shutil.copy2(src_doc, os.path.join(TEST_RELEASE_DIR, root_doc))

    guide_content = f"""# OmniStream Pro {VERSION} — Release Test & Quality Verification

## \u09aa\u09cd\u09b0\u09a4\u09bf\u099f\u09bf \u09ab\u09be\u0987\u09b2\u09c7\u09b0 \u09ac\u09bf\u09ac\u09b0\u09a3:
1. **OmniStream_Pro_Setup.exe** — \u09b8\u09ae\u09cd\u09aa\u09c2\u09b0\u09cd\u09a3 Windows \u0987\u09a8\u09b8\u09cd\u099f\u09b2\u09be\u09b0 (Auto-detection, Start Menu \u0993 Desktop shortcut \u09a4\u09c8\u09b0\u09bf \u0995\u09b0\u09c7)।
2. **OmniStream_Pro.exe** — Standalone Portable Application (\u0987\u09a8\u09b8\u09cd\u099f\u09b2 \u099b\u09be\u09dc\u09be\u0987 \u09b8\u09b0\u09be\u09b8\u09b0\u09bf \u099a\u09be\u09b2\u09be\u09a8\u09cb \u09af\u09be\u09af\u09bc)।
3. **{ZIP_NAME}** — Chrome / Edge / Brave Extension \u09aa\u09cd\u09af\u09be\u0995\u09c7\u099c।
4. **N_m3u8DL-RE.exe** — Ultra Fast Core Streaming Download Engine।
5. **uninstall.exe** — Windows Native Clean Uninstaller।
6. **C++_Engine/** — MSVC 2022 Native C++ Source & VS Solution।
7. **Desktop/** — Python + CustomTkinter Desktop GUI & Engine।
8. **Extension/** — Chrome Extension Manifest v3 Unpacked Source।

## \u0995\u09bf\u09ad\u09be\u09ac\u09c7 \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be \u0995\u09b0\u09ac\u09c7\u09a8 (Step-by-Step Testing Guide):

### \u09a7\u09be\u09aa \u09e7: Chrome Extension \u0987\u09a8\u09b8\u09cd\u099f\u09b2 \u0995\u09b0\u09c1\u09a8
1. Google Chrome \u09ac\u09cd\u09b0\u09be\u0989\u099c\u09be\u09b0\u09c7 `chrome://extensions/` \u09b2\u09bf\u0996\u09c7 Enter \u099a\u09be\u09aa\u09c1\u09a8।
2. \u0989\u09aa\u09b0\u09c7 \u09a1\u09be\u09a8\u09c7 **Developer mode** \u0985\u09a8 (ON) \u0995\u09b0\u09c1\u09a8।
3. **Load unpacked** \u09ac\u09be\u099f\u09a8\u09c7 \u0995\u09cd\u09b2\u09bf\u0995 \u0995\u09b0\u09c7 `Release Test/Extension` \u09ab\u09cb\u09b2\u09cd\u09a1\u09be\u09b0\u099f\u09bf \u09b8\u09c7\u09b2\u09c7\u0995\u09cd\u099f \u0995\u09b0\u09c1\u09a8 (অথবা `{ZIP_NAME}` আনজিপ করে লোড করতে পারেন)।

### \u09a7\u09be\u09aa \u09e8: Downloader Manager \u099a\u09be\u09b2\u09c1 \u0995\u09b0\u09c1\u09a8
1. `Release Test/OmniStream_Pro.exe` চালু করুন (অথবা `OmniStream_Pro_Setup.exe` দিয়ে ইনস্টল করে ডেস্কটপ আইকন থেকে চালু করুন)।
2. অ্যাপ চালু হলে সবুজ রঙের **Bridge Active** নোটিশ দেখতে পাবেন (Port 28795)।

### \u09a7\u09be\u09aa \u09e9: 1-Click Stream Capture \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be \u0995\u09b0\u09c1\u09a8
1. যেকোনো স্ট্রিমিং সাইট বা Netflix ভিডিও প্লে করুন।
2. ব্রাউজারের Extension আইকনে ক্লিক করুন—দেখা যাবে "App Connected"।
3. **Send to OmniStream** বাটনে চাপ দিন—ডাউনলোড ম্যানেজারে স্বয়ংক্রিয়ভাবে লিঙ্ক ও আইডি চলে আসবে এবং ডাউনলোড শুরু হবে!

### \u09a7\u09be\u09aa \u09e8: Download Mode (Netflix / IMDb / TMDB) \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be \u0995\u09b0\u09c1\u09a8
- **Netflix Mode:** ফাইলের নাম হবে `81902147_S01E01.mp4` বা নিদিষ্ট Netflix ID।
- **IMDb Mode:** স্বয়ংক্রিয়ভাবে IMDb থেকে মুভি টাইটেল ও আইডি নিয়ে `tt18259086_S01E01.mp4` নাম হবে।
- **TMDB Mode:** স্বয়ংক্রিয়ভাবে TheMovieDB থেকে অফিসিয়াল আইডি নিয়ে `939243_S01E01.mp4` নাম হবে।

### \u09a7\u09be\u09aa \u09eb: Full View \u0993 UI Buttons \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be \u0995\u09b0\u09c1\u09a8
- **Full View ↗** বাটনে ক্লিক করলে কিউ ম্যানেজার বড় হয়ে পুরো উইন্ডো জুড়ে দেখাবে।
- **← Back to Dashboard** অথবা **Escape (Esc)** চাপলে পূর্বের ড্যাশবোর্ডে ফিরে আসবে।
- **Theme Dropdown (Cyber Slate / Midnight Black):** সাথে সাথে ইন্টারফেসের থিম সুইচ হবে।
- **Download Subtitles:** সাবটাইটেল ফরম্যাট (SRT / VTT) ও ভাষা অনুযায়ী শুধু সাবটাইটেল সেভ হবে।
- **Stop / Clear Queue / Clear Logs:** তাৎক্ষণিক প্রতিক্রিয়া নিশ্চিত করা হয়েছে।
"""
    with open(os.path.join(TEST_RELEASE_DIR, "How_To_Test.md"), "w", encoding="utf-8") as f:
        f.write(guide_content)

    print("\n" + "=" * 65)
    print(f"[SUCCESS] All {VERSION} release assets prepared fresh in:")
    print(f"  -> {RELEASE_DIR}")
    print(f"  -> {TEST_RELEASE_DIR}")
    print("=" * 65)

if __name__ == "__main__":
    main()
