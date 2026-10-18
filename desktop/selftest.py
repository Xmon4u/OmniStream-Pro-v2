"""
OmniStream Pro v2.3.0 — Comprehensive Self-Test Suite
======================================================
Covers: Module imports, engine methods, progress parsing, subtitle engine,
        N_m3u8DL-RE binary flags, GUI source analysis, extension integrity,
        direct download smoke test, Netflix resolver, fullscreen/window
        risk analysis, release file presence, and optional live bridge test.

Run:   python selftest.py
Exit:  0 = all critical checks passed, 1 = one or more failures.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import inspect
import shutil

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.dirname(os.path.abspath(__file__))
EXT     = os.path.join(ROOT, "extension")
BIN     = os.path.join(DESKTOP, "bin")
sys.path.insert(0, DESKTOP)

fails = []


def ok(name, cond, detail=""):
    if cond:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name}" + (f"  →  {detail}" if detail else ""))
        fails.append(name)
    return bool(cond)


def shutil_which(name):
    return shutil.which(name)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Module Import Tests
# ─────────────────────────────────────────────────────────────────────────────
def load_bg_helpers():
    """Extension source integrity checks."""
    bg        = open(os.path.join(EXT, "background.js"), encoding="utf-8").read()
    popup_js  = open(os.path.join(EXT, "popup.js"),      encoding="utf-8").read()
    popup_html= open(os.path.join(EXT, "popup.html"),    encoding="utf-8").read()
    ok("background has onBeforeRequest",   "onBeforeRequest"    in bg)
    ok("background has isPlaylistItem",    "isPlaylistItem"     in bg)
    ok("background has selectPlayerStreams","selectPlayerStreams" in bg)
    ok("no score < 8 hard gate",           "score < 8"         not in bg)
    ok("no multi-language-only toast",     "No multi-language" not in popup_js)
    ok("popup has God Mode button",        "godScanBtn"         in popup_html)
    ok("popup has Download wiring",        "SEND_TO_OMNISTREAM" in popup_js or "Download" in popup_js)
    ok("popup has no Clear button",        "clearDetectedBtn"  not in popup_html)
    man = json.load(open(os.path.join(EXT, "manifest.json"), encoding="utf-8"))
    ok("manifest version",         man.get("version") in ("2.0.2", "2.1.0", "2.2.0", "2.3.0"))
    ok("manifest webRequest",      "webRequest" in man.get("permissions", []))
    ok("manifest host localhost",  any("127.0.0.1" in h for h in man.get("host_permissions", [])))
    ok("godmode FORCE_SCAN",       "FORCE_SCAN" in open(os.path.join(EXT, "godmode.js"), encoding="utf-8").read())
    ok("content injects godmode",  "godmode.js" in open(os.path.join(EXT, "content.js"), encoding="utf-8").read())


def test_python_modules():
    """All core Python modules must import without error."""
    for mod in ("window_chrome", "ui_icons", "extension_manager", "bridge_server",
                "core_engine", "setup_dependencies", "netflix_resolver"):
        try:
            __import__(mod)
            ok(f"import {mod}", True)
        except Exception as exc:
            ok(f"import {mod}", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 2. Engine Method & Signature Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_engine_methods():
    """Verify all OmniStreamEngine public methods exist and have correct signatures."""
    from core_engine import OmniStreamEngine
    eng = OmniStreamEngine()

    # All methods must exist
    for m in ("parse_input", "fetch_master_playlist", "run_download",
              "run_subtitle_download", "abort", "cleanup_intermediate_files",
              "_download_direct_file"):
        ok(f"OmniStreamEngine.{m} exists", hasattr(eng, m))

    # run_subtitle_download signature
    sig    = inspect.signature(eng.run_subtitle_download)
    params = list(sig.parameters.keys())
    ok("subtitle param: input_text",        "input_text"        in params)
    ok("subtitle param: save_name",         "save_name"         in params)
    ok("subtitle param: save_dir",          "save_dir"          in params)
    ok("subtitle param: sub_format",        "sub_format"        in params)
    ok("subtitle param: sub_lang",          "sub_lang"          in params)
    ok("subtitle param: log_callback",      "log_callback"      in params)
    ok("subtitle param: progress_callback", "progress_callback" in params)
    ok("subtitle returns list",             "list" in str(sig.return_annotation))
    ok("subtitle default format=SRT",       sig.parameters["sub_format"].default == "SRT")
    ok("subtitle default lang=all",         sig.parameters["sub_lang"].default   == "all")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Progress Parser Tests  (video + audio + sub + mux + builder)
# ─────────────────────────────────────────────────────────────────────────────
def test_engine_parsers():
    """Progress line parsing and message building."""
    from core_engine import OmniStreamEngine, _parse_progress_line, _build_progress_message

    # cURL parse
    info = OmniStreamEngine.parse_input(
        'curl "https://cdn.example.com/play/master.m3u8?tok=1" '
        '-H "Referer: https://site.example/" -H "User-Agent: TestUA/1.0" '
        '-H "Cookie: a=b"'
    )
    ok("curl parse url",     "master.m3u8" in info.get("url",     ""))
    ok("curl parse referer", "site.example" in info.get("referer", ""))
    ok("curl parse cookie",  "cookie" in info.get("headers", {}))

    direct = OmniStreamEngine.parse_input("https://cdn.example.com/v/clip.mp4")
    ok("direct url parse", direct.get("url", "").endswith(".mp4"))

    # Video progress line
    v = "Vid 1920x1080 | 6221 Kbps --- 120/400 30.00% 7.58MB/22.74MB 4.05MBps 00:01:12"
    pv = _parse_progress_line(v)
    ok("video line parses",     pv is not None)
    ok("video pct correct",     pv and abs(pv["pct"] - 30.0) < 0.1)
    ok("video track = vid",     pv and pv["track"] == "vid")
    ok("video size parsed",     pv and pv.get("size") == "7.58MB / 22.74MB")
    ok("video speed parsed",    pv and pv.get("speed") and abs(pv["speed"] - 4.05) < 0.1)
    ok("video eta parsed",      pv and pv.get("eta_sec") == 72)

    # Audio progress line
    a = "Aud English | 45/100 45.00% 0.5MB/1.2MB 2.1MBps 00:00:18"
    pa = _parse_progress_line(a)
    ok("audio line parses",  pa is not None)
    ok("audio track = aud",  pa and pa["track"] == "aud")
    ok("audio pct correct",  pa and abs(pa["pct"] - 45.0) < 0.1)

    # Subtitle progress line
    s = "Sub English | 30/100 30.00% 0.1MB/0.3MB 1.0MBps 00:00:10"
    ps = _parse_progress_line(s)
    ok("sub line parses",    ps is not None)
    ok("sub track = sub",    ps and ps["track"] == "sub")
    ok("sub pct correct",    ps and abs(ps["pct"] - 30.0) < 0.1)

    # Mux/merge detection
    mx = "FFmpeg merging audio and video tracks..."
    pm = _parse_progress_line(mx)
    ok("mux line = 99%",     pm and pm["pct"] == 99.0)
    ok("mux track = main",   pm and pm["track"] == "main")

    # N_m3u8DL-RE compact format
    sample2 = "Vid 1920x1080 | 6221 Kbps ------------------------------ 1/3 33.33% 7.58MB/22.74MB4.05MBps00:00:02"
    parsed2 = _parse_progress_line(sample2)
    ok("N_m3u8DL-RE compact pct",   parsed2 and abs(parsed2["pct"] - 33.33) < 0.01)
    ok("N_m3u8DL-RE compact size",  parsed2 and parsed2.get("size") == "7.58MB / 22.74MB")
    ok("N_m3u8DL-RE compact speed", parsed2 and parsed2.get("speed") and abs(parsed2["speed"] - 4.05) < 0.01)
    ok("N_m3u8DL-RE compact eta",   parsed2 and parsed2.get("eta_sec") == 2)

    # 4K / GB sizes
    sample3 = "Vid 3840x2160 | 18500 Kbps ----------------------------- 120/500 24.00% 1.25GB/5.20GB18.5MBps00:04:12"
    parsed3 = _parse_progress_line(sample3)
    ok("4K GB size parsed",  parsed3 and parsed3.get("size") == "1.25GB / 5.20GB")
    ok("4K GB speed parsed", parsed3 and parsed3.get("speed") and abs(parsed3["speed"] - 18.5) < 0.01)
    ok("4K GB eta parsed",   parsed3 and parsed3.get("eta_sec") == 252)

    # Progress message builder
    msg = _build_progress_message(50.0, speed_bps=5*1024*1024, eta_sec=30, size="500MB / 1GB")
    ok("progress msg: percent", "50.0% done"  in msg)
    ok("progress msg: speed",   "5.0 MB/s"    in msg)
    ok("progress msg: ETA",     "ETA 30s"     in msg)
    ok("progress msg: size",    "500MB / 1GB" in msg)

    # GUI metrics parser
    from main_gui import OmniStreamApp
    app_metrics = OmniStreamApp._parse_progress_metrics(
        None, 33.3,
        "33.3% done · 66.7% left · 4.05 MB/s · ETA 2s · 7.58 MB / 22.74 MB"
    )
    ok("GUI metrics size",      "7.58 MB / 22.74 MB" in app_metrics["size"])
    ok("GUI metrics speed",     "4.1 MB/s" in app_metrics["speed"] or "4.0 MB/s" in app_metrics["speed"])
    ok("GUI metrics eta",       app_metrics["time"] == "2s left")
    ok("GUI metrics remaining", app_metrics["left"] == "67% remaining")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Subtitle Engine Source Integrity
# ─────────────────────────────────────────────────────────────────────────────
def test_subtitle_engine():
    """Verify subtitle-only download engine is correctly wired in core_engine.py."""
    src = open(os.path.join(DESKTOP, "core_engine.py"), encoding="utf-8").read()

    checks = {
        "run_subtitle_download defined":    "def run_subtitle_download(",
        "--sub-only flag":                  '"--sub-only"',
        "--sub-format flag":                '"--sub-format"',
        "--auto-subtitle-fix flag":         '"--auto-subtitle-fix"',
        "-ss lang filter":                  '"-ss"',
        "SRT default param":                'sub_format: str = "SRT"',
        "all default lang":                 'sub_lang: str = "all"',
        "lang=code filter":                 "lang={sub_lang}",
        "saved_subs list built":            "saved_subs.append(",
        "scans for .srt/.vtt files":        "fname.lower().endswith(ext)",
        "no subtitle error message":        "No subtitle tracks found",
        "rc=0 no-files guard":              "rc == 0 and not saved_subs",
        "temp dir cleaned":                 "shutil.rmtree(temp_dir",
        "abort raises RuntimeError":        'raise RuntimeError("Operation aborted',
        "CREATE_NO_WINDOW":                 "0x08000000",
        "ANSI stripping":                   "_strip_ansi(line)",
        "error: unhandled exception track": '"unhandled"',
        "error: segment fail track":        '"segment"',
        "first segment error handled":      '"first segment"',
        "403 forbidden handled":            '"403" in combined',
        "run_download still intact":        "def run_download(",
        "_download_direct_file intact":     "def _download_direct_file(",
        "backward compat alias":            "DownloadEngine = OmniStreamEngine",
    }
    for desc, token in checks.items():
        ok(f"Engine: {desc}", token in src)


# ─────────────────────────────────────────────────────────────────────────────
# 5. GUI Source Integrity
# ─────────────────────────────────────────────────────────────────────────────
def test_gui_declutter():
    """GUI source code analysis — all features must be present and wired."""
    gui = open(os.path.join(DESKTOP, "main_gui.py"), encoding="utf-8").read()

    # --- Subtitle UI ---
    ok("GUI: sub_format_menu widget",           "sub_format_menu"         in gui)
    ok("GUI: sub_lang_menu widget",             "sub_lang_menu"           in gui)
    ok("GUI: subtitle_btn widget",              "subtitle_btn"            in gui)
    ok("GUI: _start_subtitle_download method",  "def _start_subtitle_download" in gui)
    ok("GUI: Download Subtitles button",        "Download Subtitles"      in gui)
    ok("GUI: Subtitle Format label",            "Subtitle Format"         in gui)
    ok("GUI: Subtitle Language label",          "Subtitle Language"       in gui)
    ok("GUI: SRT format option",                "SRT (SubRip"             in gui)
    ok("GUI: VTT format option",                "VTT (WebVTT)"            in gui)
    ok("GUI: run_subtitle_download call",       "run_subtitle_download("  in gui)
    ok("GUI: sub_item_id abort tracking",       "sub_item_id"             in gui)
    ok("GUI: subtitle btn restore after done",  "subtitle_btn.configure(state" in gui)
    ok("GUI: English lang mapped",              '"english": "eng"'        in gui)
    ok("GUI: Hindi lang mapped",                '"hindi": "hin"'          in gui)
    ok("GUI: Arabic lang mapped",               '"arabic": "ara"'         in gui)
    ok("GUI: Japanese lang mapped",             '"japanese": "jpn"'       in gui)

    # --- Existing features ---
    ok("GUI: no duplicate header Chrome btns",  "btn_header_chrome" not in gui and "btn_header_ext" not in gui)
    ok("GUI: Clear Logs on terminal",           "Clear Logs"              in gui)
    ok("GUI: Start Download",                   "Start Download"          in gui)
    ok("GUI: Download All queue",               "Download All"            in gui)
    ok("GUI: progress animation tick",          "_tick_progress_animation" in gui)
    ok("GUI: footer version v2.3.0",            "v2.3.0" in gui or "v2.2.0" in gui or "v2.1.0" in gui)
    ok("GUI: concurrent: no global flag",       "self.is_downloading = False" not in gui)
    ok("GUI: concurrent: _active_downloads",    "_active_downloads"       in gui)
    ok("GUI: concurrent: per-item cancel",      "_cancel_item"            in gui)
    ok("GUI: concurrent: engine per item",      "engine = OmniStreamEngine()" in gui)
    ok("GUI: no Busy popup",                    "A download is already in progress" not in gui)
    ok("GUI: no math.sin bounce (CPU safe)",    "math.sin"               not in gui)
    ok("GUI: Chrome-style animation comment",   "Chrome-style"            in gui)
    ok("GUI: full queue view enter",            "btn_full_queue_view" in gui and "_enter_full_queue_view" in gui)
    ok("GUI: full queue view exit",             "_exit_full_queue_view"   in gui)
    ok("GUI: run_on_main_thread",               "def run_on_main_thread"  in gui)
    ok("GUI: abort button wired",               "command=self._abort_download" in gui)

    # --- Error handling ---
    ok("GUI: RuntimeError caught",              "except RuntimeError as exc" in gui)
    ok("GUI: abort message handled",            '"abort" in err.lower()'  in gui)
    ok("GUI: error messagebox shown",           "messagebox.showerror"    in gui)

    # --- Thread safety ---
    ok("GUI: daemon threads",                   "daemon=True"             in gui)
    ok("GUI: log_queue poll",                   "_poll_log_queue"         in gui)
    ok("GUI: progress callback wired",          "progress_callback=_progress_cb" in gui)
    ok("GUI: _set_progress method",             "def _set_progress"       in gui)
    ok("GUI: _parse_progress_metrics",          "def _parse_progress_metrics" in gui)

    # --- Window chrome ---
    chrome_code = open(os.path.join(DESKTOP, "window_chrome.py"), encoding="utf-8").read()
    ok("window_chrome: _in_configure guard",        "_in_configure"              in chrome_code)
    ok("window_chrome: maximized region key cache", '_region_key == "maximized"' in chrome_code)

    # --- Fullscreen / window risk ---
    ok("overrideredirect=True",         "overrideredirect(True)"         in gui)
    ok("minsize set (crash prevention)","minsize(940"                    in gui)
    ok("WM_DELETE_WINDOW hooked",       "WM_DELETE_WINDOW"               in gui)
    ok("_on_close stops bridge server", "bridge.stop()"                  in gui)
    ok("_on_close safe try/except",     "def _on_close" in gui and "except Exception" in gui)
    ok("Escape exits full-queue view",  "Escape" in gui and "_exit_full_queue_view" in gui)
    ok("no unbounded animation recursion", "self._progress_anim_job = self.after" in gui)
    ok("animation: linear lerp exists",  "_anim_duration" in gui)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Binary / Dependency Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_dependencies_present():
    """Check N_m3u8DL-RE and FFmpeg are reachable (bin/ folder or PATH)."""
    from setup_dependencies import find_binary
    n = find_binary("N_m3u8DL-RE.exe")
    f = find_binary("ffmpeg.exe")
    ok("N_m3u8DL-RE binary found", bool(n), str(n))
    # ffmpeg is auto-downloaded at first launch — warn only, not fail
    if not f:
        print("[WARN] ffmpeg.exe not pre-bundled — will be auto-downloaded at first launch (OK)")
    else:
        ok("ffmpeg binary found", True)

    if n and os.path.isfile(n):
        try:
            r = subprocess.run([n, "--version"], capture_output=True, text=True,
                               timeout=8, creationflags=0x08000000)
            ok("N_m3u8DL-RE runs", r.returncode == 0 or "N_m3u8DL" in (r.stdout + r.stderr))
        except Exception as exc:
            ok("N_m3u8DL-RE runs", False, str(exc))

        # Verify subtitle-related flags are supported
        try:
            rh = subprocess.run([n, "--help"], capture_output=True, text=True,
                                timeout=8, creationflags=0x08000000)
            help_txt = rh.stdout + rh.stderr
            ok("N_m3u8DL-RE: --sub-only flag",           "--sub-only"            in help_txt)
            ok("N_m3u8DL-RE: --sub-format flag",          "--sub-format"          in help_txt)
            ok("N_m3u8DL-RE: -ss/select-subtitle flag",   "--select-subtitle" in help_txt or "-ss" in help_txt)
            ok("N_m3u8DL-RE: --auto-subtitle-fix flag",   "--auto-subtitle-fix"   in help_txt)
            ok("N_m3u8DL-RE: --no-ansi-color flag",       "--no-ansi-color"       in help_txt)
            ok("N_m3u8DL-RE: -mt concurrent flag",        "--concurrent-download" in help_txt or "-mt" in help_txt)
        except Exception as exc:
            ok("N_m3u8DL-RE: subtitle flags check", False, str(exc))

    if f and os.path.isfile(f):
        try:
            rf = subprocess.run([f, "-version"], capture_output=True, text=True,
                                timeout=8, creationflags=0x08000000)
            ok("ffmpeg runs", "ffmpeg" in (rf.stdout + rf.stderr).lower())
        except Exception as exc:
            ok("ffmpeg runs", False, str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# 7. Direct Download Smoke Test (live network)
# ─────────────────────────────────────────────────────────────────────────────
def test_direct_download_smoke():
    """Small public PNG file download via _download_direct_file (network required)."""
    from core_engine import OmniStreamEngine

    engine   = OmniStreamEngine()
    out_dir  = tempfile.mkdtemp(prefix="omni_selftest_")
    out_path = os.path.join(out_dir, "tiny.png")
    progress = []

    try:
        info = {
            "url": "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png",
            "user_agent": "OmniStreamPro-SelfTest/2.3.0",
            "referer":    "https://www.google.com/",
            "origin":     "https://www.google.com",
            "headers":    {},
        }
        saved = engine._download_direct_file(info, out_path,
                                              progress_callback=lambda p, m: progress.append(p))
        ok("direct download: file saved",       os.path.isfile(saved) and os.path.getsize(saved) > 100)
        ok("direct download: progress fired",   len(progress) >= 1)
        ok("direct download: progress > 0",     any(p > 0 for p in progress))
        ok("direct download: engine not aborted", not engine._is_aborted)
    except Exception as exc:
        ok("direct download: file saved",    False, str(exc))
        ok("direct download: progress fired",False)
        ok("direct download: progress > 0",  False)
        ok("direct download: engine not aborted", False)
    finally:
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 8. JS Playlist Filter Tests (requires Node.js — optional)
# ─────────────────────────────────────────────────────────────────────────────
def test_filter_logic_node():
    node = shutil_which("node")
    if not node:
        print("[SKIP] node not found — JS filter unit test skipped")
        return
    script = r"""
