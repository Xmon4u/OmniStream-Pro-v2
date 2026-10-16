"""Offline verification for publish readiness. No Chrome restart / no git push."""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(ROOT, "extension")
fails = []


def ok(name, cond, detail=""):
    if cond:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} {detail}")
        fails.append(name)


def shutil_which(name):
    import shutil
    return shutil.which(name)


def load_bg_helpers():
    bg = open(os.path.join(EXT, "background.js"), encoding="utf-8").read()
    popup_js = open(os.path.join(EXT, "popup.js"), encoding="utf-8").read()
    popup_html = open(os.path.join(EXT, "popup.html"), encoding="utf-8").read()
    ok("background has onBeforeRequest", "onBeforeRequest" in bg)
    ok("background has isPlaylistItem", "isPlaylistItem" in bg)
    ok("background has selectPlayerStreams", "selectPlayerStreams" in bg)
    ok("no score < 8 hard gate", "score < 8" not in bg)
    ok("no multi-language-only toast", "No multi-language" not in popup_js)
    ok("popup has God Mode button", "godScanBtn" in popup_html)
    ok("popup has Download wiring", "SEND_TO_OMNISTREAM" in popup_js or "Download" in popup_js)
    ok("popup has no Clear button", "clearDetectedBtn" not in popup_html)
    man = json.load(open(os.path.join(EXT, "manifest.json"), encoding="utf-8"))
    ok("manifest version", man.get("version") in ("2.0.2", "2.1.0"))
    ok("manifest webRequest", "webRequest" in man.get("permissions", []))
    ok("manifest host localhost", any("127.0.0.1" in h for h in man.get("host_permissions", [])))
    ok("godmode FORCE_SCAN", "FORCE_SCAN" in open(os.path.join(EXT, "godmode.js"), encoding="utf-8").read())
    ok("content injects godmode", "godmode.js" in open(os.path.join(EXT, "content.js"), encoding="utf-8").read())


def test_python_modules():
    sys.path.insert(0, DESKTOP)
    for mod in ("window_chrome", "ui_icons", "extension_manager", "bridge_server", "core_engine", "setup_dependencies"):
        try:
            __import__(mod)
            ok(f"import {mod}", True)
        except Exception as exc:
            ok(f"import {mod}", False, str(exc))


def test_engine_parsers():
    sys.path.insert(0, DESKTOP)
    from core_engine import OmniStreamEngine, _parse_progress_line, _build_progress_message

    info = OmniStreamEngine.parse_input(
        'curl "https://cdn.example.com/play/master.m3u8?tok=1" '
        '-H "Referer: https://site.example/" -H "User-Agent: TestUA/1.0" '
        '-H "Cookie: a=b"'
    )
    ok("curl parse url", "master.m3u8" in info.get("url", ""))
    ok("curl parse referer", "site.example" in info.get("referer", ""))
    ok("curl parse cookie", "cookie" in info.get("headers", {}))

    direct = OmniStreamEngine.parse_input("https://cdn.example.com/v/clip.mp4")
    ok("direct url parse", direct.get("url", "").endswith(".mp4"))

    sample = "Vid 1080P | 120/400 | 30.00% | 8.5MBps | 00:01:12"
    parsed = _parse_progress_line(sample)
    ok("progress parse pct", parsed and abs(parsed["pct"] - 30.0) < 0.01)
    ok("progress parse speed", parsed and parsed.get("speed") and abs(parsed["speed"] - 8.5) < 0.01)
    ok("progress parse eta", parsed and parsed.get("eta_sec") == 72)
    msg = _build_progress_message(30.0, 8.5, 72)
    ok("progress message shape", "% done" in msg and "% left" in msg and "left" in msg)


def test_dependencies_present():
    sys.path.insert(0, DESKTOP)
    from setup_dependencies import find_binary
    n = find_binary("N_m3u8DL-RE.exe")
    f = find_binary("ffmpeg.exe")
    ok("N_m3u8DL-RE binary found", bool(n), str(n))
    ok("ffmpeg binary found", bool(f), str(f))
    if n and os.path.isfile(n):
        try:
            r = subprocess.run([n, "--version"], capture_output=True, text=True, timeout=8)
            ok("N_m3u8DL-RE runs", r.returncode == 0 or "N_m3u8DL" in (r.stdout + r.stderr))
        except Exception as exc:
            ok("N_m3u8DL-RE runs", False, str(exc))
    if f and os.path.isfile(f):
        try:
            r = subprocess.run([f, "-version"], capture_output=True, text=True, timeout=8)
            ok("ffmpeg runs", r.returncode == 0 and "ffmpeg" in (r.stdout + r.stderr).lower())
        except Exception as exc:
            ok("ffmpeg runs", False, str(exc))


