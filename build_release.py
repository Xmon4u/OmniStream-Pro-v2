"""
OmniStream Pro v2.6.0 - Release Builder (C++ Native Primary Engine)
Compiles the C++ Native Application (.exe), deploys Qt runtime,
packages the Standalone Portable C++ Suite (.zip),
builds the Windows Setup Installer (.exe), and packages the Chrome Extension (.zip).
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import shutil
import zipfile
import subprocess
import glob

ROOT_DIR       = os.path.dirname(os.path.abspath(__file__))
CPP_DIR        = os.path.join(ROOT_DIR, "C++") if os.path.exists(os.path.join(ROOT_DIR, "C++")) else os.path.join(ROOT_DIR, "c++ projects")
CPP_SLN        = os.path.join(CPP_DIR, "vs_project", "OmniStreamProCpp.sln")
CPP_REL_DIR    = os.path.join(CPP_DIR, "vs_project", "Release")
CPP_EXE        = os.path.join(CPP_REL_DIR, "OmniStream_Pro.exe")
DESKTOP_DIR    = os.path.join(ROOT_DIR, "desktop")
EXTENSION_DIR  = os.path.join(ROOT_DIR, "extension")
RELEASE_DIR    = os.path.join(ROOT_DIR, "release_output")
TEST_RELEASE_DIR = os.path.join(ROOT_DIR, "Release Test")

VERSION        = "v2.6.0"
EXE_NAME       = "OmniStream_Pro.exe"
PORTABLE_ZIP   = f"OmniStream_Pro_{VERSION}_C++_Portable.zip"
EXT_ZIP_NAME   = f"OmniStream-Pro-Chrome-Extension-{VERSION}.zip"


def find_msbuild() -> str:
    """Locate MSBuild.exe via vswhere or standard Visual Studio paths."""
    # 1. Check known VS 2022 path
    known_paths = [
        r"D:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\MSBuild.exe",
    ]
    for p in known_paths:
        if os.path.isfile(p):
            return p

    # 2. Check vswhere
    vswhere = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if os.path.isfile(vswhere):
        try:
            out = subprocess.check_output([
                vswhere, "-latest", "-requires", "Microsoft.Component.MSBuild",
                "-find", r"MSBuild\**\Bin\MSBuild.exe"
            ], text=True).strip()
            if out and os.path.isfile(out.splitlines()[0]):
                return out.splitlines()[0]
        except Exception:
            pass

    # 3. Check PATH
    which_ms = shutil.which("msbuild")
    if which_ms:
        return which_ms

    raise FileNotFoundError("MSBuild.exe not found on this system.")


def find_windeployqt() -> str:
    """Locate windeployqt.exe for Qt runtime deployment."""
    known_paths = [
        r"D:\Qt\6.6.3\msvc2019_64\bin\windeployqt.exe",
        r"C:\Qt\6.6.3\msvc2019_64\bin\windeployqt.exe",
    ]
    for p in known_paths:
        if os.path.isfile(p):
            return p

    # Search common Qt roots
    for drive in ["D:\\Qt", "C:\\Qt"]:
        if os.path.isdir(drive):
            matches = glob.glob(os.path.join(drive, "**", "windeployqt.exe"), recursive=True)
            if matches:
                return matches[0]

    which_qt = shutil.which("windeployqt")
    if which_qt:
        return which_qt

    raise FileNotFoundError("windeployqt.exe not found on this system.")


def package_extension(zip_path: str):
    print(f"\n[1/6] Packaging Chrome Extension into {os.path.basename(zip_path)}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for foldername, _, filenames in os.walk(EXTENSION_DIR):
            for filename in filenames:
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, EXTENSION_DIR)
                zf.write(filepath, arcname)
    size_kb = os.path.getsize(zip_path) / 1024
    print(f"  [OK] Extension package created: {size_kb:.1f} KB")


def build_cpp_executable():
    print(f"\n[2/6] Compiling C++ Native Desktop Application (OmniStream_Pro.exe)...")
    msbuild = find_msbuild()
    print(f"  MSBuild : {msbuild}")
    print(f"  Solution: {CPP_SLN}")

    res = subprocess.run([msbuild, CPP_SLN, "/p:Configuration=Release", "/p:Platform=x64", "/m"], cwd=CPP_DIR)
    if res.returncode != 0:
        raise RuntimeError("C++ MSBuild compilation failed.")

    if not os.path.isfile(CPP_EXE):
        raise FileNotFoundError(f"Expected compiled C++ binary at {CPP_EXE}")

    # Deploy Qt runtime dependencies
    windeployqt = find_windeployqt()
    print(f"  Deploying Qt runtime using {windeployqt}...")
    subprocess.run([
        windeployqt, "--release", "--no-translations", "--compiler-runtime", CPP_EXE
    ], cwd=CPP_REL_DIR, check=True)

    # Run self-tests on the newly built C++ executable
    print(f"  Running C++ Native Core Self-Test Suite...")
    test_res = subprocess.run([CPP_EXE, "--test"], cwd=CPP_REL_DIR, capture_output=True, text=True)
    if test_res.returncode != 0:
        print(test_res.stdout)
        print(test_res.stderr)
        raise RuntimeError("C++ Native Core Self-Test failed!")
    result_line = [l.strip() for l in test_res.stdout.splitlines() if "RESULT:" in l]
    res_str = result_line[0] if result_line else "All tests passed"
    print(f"  [OK] C++ Self-Tests successful ({res_str}).")

    # Copy Downloader Engine tools (N_m3u8DL-RE.exe and ffmpeg.exe) to C++ Release directory
    for tool in ["N_m3u8DL-RE.exe", "ffmpeg.exe"]:
        tool_src = os.path.join(DESKTOP_DIR, "bin", tool)
        if not os.path.isfile(tool_src):
            tool_src = os.path.join(RELEASE_DIR, tool)
        if not os.path.isfile(tool_src):
            which_p = shutil.which(tool)
            if which_p and os.path.isfile(which_p):
                tool_src = which_p
        if tool_src and os.path.isfile(tool_src):
            shutil.copy2(tool_src, os.path.join(CPP_REL_DIR, tool))

    # Copy icons
    icon_ico = os.path.join(CPP_DIR, "app_icon.ico")
    if os.path.isfile(icon_ico):
        shutil.copy2(icon_ico, os.path.join(CPP_REL_DIR, "app_icon.ico"))

    return CPP_EXE


def package_cpp_portable(zip_path: str):
    print(f"\n[3/6] Packaging Standalone C++ Portable Suite into {os.path.basename(zip_path)}...")
    ignore_exts = {".pdb", ".obj", ".tlog", ".log", ".lastbuildstate"}
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for foldername, _, filenames in os.walk(CPP_REL_DIR):
            for filename in filenames:
                _, ext = os.path.splitext(filename)
                if ext.lower() in ignore_exts:
                    continue
                filepath = os.path.join(foldername, filename)
                arcname = os.path.relpath(filepath, CPP_REL_DIR)
                # Store files inside a root folder "OmniStream_Pro_v2.6.0" in the zip
                zip_arc = os.path.join("OmniStream_Pro_v2.6.0", arcname)
                zf.write(filepath, zip_arc)

        # Include root README and LICENSE inside the portable zip
        for doc in ["README.md", "LICENSE"]:
            doc_path = os.path.join(ROOT_DIR, doc)
            if os.path.isfile(doc_path):
                zf.write(doc_path, os.path.join("OmniStream_Pro_v2.6.0", doc))

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"  [OK] Standalone C++ Portable Suite created: {size_mb:.2f} MB")


def build_uninstaller():
    print(f"\n[4/6] Compiling Windows Native Uninstaller (uninstall.exe)...")
    build_script = os.path.join(DESKTOP_DIR, "build_uninstaller.py")
    res = subprocess.run([sys.executable, build_script], cwd=DESKTOP_DIR)
    if res.returncode != 0:
        raise RuntimeError("Uninstaller compilation failed.")
    dist_uninst = os.path.join(DESKTOP_DIR, "uninstall.exe")
    if not os.path.exists(dist_uninst):
        raise FileNotFoundError(f"Expected uninstaller at {dist_uninst}")
    release_uninst = os.path.join(RELEASE_DIR, "uninstall.exe")
    shutil.copy2(dist_uninst, release_uninst)
    shutil.copy2(dist_uninst, os.path.join(CPP_REL_DIR, "uninstall.exe"))
    return release_uninst


def build_installer():
    print(f"\n[5/6] Compiling Windows Setup Installer (OmniStream_Pro_Setup.exe)...")
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
    print(f"  OmniStream Pro {VERSION} - C++ Native Automated Release Builder")
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
    ext_zip_path = os.path.join(RELEASE_DIR, EXT_ZIP_NAME)
    package_extension(ext_zip_path)

    # 2. Compile uninstaller first so it can be packaged with C++ suite
    uninst_path = build_uninstaller()

    # 3. Compile C++ Desktop Application (.exe) and deploy Qt runtime
    cpp_exe_path = build_cpp_executable()
    release_exe_path = os.path.join(RELEASE_DIR, EXE_NAME)
    shutil.copy2(cpp_exe_path, release_exe_path)
    size_mb = os.path.getsize(release_exe_path) / (1024 * 1024)
    print(f"  [OK] Copied C++ Native {EXE_NAME} to release folder ({size_mb:.2f} MB).")

    # 4. Copy downloader engine binaries (N_m3u8DL-RE.exe & ffmpeg.exe)
    for tool_name in ["N_m3u8DL-RE.exe", "ffmpeg.exe"]:
        t_src = os.path.join(CPP_REL_DIR, tool_name)
        if not os.path.exists(t_src):
            t_src = os.path.join(DESKTOP_DIR, "bin", tool_name)
        if not os.path.exists(t_src):
            t_src = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OmniStreamPro", "bin", tool_name)
        if not os.path.exists(t_src):
            which_p = shutil.which(tool_name)
            if which_p and os.path.exists(which_p):
                t_src = which_p
        if t_src and os.path.exists(t_src):
            shutil.copy2(t_src, os.path.join(RELEASE_DIR, tool_name))
            print(f"  [OK] Copied {tool_name} to release folder.")

    dl_engine_dst = os.path.join(RELEASE_DIR, "N_m3u8DL-RE.exe")
    ffmpeg_dst = os.path.join(RELEASE_DIR, "ffmpeg.exe")

    # 5. Package Standalone C++ Portable Suite
    portable_zip_path = os.path.join(RELEASE_DIR, PORTABLE_ZIP)
    package_cpp_portable(portable_zip_path)

    # 6. Compile Windows Setup Installer (OmniStream_Pro_Setup.exe)
    setup_path = build_installer()

    # Sync to Release Test directory
    os.makedirs(TEST_RELEASE_DIR, exist_ok=True)
    print(f"\n[Sync] Copying all freshly built C++ release assets to {TEST_RELEASE_DIR}...")
    assets = [
        ("OmniStream_Pro_Setup.exe", setup_path),
        (EXE_NAME, release_exe_path),
        (PORTABLE_ZIP, portable_zip_path),
        (EXT_ZIP_NAME, ext_zip_path),
        ("N_m3u8DL-RE.exe", dl_engine_dst),
        ("ffmpeg.exe", ffmpeg_dst),
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

    # Sync C++ project and extension sources for developer inspection
    cpp_sync_src = "C++" if os.path.exists(os.path.join(ROOT_DIR, "C++")) else "c++ projects"
    for src_rel, dst_rel in [(cpp_sync_src, "C++_Engine"), ("extension", "Extension")]:
        src_path = os.path.join(ROOT_DIR, src_rel)
        dst_path = os.path.join(TEST_RELEASE_DIR, dst_rel)
        if os.path.exists(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.obj", "*.tlog", "*.log", ".vs", "__pycache__", "dist", "build"))
            print(f"  -> Synced {src_rel} -> {dst_rel}")

    # Copy root doc files
    for root_doc in ["README.md", "RELEASE_NOTES.md", "LICENSE", "Start_OmniStream_Pro.bat"]:
        src_doc = os.path.join(ROOT_DIR, root_doc)
        if os.path.exists(src_doc):
            shutil.copy2(src_doc, os.path.join(TEST_RELEASE_DIR, root_doc))

    guide_content = f"""# OmniStream Pro {VERSION} — C++ Native Release & Quality Verification

