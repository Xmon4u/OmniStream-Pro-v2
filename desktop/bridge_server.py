"""
OmniStream Pro v2.6.0 - Extension Localhost Bridge Server
Listens on 127.0.0.1:28795 for incoming video stream capture jobs from browser extensions.
Supports single stream addition, batch multi-link imports, and IDM-style queue synchronization.
Author: XMON4U (https://github.com/Xmon4u)
"""

import json
import os
import sys
import time
import logging
import re
import hmac
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Optional

try:
    from extension_manager import (
        note_extension_heartbeat,
        get_or_create_bridge_token,
        write_extension_bridge_token,
    )
except ImportError:
    # Standalone fallback: generate and persist a real token so the bridge
    # still authenticates correctly when extension_manager is unavailable.
    import secrets as _secrets, os as _os

    _FALLBACK_TOKEN_FILE = _os.path.join(
        _os.environ.get("LOCALAPPDATA", _os.path.expanduser("~")),
        "OmniStreamPro", "bridge_token.txt"
    )

    def _load_or_create_token() -> str:
        try:
            _os.makedirs(_os.path.dirname(_FALLBACK_TOKEN_FILE), exist_ok=True)
            if _os.path.isfile(_FALLBACK_TOKEN_FILE):
                with open(_FALLBACK_TOKEN_FILE, "r", encoding="utf-8") as _f:
                    _tok = _f.read().strip()
                    if len(_tok) >= 32:
                        return _tok
        except Exception:
            pass
        _tok = _secrets.token_hex(24)
        try:
            with open(_FALLBACK_TOKEN_FILE, "w", encoding="utf-8") as _f:
                _f.write(_tok)
        except Exception:
            pass
        return _tok

    _FALLBACK_TOKEN = _load_or_create_token()

    def note_extension_heartbeat():
        pass

    def get_or_create_bridge_token() -> str:
        return _FALLBACK_TOKEN

    def write_extension_bridge_token() -> str:
        return _FALLBACK_TOKEN

BRIDGE_PORT = 28795

ALLOWED_ORIGIN_PREFIXES = (
    "chrome-extension://",
    "moz-extension://",
    "extension://",
)

ALLOWED_HOSTS = {
    "127.0.0.1",
    f"127.0.0.1:{BRIDGE_PORT}",
    "localhost",
    f"localhost:{BRIDGE_PORT}",
}


def sanitize_input_title(raw_title: str) -> str:
    """Sanitize title/filename to prevent directory traversal and remove Windows illegal characters."""
    if not raw_title or not isinstance(raw_title, str):
        return ""
    # Strip any directory components / traversal
    clean = raw_title.replace("\\", "/").split("/")[-1]
    # Remove Windows invalid chars
    clean = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", clean).strip()
    clean = clean.lstrip(". ")
    stem = clean.split(".")[0].lower() if clean else ""
    if stem in {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "lpt1", "lpt2", "lpt3"}:
        clean = f"omni_{clean}"
    return clean[:200]


def is_valid_http_url(url: str) -> bool:
    """Ensure URL uses http or https scheme and has a reasonable length."""
    if not url or not isinstance(url, str):
        return False
    u = url.strip()
    return u.startswith(("http://", "https://")) and len(u) <= 8192


