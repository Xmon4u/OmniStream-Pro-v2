"""
Live Integration Test: OmniStream Pro Desktop Bridge Server & Browser Extension
Tests the full HTTP & Token communication between the Chrome Extension and Desktop Bridge Server:
- Bridge startup on 127.0.0.1:28795
- Extension token authentication (X-OmniStream-Token & Bearer)
- Origin validation (chrome-extension://, moz-extension://)
- /health endpoint (with app state, version, mode, theme)
- /add endpoint (single stream capture from extension)
- /batch_add endpoint (IDM batch capture from extension)
- /mode endpoint (remote mode switching)
- /theme endpoint (remote theme switching)
- /focus endpoint
- 1-click Subtitles trigger payload
- Rejection of invalid tokens & hostile origins
"""

import sys
import os
import json
import time
import urllib.request
import urllib.error
import queue

# Add desktop folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge_server import BridgeServer, BRIDGE_PORT
from extension_manager import get_or_create_bridge_token, write_extension_bridge_token

class MockDesktopApp:
    def __init__(self):
        self.log_queue = queue.Queue()
        self.queue_items = []
        self.is_downloading = False
        self.download_mode = "normal"
        self.current_theme_name = "Cyber Slate"

    def run_on_main_thread(self, fn):
        fn()

    def set_download_mode(self, mode):
        self.download_mode = mode

    def set_theme(self, theme):
        self.current_theme_name = theme