## প্রতিটি ফাইলের বিবরণ:
1. **OmniStream_Pro_Setup.exe** — সম্পূর্ণ C++ Windows ইনস্টলার (C++ Native App ও Qt Runtime ইনস্টল করে, Start Menu ও Desktop shortcut তৈরি করে এবং Extension ইন্টিগ্রেট করে)।
2. **{PORTABLE_ZIP}** — Standalone Portable C++ Suite (ইনস্টলেশন ছাড়াই আনজিপ করে সরাসরি চালু করা যায়, সাথে প্রয়োজনীয় সব Qt DLLs ও N_m3u8DL-RE যুক্ত)।
3. **OmniStream_Pro.exe** — C++ Native Desktop Application Executable (MSVC x64 Native Core Engine)।
4. **{EXT_ZIP_NAME}** — Chrome / Edge / Brave Extension প্যাকেজ (Manifest v3)।
5. **N_m3u8DL-RE.exe** — Ultra-Fast Core Streaming Download Engine।
6. **uninstall.exe** — Windows Native Clean Uninstaller (সহজে সম্পূর্ণ আনইনস্টল করার জন্য)।
7. **C++_Engine/** — MSVC 2022 Native C++ Source & Visual Studio Solution।
8. **Extension/** — Chrome Extension Manifest v3 Unpacked Source।

---

## কিভাবে পরীক্ষা করবেন (Step-by-Step Testing Guide):

### ধাপ ১: Chrome Extension ইনস্টল করুন
1. Google Chrome ব্রাউজারে `chrome://extensions/` লিখে Enter চাপুন।
2. উপরে ডানে **Developer mode** অন (ON) করুন।
3. **Load unpacked** বাটনে ক্লিক করে `Release Test/Extension` ফোল্ডারটি সিলেক্ট করুন (অথবা `{EXT_ZIP_NAME}` আনজিপ করে লোড করতে পারেন)।

### ধাপ ২: C++ Downloader Manager ইনস্টল ও চালু করুন
1. `Release Test/OmniStream_Pro_Setup.exe` চালু করুন এবং ইনস্টল করুন।
   - ইনস্টলার স্বয়ংক্রিয়ভাবে C++ Native Engine ও Qt Runtime `%LOCALAPPDATA%\\OmniStreamPro` তে ইনস্টল করবে।
   - Desktop এবং Start Menu তে আইকন তৈরি করবে।
2. ডেস্কটপ আইকন বা `Release Test/OmniStream_Pro.exe` চালু করুন।
3. অ্যাপ চালু হলে সবুজ রঙের **Ready / Bridge Active** ব্যাজ দেখতে পাবেন (Port 28795)।

### ধাপ ৩: 1-Click Stream Capture পরীক্ষা করুন
1. যেকোনো স্ট্রিমিং সাইট বা Netflix ভিডিও প্লে করুন।
2. ব্রাউজারের Extension আইকনে ক্লিক করুন—দেখা যাবে "App Connected"।
3. **Send to OmniStream** বাটনে চাপ দিন—ডাউনলোড ম্যানেজারে স্বয়ংক্রিয়ভাবে লিঙ্ক ও আইডি চলে আসবে এবং ডাউনলোড শুরু হবে!

### ধাপ ৪: Download Mode (Netflix / IMDb / TMDB) পরীক্ষা করুন
- **Netflix Mode:** ফাইলের নাম হবে `81902147_S01E01.mp4` বা নিদিষ্ট Netflix ID।
- **IMDb Mode:** স্বয়ংক্রিয়ভাবে IMDb থেকে মুভি টাইটেল ও আইডি নিয়ে `tt18259086_S01E01.mp4` নাম হবে।
- **TMDB Mode:** স্বয়ংক্রিয়ভাবে TheMovieDB থেকে অফিসিয়াল আইডি নিয়ে `939243_S01E01.mp4` নাম হবে।

### ধাপ ৫: Full View ও UI Buttons পরীক্ষা করুন
- **Full View ↗** বাটনে ক্লিক করলে কিউ ম্যানেজার বড় হয়ে পুরো উইন্ডো জুড়ে দেখাবে।
- **← Back to Dashboard** অথবা **Escape (Esc)** চাপলে পূর্বের ড্যাশবোর্ডে ফিরে আসবে।
- **Theme Dropdown (Cyber Slate / Midnight Black):** সাথে সাথে ইন্টারফেসের থিম সুইচ হবে।
- **Download Subtitles:** সাবটাইটেল ফরম্যাট (SRT / VTT) ও ভাষা অনুযায়ী শুধু সাবটাইটেল সেভ হবে।
- **Stop / Clear Queue / Clear Logs:** তাৎক্ষণিক প্রতিক্রিয়া নিশ্চিত করা হয়েছে।
"""
    with open(os.path.join(TEST_RELEASE_DIR, "How_To_Test.md"), "w", encoding="utf-8") as f:
        f.write(guide_content)

    print("\n" + "=" * 65)
    print(f"[SUCCESS] All {VERSION} C++ Native release assets prepared fresh in:")
    print(f"  -> {RELEASE_DIR}")
    print(f"  -> {TEST_RELEASE_DIR}")
    print("=" * 65)


if __name__ == "__main__":
    main()