class BridgeHandler(BaseHTTPRequestHandler):
    MAX_BODY_SIZE = 1024 * 1024  # 1 MB maximum payload limit

    def log_message(self, format, *args):
        # Suppress standard logging to avoid terminal clutter
        pass

    def _check_host(self) -> bool:
        host = self.headers.get("Host", "").strip().lower()
        return host in ALLOWED_HOSTS

    def _get_allowed_origin(self) -> Optional[str]:
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return None  # Direct local non-browser client (curl, selftest, internal)
        lo = origin.lower()
        for p in ALLOWED_ORIGIN_PREFIXES:
            if lo.startswith(p):
                return origin
        return ""  # Disallowed origin (e.g. web page on the internet)

    def _send_cors_headers(self):
        allowed = self._get_allowed_origin()
        if allowed:
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-OmniStream-Token, X-Requested-With")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _is_authenticated(self) -> bool:
        token = self.headers.get("X-OmniStream-Token", "").strip()
        if not token:
            auth = self.headers.get("Authorization", "").strip()
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        expected = get_or_create_bridge_token()
        if not token or not expected:
            return False
        return hmac.compare_digest(token, expected)

    def do_OPTIONS(self):
        if not self._check_host():
            self.send_response(403)
            self.end_headers()
            return
        origin = self.headers.get("Origin", "").strip()
        if origin and self._get_allowed_origin() == "":
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if not self._check_host():
            self.send_response(403)
            self.end_headers()
            return
        origin = self.headers.get("Origin", "").strip()
        if origin and self._get_allowed_origin() == "":
            self.send_response(403)
            self.end_headers()
            return

        app = getattr(self.server, "app_instance", None)

        if self.path in ("/", "/health"):
            note_extension_heartbeat()
            if app and hasattr(app, "log_queue"):
                app.log_queue.put(("bridge_connected", {}))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()

            queue_len = len(getattr(app, "queue_items", [])) if app else 0
            is_dl_attr = getattr(app, "is_downloading", False) if app else False
            if callable(is_dl_attr):
                try:
                    is_dl = bool(is_dl_attr())
                except Exception:
                    is_dl = False
            else:
                is_dl = bool(is_dl_attr)

            response = {
                "status": "ok",
                "app": "OmniStream Pro",
                "version": "2.6.0",
                "bridge": "active",
                "port": BRIDGE_PORT,
                "authenticated": self._is_authenticated(),
                "queue_count": queue_len,
                "is_downloading": is_dl,
                "mode": getattr(app, "download_mode", "normal"),
                "theme": getattr(app, "current_theme_name", "Cyber Slate") if app else "Cyber Slate"
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/queue":
            if not self._is_authenticated():
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Missing or invalid bridge token"}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()

            items = []
            if app and hasattr(app, "queue_items"):
                items = [
                    {"id": it.get("id"), "title": it.get("title"), "status": it.get("status")}
                    for it in app.queue_items
                ]
            self.wfile.write(json.dumps({"success": True, "queue": items}).encode("utf-8"))

        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        if not self._check_host():
            self.send_response(403)
            self.end_headers()
            return
        origin = self.headers.get("Origin", "").strip()
        if origin and self._get_allowed_origin() == "":
            self.send_response(403)
            self.end_headers()
            return

        app = getattr(self.server, "app_instance", None)
        try:
            content_len = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_len = 0

        if content_len > self.MAX_BODY_SIZE:
            self.send_response(413)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Payload Too Large (max 1MB)"}).encode("utf-8"))
            return

        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            data = json.loads(post_body)
        except Exception:
            data = {}

        # Require bridge token for all modifying and trigger endpoints
        if not self._is_authenticated():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Missing or invalid bridge token"}).encode("utf-8"))
            return

        if self.path == "/add":
            try:
                if not data or not isinstance(data, dict):
                    raise ValueError("No stream data provided in payload.")

                url = str(data.get("url") or "").strip()
                if not is_valid_http_url(url):
                    raise ValueError("Invalid stream URL. Only http:// and https:// URLs are permitted.")

                # Sanitize filename & title against path traversal & Windows illegal characters
                if "title" in data:
                    data["title"] = sanitize_input_title(data["title"])
                if "save_name" in data:
                    data["save_name"] = sanitize_input_title(data["save_name"])

                if app and hasattr(app, "log_queue"):
                    app.log_queue.put(("bridge_job", data))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                response = {
                    "success": True,
                    "message": "Stream added to OmniStream Pro download queue"
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                response = {"success": False, "error": str(e)}
                self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/batch_add":
            try:
                items = data.get("items", [])
                if not isinstance(items, list) or len(items) == 0:
                    raise ValueError("Payload must contain a non-empty 'items' array.")

                # Validate and sanitize all items
                for it in items:
                    if not isinstance(it, dict):
                        raise ValueError("Each item in batch must be an object.")
                    it_url = str(it.get("url") or "").strip()
                    if not is_valid_http_url(it_url):
                        raise ValueError(f"Invalid stream URL in batch: {it_url[:50]}")
                    if "title" in it:
                        it["title"] = sanitize_input_title(it["title"])
                    if "save_name" in it:
                        it["save_name"] = sanitize_input_title(it["save_name"])

                if app and hasattr(app, "log_queue"):
                    app.log_queue.put(("bridge_batch_jobs", data))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                response = {
                    "success": True,
                    "count": len(items),
                    "message": f"Successfully queued {len(items)} streams in OmniStream Pro"
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                response = {"success": False, "error": str(e)}
                self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/start_queue":
            try:
                if app and hasattr(app, "log_queue"):
                    app.log_queue.put(("start_queue_requested", {}))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "message": "Queue download initiated"}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

        elif self.path == "/focus":
            try:
                if app and hasattr(app, "log_queue"):
                    app.log_queue.put(("bring_to_foreground", {}))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "message": "Window focused"}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

        elif self.path in ("/mode", "/set_mode"):
            try:
                raw_mode = str(data.get("mode", "normal")).strip().lower()
                if "tmdb" in raw_mode:
                    new_mode = "tmdb_rename"
                elif "imdb" in raw_mode:
                    new_mode = "imdb_rename"
                elif "netflix" in raw_mode:
                    new_mode = "netflix_rename"
                elif "sub" in raw_mode or "merge" in raw_mode:
                    new_mode = "sub_merge"
                elif "normal" in raw_mode:
                    new_mode = "normal"
                else:
                    raise ValueError(f"Invalid mode '{raw_mode}'. Permitted: normal, netflix_rename, tmdb_rename, imdb_rename, sub_merge")

                if app and hasattr(app, "run_on_main_thread") and hasattr(app, "set_download_mode"):
                    app.run_on_main_thread(lambda: app.set_download_mode(new_mode))
                elif app and hasattr(app, "log_queue"):
                    app.log_queue.put(("set_mode_requested", {"mode": new_mode}))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                curr = getattr(app, "download_mode", new_mode)
                self.wfile.write(json.dumps({"success": True, "mode": curr}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

        elif self.path in ("/theme", "/set_theme"):
            try:
                raw_theme = str(data.get("theme", "Cyber Slate")).strip()
                if raw_theme.lower() in ("midnight black", "black", "midnight"):
                    new_theme = "Midnight Black"
                elif raw_theme.lower() in ("cyber slate", "cyber", "slate", "default"):
                    new_theme = "Cyber Slate"
                else:
                    raise ValueError(f"Invalid theme '{raw_theme}'. Permitted: Cyber Slate, Midnight Black")

                if app and hasattr(app, "run_on_main_thread") and hasattr(app, "set_theme"):
                    app.run_on_main_thread(lambda: app.set_theme(new_theme))
                elif app and hasattr(app, "log_queue"):
                    app.log_queue.put(("set_theme_requested", {"theme": new_theme}))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                curr_th = getattr(app, "current_theme_name", new_theme)
                self.wfile.write(json.dumps({"success": True, "theme": curr_th}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()



class ExclusiveHTTPServer(HTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        import sys, socket
        if sys.platform == "win32":
            try:
                # SO_EXCLUSIVEADDRUSE prevents other zombie processes from sharing or stealing the port on Windows
                self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
            except Exception:
                pass
        super().server_bind()


class BridgeServer:
    def __init__(self, app_instance, port: int = BRIDGE_PORT):
        self.app_instance = app_instance
        self.port = port
        self.httpd: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self):
        # Always proactively clear any orphaned/stale processes on port 28795
        self._free_port_if_needed()
        for attempt in range(2):
            try:
                self.httpd = ExclusiveHTTPServer(("127.0.0.1", self.port), BridgeHandler)
                self.httpd.app_instance = self.app_instance
                self.is_running = True
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
                return True
            except OSError:
                if attempt == 0:
                    self._free_port_if_needed()
                    time.sleep(0.3)
                else:
                    self.is_running = False
                    return False
        return False

    def _free_port_if_needed(self):
        """If an orphaned process is holding port 28795, terminate it so new instance can bind."""
        if sys.platform != "win32":
            return
        try:
            import subprocess, os
            my_pid = os.getpid()
            creationflags = 0x08000000 if sys.platform == "win32" else 0
            # Fast native netstat query (0.02s vs 2s for PowerShell)
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=2,
                creationflags=creationflags
            )
            for line in res.stdout.splitlines():
                if f":{self.port}" in line and "LISTENING" in line.upper():
                    tokens = line.strip().split()
                    if tokens:
                        try:
                            pid = int(tokens[-1])
                            if pid != my_pid and pid > 0:
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", str(pid)],
                                    capture_output=True, timeout=2,
                                    creationflags=creationflags
                                )
                        except Exception:
                            pass
        except Exception:
            pass

    def _run(self):
        try:
            if self.httpd:
                self.httpd.serve_forever()
        except Exception:
            pass

    def stop(self):
        self.is_running = False
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