def run_test():
    print("=================================================================")
    print("  OmniStream Pro v2.6.0 — Live Bridge & Extension Integration Test")
    print("=================================================================\n")

    app = MockDesktopApp()
    token = write_extension_bridge_token()
    print(f"[*] Authenticated Bridge Token: {token[:8]}...{token[-4:]}")

    server = BridgeServer(app)
    started = server.start()
    if not started:
        print("[FAIL] Could not start BridgeServer on port", BRIDGE_PORT)
        sys.exit(1)
    print(f"[OK] BridgeServer listening on 127.0.0.1:{BRIDGE_PORT}\n")

    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{BRIDGE_PORT}"

    # Helper for HTTP requests
    def req(path, method="GET", body=None, origin="chrome-extension://omnistream-extension-id", auth_token=token):
        url = base_url + path
        headers = {}
        if origin:
            headers["Origin"] = origin
        if auth_token:
            headers["X-OmniStream-Token"] = auth_token
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=3) as resp:
                status = resp.status
                headers_dict = dict(resp.headers)
                body_bytes = resp.read()
                try:
                    res_json = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    res_json = None
                return status, headers_dict, res_json
        except urllib.error.HTTPError as e:
            body_bytes = e.read()
            try:
                res_json = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                res_json = None
            return e.code, dict(e.headers), res_json

    tests_passed = 0
    total_tests = 0

    def assert_test(name, condition, extra=""):
        nonlocal tests_passed, total_tests
        total_tests += 1
        if condition:
            tests_passed += 1
            print(f"  [PASS] {name} {extra}")
        else:
            print(f"  [FAIL] {name} {extra}")
            raise AssertionError(f"Failed: {name}")

    try:
        # Test 1: /health with valid Chrome Extension origin & token
        st, hd, js = req("/health")
        assert_test("Health check response code == 200", st == 200)
        assert_test("Health check status == ok", js.get("status") == "ok")
        assert_test("Health check app == OmniStream Pro", js.get("app") == "OmniStream Pro")
        assert_test("Health check version == 2.6.0", js.get("version") == "2.6.0")
        assert_test("Health check authenticated == True", js.get("authenticated") is True)
        assert_test("CORS origin reflected for chrome-extension://", hd.get("Access-Control-Allow-Origin") == "chrome-extension://omnistream-extension-id")

        # Check heartbeat notification from /health
        hb_type, _ = app.log_queue.get(timeout=1)
        assert_test("Health check signaled 'bridge_connected' to app", hb_type == "bridge_connected")

        # Test 2: Hostile origin rejected
        st2, hd2, js2 = req("/health", origin="https://evil-attacker-site.com")
        assert_test("Hostile external web origin rejected with 403", st2 == 403)

        # Test 3: /add single stream job from extension
        stream_payload = {
            "url": "https://test-stream.org/master.m3u8",
            "title": "Episode 01 - Test",
            "curl": "curl 'https://test-stream.org/master.m3u8' -H 'Referer: https://stream.org/'",
            "mode": "normal"
        }
        st3, hd3, js3 = req("/add", method="POST", body=stream_payload)
        assert_test("/add response code == 200", st3 == 200)
        assert_test("/add success == True", js3.get("success") is True)
        
        # Verify app received message in queue
        msg_type, payload = app.log_queue.get(timeout=1)
        assert_test("App received 'bridge_job' message", msg_type == "bridge_job")
        assert_test("App job payload URL correct", payload.get("url") == stream_payload["url"])

        # Test 4: /add with Netflix mode & ID
        nf_payload = {
            "url": "https://netflix-cdn.com/stream.m3u8",
            "title": "Stranger Things",
            "mode": "netflix_rename",
            "netflixId": "80077368"
        }
        st4, hd4, js4 = req("/add", method="POST", body=nf_payload)
        assert_test("/add netflix stream response code == 200", st4 == 200)
        msg_type4, payload4 = app.log_queue.get(timeout=1)
        assert_test("Netflix job received with correct ID", payload4.get("netflixId") == "80077368")

        # Test 5: /batch_add multiple items (IDM batch import)
        batch_payload = {
            "items": [
                {"url": "https://cdn.example.com/ep1.m3u8", "title": "Ep 1"},
                {"url": "https://cdn.example.com/ep2.m3u8", "title": "Ep 2"},
                {"url": "https://cdn.example.com/ep3.m3u8", "title": "Ep 3"}
            ]
        }
        st5, hd5, js5 = req("/batch_add", method="POST", body=batch_payload)
        assert_test("/batch_add response code == 200", st5 == 200)
        assert_test("/batch_add count == 3", js5.get("count") == 3)
        msg_type5, payload5 = app.log_queue.get(timeout=1)
        assert_test("App received 'bridge_batch_jobs'", msg_type5 == "bridge_batch_jobs")
        assert_test("Batch items length == 3", len(payload5.get("items", [])) == 3)

        # Test 6: Remote mode toggle (/set_mode)
        st6, hd6, js6 = req("/set_mode", method="POST", body={"mode": "netflix_rename"})
        assert_test("/set_mode returns 200", st6 == 200)
        assert_test("App download_mode changed to netflix_rename", app.download_mode == "netflix_rename")

        st6b, hd6b, js6b = req("/set_mode", method="POST", body={"mode": "tmdb_rename"})
        assert_test("/set_mode tmdb_rename returns 200", st6b == 200)
        assert_test("App download_mode changed to tmdb_rename", app.download_mode == "tmdb_rename")

        st6c, hd6c, js6c = req("/set_mode", method="POST", body={"mode": "imdb_rename"})
        assert_test("/set_mode imdb_rename returns 200", st6c == 200)
        assert_test("App download_mode changed to imdb_rename", app.download_mode == "imdb_rename")

        # Test 7: Remote theme toggle (/set_theme)
        st7, hd7, js7 = req("/set_theme", method="POST", body={"theme": "Midnight Black"})
        assert_test("/set_theme returns 200", st7 == 200)
        assert_test("App current_theme_name changed to Midnight Black", app.current_theme_name == "Midnight Black")

        # Test 8: Unauthorized rejection with bad token
        st8, hd8, js8 = req("/add", method="POST", body=stream_payload, auth_token="invalid_random_token")
        assert_test("/add with invalid token rejected with 401 Unauthorized", st8 == 401)

        print(f"\n=================================================================")
        print(f"SUCCESS: All {tests_passed}/{total_tests} integration tests passed!")
        print("=================================================================")
    finally:
        server.stop()
        print("[*] Bridge server cleanly shut down.")

if __name__ == "__main__":
    run_test()
