"""
OmniStream Pro - System Tray Manager
Handles Windows taskbar system tray integration, background minimization, and quick controls.
"""

import os
import sys
import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw

try:
    import pystray
except ImportError:
    pystray = None


class TrayManager:
    """Manages Windows System Tray icon, menu actions, and minimize-to-tray behavior."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TrayManager()
        return cls._instance

    def __init__(self):
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False

    def _create_fallback_image(self) -> Image.Image:
        """Create a default 64x64 blue badge image if icon file is missing."""
        img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill="#2563eb", outline="#60a5fa", width=2)
        draw.polygon([(24, 18), (24, 46), (46, 32)], fill="#ffffff")
        return img

    def start(
        self,
        icon_path: str,
        on_show: Callable[[], None],
        on_pause_all: Callable[[], None],
        on_resume_all: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        """Initialize and run system tray icon in detached thread."""
        if not pystray or self.is_running:
            return

        # Load icon image
        image = None
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
            except Exception:
                pass
        if not image:
            image = self._create_fallback_image()

        menu = pystray.Menu(
            pystray.MenuItem("Show OmniStream", lambda icon, item: on_show(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pause All Downloads", lambda icon, item: on_pause_all()),
            pystray.MenuItem("Resume All Downloads", lambda icon, item: on_resume_all()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", lambda icon, item: on_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit OmniStream", lambda icon, item: on_exit()),
        )

        self.icon = pystray.Icon(
            "omnistream_pro",
            image,
            "OmniStream Pro",
            menu
        )

        def _runner():
            self.is_running = True
            try:
                self.icon.run()
            except Exception as e:
                print(f"[TrayManager] Tray loop exited: {e}")
            finally:
                self.is_running = False

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()

    def update_tooltip(self, text: str):
        """Update hover tooltip on tray icon."""
        if self.icon and self.is_running:
            try:
                self.icon.title = f"OmniStream Pro - {text}"
            except Exception:
                pass

    def stop(self):
        """Gracefully remove system tray icon."""
        if self.icon and self.is_running:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.is_running = False