def test_direct_download_smoke():
    """Tiny public file download through engine helper (network)."""
    sys.path.insert(0, DESKTOP)
    from core_engine import OmniStreamEngine

    engine = OmniStreamEngine()
    out_dir = tempfile.mkdtemp(prefix="omni_selftest_")
    out_path = os.path.join(out_dir, "tiny.bin")
    progress = []

    def on_prog(pct, msg):
        progress.append((pct, msg))

    try:
        # 1x1 PNG from a stable public host
        info = {
            "url": "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png",
            "user_agent": "OmniStreamPro-SelfTest/2.0.2",
            "referer": "https://www.google.com/",
            "origin": "https://www.google.com",
            "headers": {},
        }
        saved = engine._download_direct_file(info, out_path, progress_callback=on_prog)
        ok("direct download saved", os.path.isfile(saved) and os.path.getsize(saved) > 100)
        ok("direct download progress fired", len(progress) >= 1)
    except Exception as exc:
        ok("direct download saved", False, str(exc))
        ok("direct download progress fired", False, str(exc))
    finally:
        try:
            if os.path.isfile(out_path):
                os.remove(out_path)
            os.rmdir(out_dir)
        except Exception:
            pass


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
  [{url:'https://cdn.x/1080/index.m3u8'}, true],
  [{url:'https://cdn.x/player/master.m3u8'}, true],
  [{url:'https://cdn.x/seg-1.ts'}, false],
  [{url:'https://cdn.x/video.mp4'}, true],
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


def test_gui_declutter():
    gui = open(os.path.join(DESKTOP, "main_gui.py"), encoding="utf-8").read()
    ok("no duplicate header Chrome buttons", "btn_header_chrome" not in gui and "btn_header_ext" not in gui)
    ok("has Clear Logs on terminal", "Clear Logs" in gui)
    ok("has Start Download", "Start Download" in gui)
    ok("has Download All", "Download All" in gui)
    ok("progress animation tick", "_tick_progress_animation" in gui)
    ok("footer version", "v2.1.0" in gui or "v2.0.2" in gui)


def test_release_files():
    ok("app_icon.png", os.path.isfile(os.path.join(DESKTOP, "app_icon.png")))
    ok("app_icon.ico", os.path.isfile(os.path.join(DESKTOP, "app_icon.ico")))
    for name in ("icon16.png", "icon32.png", "icon48.png", "icon128.png"):
        ok(f"extension/{name}", os.path.isfile(os.path.join(EXT, "icons", name)))
    ok("LICENSE", os.path.isfile(os.path.join(ROOT, "LICENSE")))
    ok("README.md", os.path.isfile(os.path.join(ROOT, "README.md")))
    ok("RELEASE_NOTES.md", os.path.isfile(os.path.join(ROOT, "RELEASE_NOTES.md")))
    ok("requirements.txt", os.path.isfile(os.path.join(ROOT, "requirements.txt")))
    ok("Start bat", os.path.isfile(os.path.join(ROOT, "Start_OmniStream_Pro.bat")))
    ok("desktop/bin/README.md", os.path.isfile(os.path.join(DESKTOP, "bin", "README.md")))
    ok("extension/README.md", os.path.isfile(os.path.join(EXT, "README.md")))
    ok("build_release.py", os.path.isfile(os.path.join(ROOT, "build_release.py")))
    ok("build_installer.py", os.path.isfile(os.path.join(ROOT, "build_installer.py")))


def test_bridge_optional():
    try:
        with urllib.request.urlopen("http://127.0.0.1:28795/health", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            ok("bridge /health reachable", True, str(data)[:80])
            # Exercise /add endpoint shape (should accept JSON without crashing)
            req = urllib.request.Request(
                "http://127.0.0.1:28795/add",
                data=json.dumps({
                    "url": "https://example.com/test.m3u8",
                    "title": "selftest_probe",
                    "curl": "curl \"https://example.com/test.m3u8\"",
                    "autoStart": False,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as add_resp:
                body = add_resp.read().decode("utf-8", errors="ignore")
                ok("bridge /add accepts job", add_resp.status in (200, 201) or "ok" in body.lower() or "success" in body.lower(), body[:120])
    except Exception:
        print("[SKIP] bridge not running (start the app before live bridge test)")


def test_release_binaries_optional():
    out = os.path.join(ROOT, "release_output")
    portable = os.path.join(out, "OmniStream_Pro.exe")
    setup = os.path.join(out, "OmniStream_Pro_Setup.exe")
    zip_v210 = os.path.join(out, "OmniStream-Pro-Chrome-Extension-v2.1.0.zip")
    zip_v202 = os.path.join(out, "OmniStream-Pro-Chrome-Extension-v2.0.2.zip")
    zip_path = zip_v210 if os.path.isfile(zip_v210) else zip_v202
    magic = b"MEI\x0c\x0b\x0a\x0b\x0e"
    if os.path.isfile(portable):
        data = open(portable, "rb").read()
        ok("portable exe PKG cookie", magic in data)
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
    if os.path.isfile(zip_path):
        import zipfile
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            ok("extension zip has manifest", any(n.endswith("manifest.json") for n in names))
            ok("extension zip has popup.js", any(n.endswith("popup.js") for n in names))
    else:
        print("[SKIP] extension zip not in release_output yet")


if __name__ == "__main__":
    print("OmniStream Pro self-test (extension + downloader)")
    load_bg_helpers()
    test_python_modules()
    test_engine_parsers()
    test_dependencies_present()
    test_direct_download_smoke()
    test_filter_logic_node()
    test_gui_declutter()
    test_release_files()
    test_bridge_optional()
    test_release_binaries_optional()
    print("---")
    if fails:
        print(f"{len(fails)} failed: {fails}")
        sys.exit(1)
    print("All critical checks passed.")
    sys.exit(0)
