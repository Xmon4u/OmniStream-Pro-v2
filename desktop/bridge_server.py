"""
OmniStream Pro v2.0.0 - Extension Localhost Bridge Server
Listens on 127.0.0.1:28795 for incoming video stream capture jobs from browser extensions.
Supports single stream addition, batch multi-link imports, and IDM-style queue synchronization.
Author: XMON4U (https://github.com/Xmon4u)
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from typing import Optional

BRIDGE_PORT = 28795

class BridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress standard logging to avoid terminal clutter
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        app = getattr(self.server, "app_instance", None)

        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            
            queue_len = len(getattr(app, "queue_items", [])) if app else 0
            is_dl = getattr(app, "is_downloading", False) if app else False

            response = {
                "status": "ok",
                "app": "OmniStream Pro",
                "version": "2.0.0",
                "bridge": "active",
                "port": BRIDGE_PORT,
                "queue_count": queue_len,
                "is_downloading": is_dl
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))

        elif self.path == "/queue":
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
        app = getattr(self.server, "app_instance", None)
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"

        try:
            data = json.loads(post_body)
        except Exception as e:
            data = {}

        if self.path == "/add":
            try:
                if not data:
                    raise ValueError("No stream data provided in payload.")

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

        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()


class BridgeServer:
    def __init__(self, app_instance, port: int = BRIDGE_PORT):
        self.app_instance = app_instance
        self.port = port
        self.httpd: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self):
        try:
            self.httpd = HTTPServer(("127.0.0.1", self.port), BridgeHandler)
            self.httpd.app_instance = self.app_instance
            self.is_running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            return True
        except OSError:
            # Port already in use or permission denied
            self.is_running = False
            return False

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