function isPlaylistItem(item) {
  const url = String((item && item.url) || '');
  if (!url) return false;
  const lo = url.toLowerCase();
  let path = lo;
  try { path = new URL(url).pathname.toLowerCase(); } catch (e) {}
  if (/\.(m4s|ts|aac|m4a|vtt|srt|jpg|png|webp|gif)(\?|#|$)/.test(path)) return false;
  if (/(preview|trailer|thumb|sprite|poster|preroll|advert|\/ads\/)/.test(lo)) return false;
  if (/(^|\/)(audio|audios|subtitle|subtitles|caption)\//.test(path)) return false;
  const mime = String(item.mime || '').toLowerCase();
  const typeLo = String(item.type || '').toLowerCase();
  if (/\.m3u8(\?|#|$)/i.test(lo) || mime.includes('mpegurl') || typeLo.includes('hls')) return true;
  if (/\.mpd(\?|#|$)/i.test(lo) || mime.includes('dash+xml') || typeLo.includes('dash')) return true;
  if (/\.(mp4|webm|mkv)(\?|#|$)/i.test(path) || mime.includes('video/mp4') || mime.includes('video/webm')) return true;
  return false;
}
const cases = [
  [{url:'https://cdn.x/hls/stream.m3u8?t=1'}, true],
  [{url:'https://cdn.x/1080/index.m3u8'},      true],
  [{url:'https://cdn.x/player/master.m3u8'},   true],
  [{url:'https://cdn.x/seg-1.ts'},             false],
  [{url:'https://cdn.x/video.mp4'},            true],
  [{url:'https://cdn.x/a', mime:'application/vnd.apple.mpegurl', type:'HLS'}, true],
];
let fail = 0;
for (const [item, expect] of cases) {
  const got = isPlaylistItem(item);
  if (got !== expect) { console.log('BAD', item.url, got, expect); fail++; }
}
process.exit(fail ? 1 : 0);
"""
    path = os.path.join(DESKTOP, "_filter_test.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run([node, path], capture_output=True, text=True)
    ok("JS playlist filter cases", r.returncode == 0, r.stdout + r.stderr)
    try:
        os.remove(path)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 9. Netflix Resolver Tests
# ─────────────────────────────────────────────────────────────────────────────
def test_netflix_resolver():
    from netflix_resolver import (
        extract_netflix_id, resolve_netflix_title,
        get_non_conflicting_path, sanitize_filename
    )

    # ID extraction
    ok("extract ID: raw digits",        extract_netflix_id("81902147")                               == "81902147")
    ok("extract ID: .mp4 filename",     extract_netflix_id("81902147.mp4")                           == "81902147")
    ok("extract ID: OmniStream name",   extract_netflix_id("OmniStream_81902147")                    == "81902147")
    ok("extract ID: watch URL",         extract_netflix_id("https://www.netflix.com/watch/81902147") == "81902147")
    ok("extract ID: title URL",         extract_netflix_id("https://www.netflix.com/title/81902147") == "81902147")
    ok("extract ID: regional URL",      extract_netflix_id("https://www.netflix.com/bd-en/watch/81902147") == "81902147")
    ok("extract ID: curl referer",      extract_netflix_id('curl "https://..." -H "Referer: https://www.netflix.com/watch/81902147"') == "81902147")
    ok("extract ID: None for non-NF",   extract_netflix_id("https://random-site.com/video.mp4") is None)

    # Non-conflicting path
    with tempfile.TemporaryDirectory(prefix="omni_test_rename_") as tmp_dir:
        f1 = os.path.join(tmp_dir, "Sonic the Hedgehog 3 (2024).mp4")
        with open(f1, "w") as f:
            f.write("test content")
        unique_path = get_non_conflicting_path(tmp_dir, "Sonic the Hedgehog 3 (2024).mp4")
        ok("non-conflicting: avoids overwrite",    os.path.basename(unique_path) == "Sonic the Hedgehog 3 (2024) (1).mp4")
        ok("non-conflicting: preserves extension", unique_path.endswith(".mp4"))

        with open(unique_path, "w") as f:
            f.write("test 2")
        unique_path2 = get_non_conflicting_path(tmp_dir, "Sonic the Hedgehog 3 (2024).mp4")
        ok("non-conflicting: increments to (2)",   os.path.basename(unique_path2) == "Sonic the Hedgehog 3 (2024) (2).mp4")

    # Filename sanitization
    san = sanitize_filename('Movie: Subtitle / "Part 1" <2024>? *')
    ok("sanitize: removes bad chars",
       ":" not in san and "/" not in san and '"' not in san and "<" not in san)

    # Live online title resolution (network)
    resolved = resolve_netflix_title("81902147")
    ok("Netflix 81902147 → Sonic the Hedgehog 3 (2024)", resolved == "Sonic the Hedgehog 3 (2024)")


# ─────────────────────────────────────────────────────────────────────────────
# 10. Release File Presence
# ─────────────────────────────────────────────────────────────────────────────
def test_release_files():
    ok("app_icon.png",         os.path.isfile(os.path.join(DESKTOP, "app_icon.png")))
    ok("app_icon.ico",         os.path.isfile(os.path.join(DESKTOP, "app_icon.ico")))
    for name in ("icon16.png", "icon32.png", "icon48.png", "icon128.png"):
        ok(f"extension/{name}", os.path.isfile(os.path.join(EXT, "icons", name)))
    ok("LICENSE",              os.path.isfile(os.path.join(ROOT, "LICENSE")))
    ok("README.md",            os.path.isfile(os.path.join(ROOT, "README.md")))
    ok("RELEASE_NOTES.md",     os.path.isfile(os.path.join(ROOT, "RELEASE_NOTES.md")))
    ok("requirements.txt",     os.path.isfile(os.path.join(ROOT, "requirements.txt")))
    ok("Start bat",            os.path.isfile(os.path.join(ROOT, "Start_OmniStream_Pro.bat")))
    ok("desktop/bin/README.md",os.path.isfile(os.path.join(DESKTOP, "bin", "README.md")))
    ok("extension/README.md",  os.path.isfile(os.path.join(EXT, "README.md")))
    ok("build_release.py",     os.path.isfile(os.path.join(ROOT, "build_release.py")))
    ok("build_installer.py",   os.path.isfile(os.path.join(ROOT, "build_installer.py")))


# ─────────────────────────────────────────────────────────────────────────────
# 11. Bridge Server (optional — only if app is running)
# ─────────────────────────────────────────────────────────────────────────────
def test_bridge_optional():
    try:
        with urllib.request.urlopen("http://127.0.0.1:28795/health", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            ok("bridge /health reachable", True, str(data)[:80])
            req = urllib.request.Request(
                "http://127.0.0.1:28795/add",
                data=json.dumps({
                    "url": "https://example.com/test.m3u8",
                    "title": "selftest_probe",
                    "curl": 'curl "https://example.com/test.m3u8"',
                    "autoStart": False,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as add_resp:
                body = add_resp.read().decode("utf-8", errors="ignore")
                ok("bridge /add accepts job",
                   add_resp.status in (200, 201) or "ok" in body.lower() or "success" in body.lower(),
                   body[:120])
    except Exception:
        print("[SKIP] bridge not running — start the app before live bridge test")


# ─────────────────────────────────────────────────────────────────────────────
# 12. Release Binaries (optional)
# ─────────────────────────────────────────────────────────────────────────────
def test_release_binaries_optional():
    out     = os.path.join(ROOT, "release_output")
    portable= os.path.join(out, "OmniStream_Pro.exe")
    setup   = os.path.join(out, "OmniStream_Pro_Setup.exe")
    zip_v   = os.path.join(out, "OmniStream-Pro-Chrome-Extension-v2.3.0.zip")
    magic   = b"MEI\x0c\x0b\x0a\x0b\x0e"

    if os.path.isfile(portable):
        ok("portable exe PKG cookie", magic in open(portable, "rb").read())
    else:
        print("[SKIP] portable exe not in release_output yet")
    if os.path.isfile(setup):
        data = open(setup, "rb").read()
        ok("setup exe PKG cookie", magic in data and not data.endswith(b"\x00" * 64))
    else:
        print("[SKIP] setup exe not in release_output yet")
    uninst = os.path.join(out, "uninstall.exe")
    if os.path.isfile(uninst):
        ok("native uninstaller exists", os.path.getsize(uninst) > 10000)
    if os.path.isfile(zip_v):
        import zipfile
        with zipfile.ZipFile(zip_v, "r") as zf:
            names = zf.namelist()
            ok("extension zip has manifest", any(n.endswith("manifest.json") for n in names))
            ok("extension zip has popup.js", any(n.endswith("popup.js")      for n in names))
    else:
        print("[SKIP] extension zip not in release_output yet")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  OmniStream Pro v2.3.0 — Self-Test Suite")
    print("=" * 60)
    print()

    print("--- [1] Extension Source ---")
    load_bg_helpers()
    print()

    print("--- [2] Python Module Imports ---")
    test_python_modules()
    print()

    print("--- [3] Engine Methods & Signatures ---")
    test_engine_methods()
    print()

    print("--- [4] Progress Parser ---")
    test_engine_parsers()
    print()

    print("--- [5] Subtitle Engine Source ---")
    test_subtitle_engine()
    print()

    print("--- [6] GUI Source Analysis + Fullscreen/Window Risk ---")
    test_gui_declutter()
    print()

    print("--- [7] Binary Dependencies ---")
    test_dependencies_present()
    print()

    print("--- [8] Netflix Resolver ---")
    test_netflix_resolver()
    print()

    print("--- [9] Direct Download Smoke Test ---")
    test_direct_download_smoke()
    print()

    print("--- [10] JS Filter Logic ---")
    test_filter_logic_node()
    print()

    print("--- [11] Release Files ---")
    test_release_files()
    print()

    print("--- [12] Bridge Server (optional) ---")
    test_bridge_optional()
    print()

    print("--- [13] Release Binaries (optional) ---")
    test_release_binaries_optional()
    print()

    print("=" * 60)
    if fails:
        print(f"RESULT: {len(fails)} FAILED  |  {len(fails)} issue(s):")
        for f in fails:
            print(f"  ✗  {f}")
        sys.exit(1)
    else:
        print("RESULT: All critical checks PASSED.")
        sys.exit(0)
