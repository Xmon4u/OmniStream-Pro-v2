"""
OmniStream Pro v2.0.0
Universal Multi-Audio HLS/M3U8 Stream Downloader & Multiplexer
Features: IDM-Style Batch Queue, "Download All", Extension Bridge, and Multi-Audio MKV Muxing.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import queue
import time
import threading
import webbrowser
import re
import json
import logging
from logging.handlers import RotatingFileHandler
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Enable Windows DPI awareness so the UI renders crisp on high-DPI displays
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core_engine import OmniStreamEngine, DEFAULT_SAVE_DIR
from setup_dependencies import ensure_dependencies
from bridge_server import BridgeServer
from ui_icons import apply_window_icon, build_icon_set
from window_chrome import RoundedFrame
from netflix_resolver import extract_netflix_id, resolve_netflix_title, get_non_conflicting_path
from extension_manager import (
    deploy_extension_files,
    is_extension_installed,
    mark_extension_installed,
    invalidate_extension_cache,
    get_deployed_extension_dir,
    open_chrome_extensions,
    open_extension_folder,
    launch_browser_with_extension,
    copy_path_to_clipboard,
    get_browser_executable,
    extension_is_live,
    extension_heartbeat_time,
    get_last_launch_error,
    get_app_data_dir
)

# Initialize rotating file logger in %LOCALAPPDATA%/OmniStreamPro/logs/omnistream.log
logger = logging.getLogger("OmniStreamPro")
logger.setLevel(logging.INFO)
try:
    _log_dir = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(_log_dir, exist_ok=True)
    _log_path = os.path.join(_log_dir, "omnistream.log")
    _file_handler = RotatingFileHandler(_log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_file_handler)
except Exception:
    pass

# CustomTkinter Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Professional Developer Tool Color Palettes & Design Tokens ────────────────
THEMES = {
    "Cyber Slate": {
        "name": "Cyber Slate",
        "bg_root": "#0d1117",
        "bg_header": "#161b22",
        "bg_card": "#161b22",
        "bg_card2": "#21262d",
        "bg_input": "#090d13",
        "bg_terminal": "#05070a",
        "accent_primary": "#2563eb",
        "accent_hover": "#1d4ed8",
        "accent_cyan": "#38bdf8",
        "accent_glow": "#60a5fa",
        "accent_emerald": "#10b981",
        "accent_rose": "#ef4444",
        "accent_amber": "#f59e0b",
        "border_main": "#30363d",
        "border_sub": "#21262d",
        "text_title": "#f0f6fc",
        "text_body": "#8b949e",
        "text_muted": "#6e7681",
        "text_log": "#79c0ff",
    },
    "Midnight Black": {
        "name": "Midnight Black",
        "bg_root": "#000000",
        "bg_header": "#09090b",
        "bg_card": "#0c0d10",
        "bg_card2": "#15161b",
        "bg_input": "#050507",
        "bg_terminal": "#000000",
        "accent_primary": "#6366f1",
        "accent_hover": "#4f46e5",
        "accent_cyan": "#38bdf8",
        "accent_glow": "#818cf8",
        "accent_emerald": "#10b981",
        "accent_rose": "#ef4444",
        "accent_amber": "#f59e0b",
        "border_main": "#23232a",
        "border_sub": "#181920",
        "text_title": "#ffffff",
        "text_body": "#a1a1aa",
        "text_muted": "#71717a",
        "text_log": "#a5b4fc",
    }
}

DEFAULT_THEME = "Cyber Slate"

def load_saved_theme():
    try:
        p = os.path.join(get_app_data_dir(), "theme_setting.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                th = data.get("theme", DEFAULT_THEME)
                if th in THEMES:
                    return th
    except Exception:
        pass
    return DEFAULT_THEME

def save_theme_setting(theme_name: str):
    try:
        p = os.path.join(get_app_data_dir(), "theme_setting.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"theme": theme_name}, f)
    except Exception:
        pass

INITIAL_THEME = THEMES[load_saved_theme()]

BG_ROOT        = INITIAL_THEME["bg_root"]
BG_HEADER      = INITIAL_THEME["bg_header"]
BG_CARD        = INITIAL_THEME["bg_card"]
BG_CARD2       = INITIAL_THEME["bg_card2"]
BG_INPUT       = INITIAL_THEME["bg_input"]
BG_TERMINAL    = INITIAL_THEME["bg_terminal"]
ACCENT_PRIMARY = INITIAL_THEME["accent_primary"]
ACCENT_HOVER   = INITIAL_THEME["accent_hover"]
ACCENT_CYAN    = INITIAL_THEME["accent_cyan"]
ACCENT_GLOW    = INITIAL_THEME["accent_glow"]
ACCENT_EMERALD = INITIAL_THEME["accent_emerald"]
ACCENT_ROSE    = INITIAL_THEME["accent_rose"]
ACCENT_AMBER   = INITIAL_THEME["accent_amber"]
BORDER_MAIN    = INITIAL_THEME["border_main"]
BORDER_SUB     = INITIAL_THEME["border_sub"]
TEXT_TITLE     = INITIAL_THEME["text_title"]
TEXT_BODY      = INITIAL_THEME["text_body"]
TEXT_MUTED     = INITIAL_THEME["text_muted"]
TEXT_LOG       = INITIAL_THEME["text_log"]
FONT_MAIN      = "Segoe UI"
FONT_CODE      = "Cascadia Code"

# Grid Rows
ROW_HEADER   = 0
ROW_BANNER   = 1
ROW_INPUT    = 2
ROW_OPTIONS  = 3
ROW_ACTIONS  = 4
ROW_PROGRESS = 5
ROW_CONTAINER= 6
ROW_FOOTER   = 7


class ExtensionSetupDialog(ctk.CTkToplevel):
    """Ultra-modern, 1-click Chrome extension setup modal."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Chrome Extension Setup — OmniStream Pro")
        self.geometry("620x510")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        apply_window_icon(self, BASE_DIR)
        self.icons = parent.icons

        self.transient(parent)
        self.grab_set()

        try:
            self.update_idletasks()
            px = parent.winfo_x() + (parent.winfo_width() // 2) - 310
            py = parent.winfo_y() + (parent.winfo_height() // 2) - 255
            self.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        # Auto-copy path to clipboard immediately upon opening!
        copy_path_to_clipboard()

        self._build_content()
        self._started_at = time.time()
        self.after(400, self._install_into_browser)

    def _install_into_browser(self):
        """Open Chrome and load the extension. Do not treat an old flag as success."""
        def _bg():
            mode = launch_browser_with_extension()
            err = get_last_launch_error()

            def _ui():
                try:
                    if mode:
                        self.btn_launch.configure(text="Chrome opened — adding the extension")
                        self._poll_connection()
                    else:
                        self.btn_launch.configure(text=err or "Could not add the extension")
                except Exception:
                    pass
            if hasattr(self, "parent") and hasattr(self.parent, "run_on_main_thread"):
                self.parent.run_on_main_thread(_ui)
            else:
                self.after(0, _ui)
        threading.Thread(target=_bg, daemon=True).start()

    def _poll_connection(self):
        """Close nothing until this open actually receives a new bridge ping."""
        try:
            if extension_heartbeat_time() >= self._started_at - 1:
                self._show_connected_success()
                return
        except Exception:
            pass
        self.after(1000, self._poll_connection)

    def _show_connected_success(self):
        try:
            self.success_frame.pack(fill="x", pady=(0, 10), before=self.btn_row)
            self.btn_launch.configure(text="Extension added to your Chrome account", image=self.icons["check"], fg_color="#065f46", state="disabled")
            if hasattr(self.parent, "update_bridge_status"):
                self.parent.update_bridge_status(True)
        except Exception:
            pass

    def _build_content(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=22, pady=18)

        # Header Banner
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(header, text="", image=self.icons["logo_sm"]).pack(side="left", padx=(0, 12))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            title_box, text="Browser Extension Setup",
            font=ctk.CTkFont(family=FONT_MAIN, size=16, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box, text="Connect Google Chrome to enable 1-click video stream capture from any website.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED, anchor="w"
        ).pack(anchor="w")

        # ── Option 1: 1-Click Auto Launch Card ────────────────────────────────
        hero_card = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color="#312e81")
        hero_card.pack(fill="x", pady=(0, 12))

        hero_top = ctk.CTkFrame(hero_card, fg_color="transparent")
        hero_top.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            hero_top, text="Option 1: Launch Chrome with the extension", image=self.icons["chrome"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(side="left")

        badge = ctk.CTkLabel(
            hero_top, text=" Zero Clicks ", font=ctk.CTkFont(family=FONT_MAIN, size=9, weight="bold"),
            fg_color="#064e3b", text_color="#6ee7b7", corner_radius=4, padx=6, pady=1
        )
        badge.pack(side="right")

        ctk.CTkLabel(
            hero_card,
            text="Launches Google Chrome with OmniStream Extension loaded and activated automatically.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY, anchor="w"
        ).pack(fill="x", padx=14, pady=(0, 8))

        self.btn_launch = ctk.CTkButton(
            hero_card, text="Launch Chrome", image=self.icons["play"], compound="left",
            height=36, corner_radius=8,
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER, text_color="white",
            command=self._launch_chrome
        )
        self.btn_launch.pack(fill="x", padx=14, pady=(0, 12))

        # ── Option 2: 2-Step Manual Guide Card ────────────────────────────────
        manual_card = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
        manual_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            manual_card, text="Option 2: Load it into Chrome manually", image=self.icons["folder"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(anchor="w", padx=14, pady=(10, 4))

        step1 = ctk.CTkFrame(manual_card, fg_color="transparent")
        step1.pack(fill="x", padx=14, pady=(2, 4))
        ctk.CTkLabel(step1, text="1.", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), text_color=ACCENT_CYAN).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(step1, text="Open chrome://extensions and turn ON 'Developer mode' (top-right).", font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY).pack(side="left")

        step2 = ctk.CTkFrame(manual_card, fg_color="transparent")
        step2.pack(fill="x", padx=14, pady=(2, 6))
        ctk.CTkLabel(step2, text="2.", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), text_color=ACCENT_CYAN).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(step2, text="Drag the opened folder into Chrome, OR click 'Load unpacked' and paste (Ctrl+V).", font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY).pack(side="left")

        # Path Row
        ext_dir = get_deployed_extension_dir()
        path_box = ctk.CTkFrame(manual_card, fg_color="transparent")
        path_box.pack(fill="x", padx=14, pady=(2, 10))

        self.path_entry = ctk.CTkEntry(
            path_box, fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=30, text_color="#c8deff", font=ctk.CTkFont(family=FONT_CODE, size=10), corner_radius=6
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.path_entry.insert(0, ext_dir)
        self.path_entry.configure(state="readonly")

        self.btn_copy_path = ctk.CTkButton(
            path_box, text="Copy Path", width=75, height=30,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY, font=ctk.CTkFont(family=FONT_MAIN, size=10),
            corner_radius=6, command=self._copy_path
        )
        self.btn_copy_path.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            path_box, text="", image=self.icons["folder_sm"], width=34, height=30,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY, font=ctk.CTkFont(size=12), corner_radius=6,
            command=open_extension_folder
        ).pack(side="left")

        # Success Banner (Hidden by default, shown when connected)
        self.success_frame = ctk.CTkFrame(container, fg_color="#064e3b", corner_radius=8, border_width=1, border_color="#059669")
        ctk.CTkLabel(
            self.success_frame, text="Extension connected. Ready to capture streams.", image=self.icons["check"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), text_color="#a7f3d0", padx=12, pady=8
        ).pack()

        # Bottom Buttons
        self.btn_row = ctk.CTkFrame(container, fg_color="transparent")
        self.btn_row.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            self.btn_row, text="Extensions Page", image=self.icons["globe"], compound="left", width=160, height=34,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            corner_radius=8, command=open_chrome_extensions
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self.btn_row, text="Open Folder", image=self.icons["folder"], compound="left", width=130, height=34,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_TITLE, font=ctk.CTkFont(family=FONT_MAIN, size=11),
            corner_radius=8, command=open_extension_folder
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            self.btn_row, text="I've Installed It", image=self.icons["check"], compound="left", width=150, height=34,
            fg_color="#065f46", hover_color="#047857",
            text_color="#a7f3d0", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            corner_radius=8, command=self._confirm_installed
        ).pack(side="left")

        ctk.CTkButton(
            self.btn_row, text="Later", width=70, height=34,
            fg_color="transparent", hover_color=BG_CARD2,
            text_color=TEXT_MUTED, font=ctk.CTkFont(family=FONT_MAIN, size=11),
            corner_radius=8, command=self.destroy
        ).pack(side="right")

    def _launch_chrome(self):
        def _bg():
            mode = launch_browser_with_extension()
            if mode:
                label = "Browser opened — waiting for the extension"
                def _ui_ok():
                    try:
                        self.btn_launch.configure(text=label, fg_color="#065f46")
                        if hasattr(self.parent, "_poll_auto_setup_connection"):
                            self.parent._poll_auto_setup_connection(0)
                    except Exception:
                        pass
                if hasattr(self, "parent") and hasattr(self.parent, "run_on_main_thread"):
                    self.parent.run_on_main_thread(_ui_ok)
                else:
                    self.after(0, _ui_ok)
            else:
                def _ui_err():
                    try:
                        open_chrome_extensions()
                        open_extension_folder()
                    except Exception:
                        pass
                if hasattr(self, "parent") and hasattr(self.parent, "run_on_main_thread"):
                    self.parent.run_on_main_thread(_ui_err)
                else:
                    self.after(0, _ui_err)
        threading.Thread(target=_bg, daemon=True).start()

    def _copy_path(self):
        copy_path_to_clipboard()
        self.btn_copy_path.configure(text="Copied!")
        self.after(1500, lambda: self.btn_copy_path.configure(text="Copy Path"))

    def _confirm_installed(self):
        mark_extension_installed()
        if hasattr(self.parent, "update_bridge_status"):
            self.parent.update_bridge_status(True)
        self.destroy()


class OmniStreamApp(ctk.CTk):
    """OmniStream Pro v2.0.0 Main Application Window."""

    def __init__(self):
        super().__init__()
        self.title("OmniStream Pro v2.3 — IDM-Grade Stream Downloader")

        # Responsive sizing: generous height so Download Queue is large, clear, and spacious
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        win_w = min(1120, max(980, int(sw * 0.78)))
        win_h = min(940, max(820, int(sh * 0.86)))
        x = max(0, (sw - win_w) // 2)
        y = max(0, (sh - win_h) // 2 - 20)
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.minsize(940, 700)
        self.configure(fg_color=BG_ROOT)
        self.overrideredirect(True)

        apply_window_icon(self, BASE_DIR)
        self.icons = build_icon_set(BASE_DIR)
        self._chrome = RoundedFrame(self, radius=18)

        self.log_queue           = queue.Queue()
        self._active_downloads   = {}  # item_id -> OmniStreamEngine (currently downloading)
        self.queue_items         = []  # list of dicts
        self.is_queue_running    = False
        self.download_mode       = "normal"  # "normal" or "netflix_rename"
        self.item_progress_bars  = {}  # item_id -> (CTkProgressBar, CTkLabel)
        self.item_progress_widgets = {}  # item_id -> dict of widgets for rich card metrics
        # Per-item progress tracking with time-based linear lerp
        self._item_display_pct   = {}  # item_id -> float
        self._item_target_pct    = {}  # item_id -> float
        self._item_anim_start_pct = {}
        self._item_anim_start_time = {}
        self._item_anim_duration = {}
        # Global progress bar state (shows the active download)
        self._active_item_id     = None  # which item the top progress bar shows
        self._display_pct        = 0.0
        self._target_pct         = 0.0
        self._anim_start_pct     = 0.0
        self._anim_start_time    = time.time()
        self._anim_duration      = 0.3
        self._progress_anim_job  = None
        # Performance: throttle log inserts and queue redraws
        self._log_buffer         = []   # accumulated log lines for batch insert
        self._last_log_flush     = 0.0  # time of last log flush
        self._queue_dirty        = False  # set True when queue needs full redraw
        self._last_queue_refresh = 0.0   # time of last full queue redraw

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.bind("<Escape>", lambda _e: self._exit_full_queue_view() if getattr(self, "_is_full_queue_view", False) else None)
        self.after(30, self._finish_window_chrome)
        self._poll_log_queue()
        self._tick_progress_animation()
        self._start_dependency_check()
        self._start_bridge_server()
        self.after(800, self._check_extension_prompt)

    def _on_close(self):
        """Gracefully stop bridge server and clean up before exit."""
        try:
            if hasattr(self, '_chrome') and self._chrome:
                self._chrome.uninstall()
        except Exception:
            pass
        try:
            if hasattr(self, '_active_downloads'):
                for engine in list(self._active_downloads.values()):
                    try:
                        engine.abort()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if hasattr(self, 'bridge') and self.bridge:
                self.bridge.stop()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    def _check_extension_prompt(self):
        def _bg_check():
            try:
                deployed = deploy_extension_files()
                copy_path_to_clipboard(deployed)
                if extension_is_live():
                    self.run_on_main_thread(lambda: self.update_bridge_status(True))
                else:
                    self.run_on_main_thread(self._auto_setup_extension)
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()

    def _auto_setup_extension(self):
        """Maximum Automation: Smart multi-strategy Chrome extension auto-setup."""
        self._log("[Auto-Setup] Initiating automated Chrome extension setup...")

        def _bg_launch():
            browser_exe = get_browser_executable()
            if not browser_exe:
                self.run_on_main_thread(lambda: self.show_banner(
                    "No supported browser found. Install Google Chrome and restart.",
                    level="error", show_btn=True, btn_text="Manual Setup",
                    btn_cmd=lambda: ExtensionSetupDialog(self)
                ))
                return

            self._accept_heartbeat_after = time.time()
            mode = launch_browser_with_extension(restart_running=False)
            if mode == "profile":
                msg = "Extension added to the Chrome window you are using. It works on every tab there."
            elif mode == "profile-ready":
                msg = "The extension is already in this Chrome window. It works on every tab there."
            elif mode == "default":
                msg = "Chrome started with the OmniStream extension. Waiting for it to connect..."
            elif mode == "companion-existing":
                msg = "The OmniStream browser window is already open with the extension."
            elif mode == "companion":
                msg = "Opened a Chrome window with the extension installed. Use that window while this app is open."
            else:
                msg = ""

            if mode:
                self.run_on_main_thread(lambda m=msg: (
                    self._log(f"[Auto-Setup] {m}"),
                    self.show_banner(m, level="info", show_btn=False),
                    self._poll_auto_setup_connection(attempts=0)
                ))
            else:
                err = get_last_launch_error() or "Chrome could not load the extension."
                self.run_on_main_thread(lambda e=err: (
                    self._log(f"[Auto-Setup] {e}"),
                    self.show_banner(
                        e,
                        level="warning", show_btn=True, btn_text="Add to this Chrome",
                        btn_cmd=self._launch_chrome_with_extension
                    )
                ))

        threading.Thread(target=_bg_launch, daemon=True).start()

    def _poll_auto_setup_connection(self, attempts: int):
        def _bg_poll():
            invalidate_extension_cache()
            if extension_heartbeat_time() >= getattr(self, "_accept_heartbeat_after", 0):
                self.run_on_main_thread(lambda: (
                    self.show_banner(
                        "Chrome extension connected. Ready to capture streams.",
                        level="success", show_btn=False
                    ),
                    self.update_bridge_status(True),
                    self.after(4000, self.hide_banner)
                ))
                return
            # Poll for up to 30 seconds (first 10 checks every 2s, then every 5s)
            delay_sec = 2.0 if attempts < 10 else 5.0
            max_attempts = 20
            if attempts < max_attempts:
                time.sleep(delay_sec)
                self.run_on_main_thread(lambda: self._poll_auto_setup_connection(attempts + 1))
            else:
                self.run_on_main_thread(lambda: self.show_banner(
                    "Extension not detected yet. Open setup or add it in Chrome.",
                    level="warning", show_btn=True, btn_text="View Setup",
                    btn_cmd=lambda: ExtensionSetupDialog(self)
                ))
        threading.Thread(target=_bg_poll, daemon=True).start()

    # ── UI Layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(ROW_CONTAINER, weight=1)

        self._build_header()
        self._build_banner()
        self._build_input_card()
        self._build_options_card()
        self._build_action_buttons()
        self._build_progress_row()
        self._build_container_and_queue()
        self._build_footer()

    def _build_banner(self):
        self.banner_frame = ctk.CTkFrame(self, fg_color="#1e1b4b", corner_radius=10, border_width=1, border_color="#3730a3", height=42)
        # Hidden by default; shown dynamically
        self.banner_lbl = ctk.CTkLabel(
            self.banner_frame, text="",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color="#c7d2fe"
        )
        self.banner_lbl.pack(side="left", padx=16, pady=6)

        self.btn_banner_action = ctk.CTkButton(
            self.banner_frame, text="Setup Extension", image=self.icons["extension"], compound="left", width=148, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER, corner_radius=6,
            command=lambda: ExtensionSetupDialog(self)
        )
        self.btn_banner_action.pack(side="right", padx=(0, 10), pady=6)

        self.btn_banner_close = ctk.CTkButton(
            self.banner_frame, text="", image=self.icons["close"], width=26, height=26,
            font=ctk.CTkFont(size=11), fg_color="transparent", hover_color="#312e81",
            text_color="#a5b4fc", corner_radius=6,
            command=self.hide_banner
        )
        self.btn_banner_close.pack(side="right", padx=(0, 6), pady=6)

    def show_banner(self, text: str, level: str = "info", show_btn: bool = False, btn_text: str = "", btn_cmd = None):
        colors = {
            "info":    ("#1e1b4b", "#3730a3", "#c7d2fe"),
            "success": ("#064e3b", "#059669", "#a7f3d0"),
            "warning": ("#78350f", "#d97706", "#fef3c7"),
            "error":   ("#881337", "#e11d48", "#fecdd3")
        }
        bg, border, fg = colors.get(level, colors["info"])
        self.banner_frame.configure(fg_color=bg, border_color=border)
        self.banner_lbl.configure(text=text, text_color=fg)
        if show_btn:
            self.btn_banner_action.pack(side="right", padx=(0, 10), pady=6)
            if btn_text:
                self.btn_banner_action.configure(text=btn_text)
            if btn_cmd:
                self.btn_banner_action.configure(command=btn_cmd)
        else:
            self.btn_banner_action.pack_forget()

        self.banner_frame.grid(row=ROW_BANNER, column=0, sticky="ew", padx=18, pady=(6, 2))

    def hide_banner(self):
        self.banner_frame.grid_forget()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=52)
        self.hdr_frame = hdr
        hdr.grid(row=ROW_HEADER, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="", image=self.icons["logo"]).grid(
            row=0, column=0, padx=(14, 8), pady=6
        )

        title_box = ctk.CTkFrame(hdr, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", pady=6)

        self.header_title = ctk.CTkLabel(
            title_box, text="OmniStream Pro",
            font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.header_title.pack(side="left")

        self.header_version = ctk.CTkLabel(
            title_box, text=" v2.4.0 ",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            fg_color=BG_CARD2, text_color=TEXT_MUTED,
            corner_radius=4, padx=5, pady=1
        )
        self.header_version.pack(side="left", padx=(8, 0))

        header_actions = ctk.CTkFrame(hdr, fg_color="transparent")
        header_actions.grid(row=0, column=2, padx=(8, 12), pady=0, sticky="e")

        # Top-down Theme Dropdown menu
        self.theme_menu = ctk.CTkOptionMenu(
            header_actions,
            values=["Cyber Slate", "Midnight Black"],
            command=self._on_theme_changed,
            width=124, height=26,
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            fg_color=BG_CARD2, button_color=BG_CARD,
            button_hover_color=BORDER_MAIN,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BORDER_MAIN,
            dropdown_text_color=TEXT_TITLE,
            text_color=TEXT_TITLE,
            corner_radius=6,
        )
        self.theme_menu.set(getattr(self, "current_theme_name", "Cyber Slate"))
        self.theme_menu.pack(side="left", padx=(0, 10))

        self.status_badge = ctk.CTkLabel(
            header_actions, text="● Ready",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            text_color=ACCENT_EMERALD,
            fg_color=BG_CARD2, corner_radius=12, padx=10, pady=2
        )
        self.status_badge.pack(side="left")

        caption = ctk.CTkFrame(hdr, fg_color="transparent")
        caption.grid(row=0, column=3, sticky="ne", padx=0, pady=0)
        self._caption_btn(caption, "\uE921", self._chrome.minimize)
        self._caption_max = self._caption_btn(caption, "\uE922", self._toggle_max)
        self._caption_btn(caption, "\uE8BB", self._on_close, danger=True)

        for widget in (hdr, title_box):
            self._chrome.bind_drag(widget)
        for child in title_box.winfo_children():
            self._chrome.bind_drag(child)

    def _on_theme_changed(self, theme_name: str):
        self._apply_theme(theme_name)
        self._log(f"[Theme] Switched to {theme_name} theme.")

    def set_theme(self, theme_name: str):
        if theme_name in THEMES:
            def _apply():
                self._apply_theme(theme_name)
                if hasattr(self, "theme_menu"):
                    self.theme_menu.set(theme_name)
            self.run_on_main_thread(_apply)

    def _apply_theme(self, theme_name: str):
        if theme_name not in THEMES:
            return
        theme = THEMES[theme_name]
        self.current_theme_name = theme_name

        global BG_ROOT, BG_HEADER, BG_CARD, BG_CARD2, BG_INPUT, BG_TERMINAL
        global ACCENT_PRIMARY, ACCENT_HOVER, ACCENT_CYAN, ACCENT_GLOW
        global ACCENT_EMERALD, ACCENT_ROSE, ACCENT_AMBER
        global BORDER_MAIN, BORDER_SUB, TEXT_TITLE, TEXT_BODY, TEXT_MUTED, TEXT_LOG

        BG_ROOT        = theme["bg_root"]
        BG_HEADER      = theme["bg_header"]
        BG_CARD        = theme["bg_card"]
        BG_CARD2       = theme["bg_card2"]
        BG_INPUT       = theme["bg_input"]
        BG_TERMINAL    = theme["bg_terminal"]
        ACCENT_PRIMARY = theme["accent_primary"]
        ACCENT_HOVER   = theme["accent_hover"]
        ACCENT_CYAN    = theme["accent_cyan"]
        ACCENT_GLOW    = theme["accent_glow"]
        ACCENT_EMERALD = theme["accent_emerald"]
        ACCENT_ROSE    = theme["accent_rose"]
        ACCENT_AMBER   = theme["accent_amber"]
        BORDER_MAIN    = theme["border_main"]
        BORDER_SUB     = theme["border_sub"]
        TEXT_TITLE     = theme["text_title"]
        TEXT_BODY      = theme["text_body"]
        TEXT_MUTED     = theme["text_muted"]
        TEXT_LOG       = theme["text_log"]

        try:
            # 1. Root & Header
            self.configure(fg_color=BG_ROOT)
            if hasattr(self, "hdr_frame"):
                self.hdr_frame.configure(fg_color=BG_HEADER)
            if hasattr(self, "header_title"):
                self.header_title.configure(text_color=TEXT_TITLE)
            if hasattr(self, "header_version"):
                self.header_version.configure(fg_color=BG_CARD2, text_color=TEXT_MUTED)
            if hasattr(self, "status_badge"):
                self.status_badge.configure(fg_color=BG_CARD2)
            if hasattr(self, "theme_menu"):
                self.theme_menu.configure(
                    fg_color=BG_CARD2, button_color=BG_CARD,
                    button_hover_color=BORDER_MAIN,
                    dropdown_fg_color=BG_CARD,
                    dropdown_hover_color=BORDER_MAIN,
                    dropdown_text_color=TEXT_TITLE,
                    text_color=TEXT_TITLE,
                )

            # 2. Input card
            if hasattr(self, "input_card"):
                self.input_card.configure(fg_color=BG_CARD, border_color=BORDER_MAIN)
            if hasattr(self, "input_paste_btn"):
                self.input_paste_btn.configure(
                    fg_color=BG_CARD2, hover_color=BORDER_MAIN,
                    border_color=BORDER_MAIN, text_color=TEXT_TITLE
                )
            if hasattr(self, "input_box"):
                self.input_box.configure(
                    fg_color=BG_INPUT, border_color=BORDER_SUB, text_color=TEXT_TITLE
                )

            # 3. Options card
            if hasattr(self, "options_card"):
                self.options_card.configure(fg_color=BG_CARD, border_color=BORDER_MAIN)
            menu_kw_update = dict(
                fg_color=BG_INPUT, button_color=BORDER_MAIN,
                button_hover_color=ACCENT_PRIMARY,
                dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_MAIN,
                text_color=TEXT_TITLE
            )
            for m in ("res_menu", "audio_menu", "sub_format_menu", "sub_lang_menu"):
                if hasattr(self, m):
                    getattr(self, m).configure(**menu_kw_update)

            if hasattr(self, "filename_entry"):
                self.filename_entry.configure(fg_color=BG_INPUT, border_color=BORDER_SUB, text_color=TEXT_TITLE)
            if hasattr(self, "folder_entry"):
                self.folder_entry.configure(fg_color=BG_INPUT, border_color=BORDER_SUB, text_color=TEXT_TITLE)
            if hasattr(self, "folder_browse_btn"):
                self.folder_browse_btn.configure(
                    fg_color=BG_CARD2, hover_color=BORDER_MAIN,
                    border_color=BORDER_MAIN, text_color=TEXT_TITLE
                )
            if hasattr(self, "mode_menu"):
                try:
                    self.mode_menu.configure(
                        selected_color=ACCENT_PRIMARY,
                        selected_hover_color=ACCENT_HOVER,
                        unselected_color=BG_INPUT,
                        unselected_hover_color=BG_CARD2,
                        text_color=TEXT_TITLE
                    )
                except Exception:
                    pass

            # 4. Action buttons
            if hasattr(self, "start_btn"):
                self.start_btn.configure(fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER)
            if hasattr(self, "subtitle_btn"):
                self.subtitle_btn.configure(
                    fg_color=BG_CARD2, hover_color=BORDER_MAIN,
                    border_color=BORDER_MAIN, text_color=TEXT_TITLE
                )
            if hasattr(self, "abort_btn"):
                self.abort_btn.configure(fg_color=BG_CARD2, border_color=BORDER_SUB)

            # 5. Progress card
            if hasattr(self, "progress_card"):
                self.progress_card.configure(fg_color=BG_CARD, border_color=BORDER_MAIN)
            if hasattr(self, "prog_icon_box"):
                self.prog_icon_box.configure(fg_color=BG_INPUT)
            if hasattr(self, "progress_bar"):
                self.progress_bar.configure(progress_color=ACCENT_PRIMARY, fg_color=BG_INPUT)
            if hasattr(self, "prog_percent_lbl"):
                self.prog_percent_lbl.configure(text_color=ACCENT_CYAN)
            if hasattr(self, "prog_speed_lbl"):
                self.prog_speed_lbl.configure(text_color=ACCENT_CYAN)
            if hasattr(self, "prog_size_lbl"):
                self.prog_size_lbl.configure(text_color=TEXT_BODY)
            if hasattr(self, "prog_name_lbl"):
                self.prog_name_lbl.configure(text_color=TEXT_TITLE)
            if hasattr(self, "prog_status_lbl"):
                self.prog_status_lbl.configure(text_color=TEXT_MUTED)

            # 6. Container & Queue
            if hasattr(self, "main_container"):
                self.main_container.configure(fg_color=BG_CARD, border_color=BORDER_MAIN)
            if hasattr(self, "btn_view_queue"):
                self.btn_view_queue.configure(fg_color=ACCENT_PRIMARY)
            if hasattr(self, "btn_view_terminal"):
                self.btn_view_terminal.configure(fg_color=BG_CARD2, text_color=TEXT_BODY)
            if hasattr(self, "queue_scroll"):
                self.queue_scroll.configure(fg_color=BG_INPUT, border_color=BORDER_SUB)
            if hasattr(self, "log_textbox"):
                self.log_textbox.configure(fg_color=BG_TERMINAL, text_color=TEXT_LOG)
            if hasattr(self, "btn_clear_all"):
                self.btn_clear_all.configure(fg_color=BG_CARD2, border_color=BORDER_MAIN, text_color=TEXT_TITLE)
            if hasattr(self, "btn_full_queue_view"):
                self.btn_full_queue_view.configure(fg_color=BG_CARD2, border_color=BORDER_MAIN, text_color=TEXT_TITLE)
            if hasattr(self, "btn_back_to_dashboard"):
                self.btn_back_to_dashboard.configure(fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER)

            # 7. Footer
            if hasattr(self, "footer_frame"):
                self.footer_frame.configure(fg_color=BG_HEADER)

            # 8. Refresh queue items with active theme colors
            if hasattr(self, "_refresh_queue_ui"):
                self._refresh_queue_ui()
        except Exception as ex:
            logger.error(f"Error applying theme: {ex}", exc_info=True)

        save_theme_setting(theme_name)

    def _caption_btn(self, parent, glyph, command, danger=False):
        hover = "#dc2626" if danger else "#30363d"
        button = ctk.CTkButton(
            parent, text=glyph, width=44, height=32,
            fg_color="transparent", hover_color=hover,
            text_color="#e2e8f0",
            font=ctk.CTkFont(family="Segoe MDL2 Assets", size=10),
            corner_radius=0, command=command,
        )
        button.pack(side="left", padx=0)
        return button

    def _toggle_max(self):
        self._chrome.toggle_max()
        if hasattr(self, "_caption_max"):
            self._caption_max.configure(text="\uE923" if self._chrome.maximized else "\uE922")

    def _finish_window_chrome(self):
        try:
            self._chrome.install()
            apply_window_icon(self, BASE_DIR)
        except Exception:
            pass

    def _launch_chrome_with_extension(self):
        """Add the extension to the Chrome account that is already open."""
        self.show_banner(
            "Opening the Chrome extensions page and adding the extension.",
            level="info", show_btn=False,
        )

        def _bg():
            self._accept_heartbeat_after = time.time()
            mode = launch_browser_with_extension(restart_running=True)
            def _ui():
                if mode == "profile":
                    text = "Extension added to this Chrome window. It works on every tab there."
                    self._log(f"[Chrome] {text}")
                    self.show_banner(text, level="info", show_btn=False)
                    self._poll_auto_setup_connection(attempts=0)
                elif mode == "profile-ready":
                    text = "The extension is already in this Chrome window. It works on every tab there."
                    self._log(f"[Chrome] {text}")
                    self.show_banner(text, level="success", show_btn=False)
                    self._poll_auto_setup_connection(attempts=0)
                elif mode:
                    self._log(f"[Chrome] Browser launched with the extension ({mode}).")
                    self._poll_auto_setup_connection(attempts=0)
                else:
                    err = get_last_launch_error() or "Chrome could not add the extension."
                    self._log(f"[Chrome] {err}")
                    self.show_banner(err, level="error", show_btn=False)
            self.run_on_main_thread(_ui)
        threading.Thread(target=_bg, daemon=True).start()

    def update_bridge_status(self, is_active: bool):
        """Update extension bridge connection status badge."""
        if is_active:
            self.bridge_badge.configure(text="Bridge  ·  Active", text_color=ACCENT_EMERALD)
        else:
            self.bridge_badge.configure(text="Bridge  ·  Standby", text_color=ACCENT_AMBER)

    # ── Card 1: Input Source ──────────────────────────────────────────────────
    def _build_input_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_MAIN)
        self.input_card = card
        card.grid(row=ROW_INPUT, column=0, sticky="ew", padx=18, pady=(8, 4))
        card.grid_columnconfigure(0, weight=1)

        # Top row
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(8, 4))

        ctk.CTkLabel(
            top, text="Stream Source", image=self.icons["stream"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

        ctk.CTkLabel(
            top, text="  Auto-parses cURL bash/cmd, M3U8, MPD, MP4, and MKV links",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED
        ).pack(side="left")

        self.input_paste_btn = ctk.CTkButton(
            top, text="Paste", image=self.icons["paste"], compound="left", width=80, height=26,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_MAIN,
            text_color=TEXT_TITLE,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=6,
            command=self._paste_clipboard
        )
        self.input_paste_btn.pack(side="right")

        # Input Box
        self.input_box = ctk.CTkTextbox(
            card, height=40,
            font=ctk.CTkFont(family=FONT_CODE, size=10),
            fg_color=BG_INPUT, text_color=TEXT_TITLE,
            border_width=1, border_color=BORDER_SUB, corner_radius=6
        )
        self.input_box.pack(fill="x", padx=14, pady=(0, 8))

    # ── Card 2: Configuration ─────────────────────────────────────────────────
    def _build_options_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_MAIN)
        self.options_card = card
        card.grid(row=ROW_OPTIONS, column=0, sticky="ew", padx=18, pady=(0, 4))
        card.grid_columnconfigure(0, weight=0, minsize=115)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(2, weight=0, minsize=115)
        card.grid_columnconfigure(3, weight=1)

        def lbl(row, col, text):
            ctk.CTkLabel(
                card, text=text,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                text_color=TEXT_BODY
            ).grid(row=row, column=col, sticky="w", padx=(14, 8), pady=3)

        entry_kw = dict(
            fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=30, text_color=TEXT_TITLE,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=6
        )
        menu_kw = dict(
            fg_color=BG_INPUT, button_color=BORDER_MAIN,
            button_hover_color=ACCENT_PRIMARY,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_MAIN,
            height=30,
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_TITLE, corner_radius=6
        )

        # Row 0: Title & Resolution
        lbl(0, 0, "Title (optional)")
        self.filename_entry = ctk.CTkEntry(
            card, placeholder_text="Leave blank to auto-detect", **entry_kw
        )
        self.filename_entry.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=3)

        lbl(0, 2, "Resolution")
        self.res_menu = ctk.CTkOptionMenu(
            card,
            values=["1080p (Full HD - Recommended)", "720p (HD Quality)", "480p (SD Quality)", "Best Available", "Audio Only (No Video)"],
            **menu_kw
        )
        self.res_menu.set("1080p (Full HD - Recommended)")
        self.res_menu.grid(row=0, column=3, sticky="ew", padx=(0, 14), pady=3)

        # Row 1: Save Folder & Audio Selection
        lbl(1, 0, "Save Folder")
        fr = ctk.CTkFrame(card, fg_color="transparent")
        fr.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=3)
        fr.grid_columnconfigure(0, weight=1)

        self.folder_entry = ctk.CTkEntry(fr, **entry_kw)
        self.folder_entry.grid(row=0, column=0, sticky="ew")
        self.folder_entry.insert(0, DEFAULT_SAVE_DIR)

        self.folder_browse_btn = ctk.CTkButton(
            fr, text="Browse", width=68, height=30,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_MAIN,
            text_color=TEXT_TITLE,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=6,
            command=self._browse_folder
        )
        self.folder_browse_btn.grid(row=0, column=1, padx=(6, 0))

        lbl(1, 2, "Audio Tracks")
        self.audio_menu = ctk.CTkOptionMenu(
            card,
            values=[
                "All Available Languages (Lossless)",
                "English + Hindi (Dual Audio)",
                "English Only",
                "Hindi Only",
            ],
            **menu_kw
        )
        self.audio_menu.set("All Available Languages (Lossless)")
        self.audio_menu.grid(row=1, column=3, sticky="ew", padx=(0, 14), pady=3)

        # Row 2: Mode Selection | Subtitle Format + Language
        lbl(2, 0, "Download Mode")
        mode_box = ctk.CTkFrame(card, fg_color="transparent")
        mode_box.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=3)
        mode_box.grid_columnconfigure(0, weight=1)

        self.mode_menu = ctk.CTkSegmentedButton(
            mode_box,
            values=["Normal Mode", "Sub Merge Mode", "Netflix Rename Mode"],
            command=self._on_mode_changed,
            height=30,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            selected_color=ACCENT_PRIMARY,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_INPUT,
            unselected_hover_color=BG_CARD2,
            text_color=TEXT_TITLE,
            corner_radius=6
        )
        self.mode_menu.set("Normal Mode")
        self.mode_menu.grid(row=0, column=0, sticky="ew")

        # Row 2 right: Subtitle Format
        lbl(2, 2, "Subtitle Format")
        self.sub_format_menu = ctk.CTkOptionMenu(
            card,
            values=["SRT (SubRip — Universal)", "VTT (WebVTT)"],
            **menu_kw
        )
        self.sub_format_menu.set("SRT (SubRip — Universal)")
        self.sub_format_menu.grid(row=2, column=3, sticky="ew", padx=(0, 14), pady=3)

        # Row 3: Mode Status | Subtitle Language
        lbl(3, 0, "Mode Status")
        self.mode_hint_lbl = ctk.CTkLabel(
            card,
            text="Normal Mode: Downloads with original stream title/filename.",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED,
            anchor="w",
            wraplength=380,
            justify="left"
        )
        self.mode_hint_lbl.grid(row=3, column=1, sticky="w", padx=(0, 14), pady=3)

        # Dynamic wrap on resize to prevent vertical jumping
        def _on_options_resize(event):
            try:
                if hasattr(self, "mode_hint_lbl"):
                    target_wrap = max(260, (event.width // 2) - 130)
                    self.mode_hint_lbl.configure(wraplength=target_wrap)
            except Exception:
                pass
        card.bind("<Configure>", _on_options_resize, add="+")

        lbl(3, 2, "Subtitle Language")
        self.sub_lang_menu = ctk.CTkOptionMenu(
            card,
            values=[
                "All Languages",
                "English (eng)",
                "Hindi (hin)",
                "Arabic (ara)",
                "German (deu)",
                "Spanish (spa)",
                "French (fra)",
                "Portuguese (por)",
                "Russian (rus)",
                "Japanese (jpn)",
                "Korean (kor)",
                "Chinese Simplified (zho)",
            ],
            **menu_kw
        )
        self.sub_lang_menu.set("All Languages")
        self.sub_lang_menu.grid(row=3, column=3, sticky="ew", padx=(0, 14), pady=3)

        # Row 4: Embed Subtitles into Video (MKV) Checkbox
        lbl(4, 0, "Subtitles")
        sub_opts_frame = ctk.CTkFrame(card, fg_color="transparent")
        sub_opts_frame.grid(row=4, column=1, columnspan=3, sticky="w", padx=(0, 14), pady=(4, 6))

        self.embed_subs_var = ctk.BooleanVar(value=True)
        self.embed_subs_cb = ctk.CTkCheckBox(
            sub_opts_frame,
            text="Embed Subtitles into Video (MKV container)",
            variable=self.embed_subs_var,
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            text_color=TEXT_TITLE,
            corner_radius=4
        )
        self.embed_subs_cb.pack(side="left")

    def _on_mode_changed(self, value: str):
        val_low = value.lower()
        if "sub" in val_low or "merge" in val_low:
            self.download_mode = "sub_merge"
            self.embed_subs_var.set(True)
            self.mode_hint_lbl.configure(
                text="Sub Merge Mode: Video + all multi-audio tracks + all subtitles merged together into MKV.",
                text_color=ACCENT_CYAN
            )
            self._log("[Mode] Switched to Sub Merge Mode — video, all multi-audio tracks, and subtitles will be merged together into MKV.")
        elif "netflix" in val_low:
            self.download_mode = "netflix_rename"
            self.embed_subs_var.set(True)
            self.mode_hint_lbl.configure(
                text="Netflix Mode: Auto-identifies ID & renames to official movie/series title with video, multi-audio & subtitles.",
                text_color=ACCENT_CYAN
            )
            self._log("[Mode] Switched to Netflix Rename Mode — will detect Netflix ID & auto-rename upon download completion.")
        else:
            self.download_mode = "normal"
            self.embed_subs_var.set(False)
            self.mode_hint_lbl.configure(
                text="Normal Mode: Downloads with original stream title/filename and audio tracks.",
                text_color=TEXT_MUTED
            )
            self._log("[Mode] Switched to Normal Mode.")

    def set_download_mode(self, mode: str):
        m = str(mode).lower()
        if "netflix" in m:
            display_name = "Netflix Rename Mode"
        elif "sub" in m or "merge" in m:
            display_name = "Sub Merge Mode"
        else:
            display_name = "Normal Mode"
        def _apply():
            if hasattr(self, "mode_menu"):
                self.mode_menu.set(display_name)
            self._on_mode_changed(display_name)
        self.run_on_main_thread(_apply)

    # ── Action Buttons ────────────────────────────────────────────────────────
    def _build_action_buttons(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        self.action_bar = bar
        bar.grid(row=ROW_ACTIONS, column=0, sticky="ew", padx=18, pady=(4, 4))

        # Standard desktop button sizes that never distort on resize or fullscreen
        self.start_btn = ctk.CTkButton(
            bar,
            text="Start Download", image=self.icons["play"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            height=34, width=150, corner_radius=6,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white",
            command=self._start_download
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        # Subtitle-only download button
        self.subtitle_btn = ctk.CTkButton(
            bar,
            text="Download Subtitles", image=self.icons.get("stream", self.icons["play"]), compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            height=34, width=165, corner_radius=6,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_MAIN,
            text_color=TEXT_TITLE,
            command=self._start_subtitle_download
        )
        self.subtitle_btn.pack(side="left", padx=(0, 8))

        self.abort_btn = ctk.CTkButton(
            bar,
            text="Stop", image=self.icons["stop"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            height=34, width=85, corner_radius=6,
            fg_color=BG_CARD2, hover_color=ACCENT_ROSE,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_MUTED,
            state="disabled",
            command=self._abort_download
        )
        self.abort_btn.pack(side="left")

    # ── Progress Row (Demo Layout Matching Dark Theme) ─────────────────────────
    def _build_progress_row(self):
        self.progress_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_MAIN
        )
        self.progress_card.grid(row=ROW_PROGRESS, column=0, sticky="ew", padx=18, pady=(0, 4))
        self.progress_card.grid_columnconfigure(0, weight=1)

        # Top Section: [File Icon] + [Title / Status] ... [Percent Badge]
        top_bar = ctk.CTkFrame(self.progress_card, fg_color="transparent")
        top_bar.pack(fill="x", padx=14, pady=(6, 2))
        top_bar.grid_columnconfigure(1, weight=1)

        # Icon box badge
        icon_box = ctk.CTkFrame(top_bar, fg_color=BG_INPUT, corner_radius=6, width=32, height=32)
        self.prog_icon_box = icon_box
        icon_box.grid(row=0, column=0, rowspan=2, padx=(0, 10), sticky="w")
        icon_box.grid_propagate(False)
        self.prog_icon_lbl = ctk.CTkLabel(
            icon_box, text="", image=self.icons.get("file", self.icons["stream"])
        )
        self.prog_icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Name / Title
        self.prog_name_lbl = ctk.CTkLabel(
            top_bar,
            text="Ready to Download",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        )
        self.prog_name_lbl.grid(row=0, column=1, sticky="w")

        # Status text below title
        self.prog_status_lbl = ctk.CTkLabel(
            top_bar,
            text="Ready — Paste a stream URL above or send links from the Chrome extension.",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED, anchor="w"
        )
        self.prog_status_lbl.grid(row=1, column=1, sticky="w", pady=(1, 0))

        # Percentage badge
        self.prog_percent_lbl = ctk.CTkLabel(
            top_bar,
            text="0%",
            font=ctk.CTkFont(family=FONT_MAIN, size=13, weight="bold"),
            text_color=ACCENT_CYAN, anchor="e"
        )
        self.prog_percent_lbl.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

        # Backward compatibility alias
        self.progress_lbl = self.prog_status_lbl

        # Track / Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_card, height=6, corner_radius=3,
            progress_color=ACCENT_PRIMARY, fg_color=BG_INPUT
        )
        self.progress_bar.pack(fill="x", padx=14, pady=(5, 6))
        self.progress_bar.set(0)

        # Details Section: Exactly 2 indicators — Size (left) & Speed (right)
        details = ctk.CTkFrame(self.progress_card, fg_color="transparent")
        details.pack(fill="x", padx=14, pady=(0, 8))
        details.grid_columnconfigure(0, weight=1)
        details.grid_columnconfigure(1, weight=1)

        self.prog_size_lbl = ctk.CTkLabel(
            details, text="-- / --",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            text_color=TEXT_BODY, anchor="w"
        )
        self.prog_size_lbl.grid(row=0, column=0, sticky="w")

        self.prog_speed_lbl = ctk.CTkLabel(
            details, text="0.0 MB/s",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            text_color=ACCENT_CYAN, anchor="e"
        )
        self.prog_speed_lbl.grid(row=0, column=1, sticky="e")

        # Dummy labels retained for compatibility
        self.prog_time_lbl = ctk.CTkLabel(details, text="")
        self.prog_left_lbl = ctk.CTkLabel(details, text="")

    # ── Container & Queue View (IDM Experience) ───────────────────────────────
    def _build_container_and_queue(self):
        self.main_container = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_MAIN)
        self.main_container.grid(row=ROW_CONTAINER, column=0, sticky="nsew", padx=18, pady=(0, 5))
        self.main_container.grid_rowconfigure(1, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Tab Selector Bar (Standard Dashboard View)
        self.tab_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tab_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))

        # Switch Buttons
        btn_box = ctk.CTkFrame(self.tab_bar, fg_color="transparent")
        btn_box.pack(side="left")

        self.btn_view_queue = ctk.CTkButton(
            btn_box, text="Download Queue (0)", image=self.icons["queue"], compound="left", width=175, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=ACCENT_PRIMARY, text_color="white", corner_radius=6,
            command=self._show_queue_view
        )
        self.btn_view_queue.pack(side="left", padx=(0, 6))

        self.btn_view_terminal = ctk.CTkButton(
            btn_box, text="Terminal", image=self.icons["terminal"], compound="left", width=110, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=BG_CARD2, text_color=TEXT_BODY, corner_radius=6,
            command=self._show_terminal_view
        )
        self.btn_view_terminal.pack(side="left")

        # Terminal-only actions (hidden on Queue view)
        self.term_actions = ctk.CTkFrame(self.tab_bar, fg_color="transparent")
        ctk.CTkButton(
            self.term_actions, text="Clear Logs", width=86, height=24,
            font=ctk.CTkFont(size=10), fg_color=BG_CARD2,
            hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_MAIN,
            text_color=TEXT_BODY, corner_radius=5,
            command=lambda: self.log_textbox.delete("1.0", "end")
        ).pack(side="right")

        # ── Dedicated Full Screen Queue Header Bar ──
        self.full_view_header_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        btn_back_box = ctk.CTkFrame(self.full_view_header_bar, fg_color="transparent")
        btn_back_box.pack(side="left")

        self.btn_back_to_dashboard = ctk.CTkButton(
            btn_back_box, text="← Back to Dashboard",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white", width=160, height=30, corner_radius=6,
            command=self._exit_full_queue_view
        )
        self.btn_back_to_dashboard.pack(side="left", padx=(0, 10))

        self.full_view_title = ctk.CTkLabel(
            btn_back_box, text="Downloads & Queue Manager (Full Screen View)",
            font=ctk.CTkFont(family=FONT_MAIN, size=13, weight="bold"),
            text_color=TEXT_TITLE
        )
        self.full_view_title.pack(side="left")

        self.full_view_stats_lbl = ctk.CTkLabel(
            self.full_view_header_bar, text="Queue: 0 items",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED
        )
        self.full_view_stats_lbl.pack(side="right", padx=8)

        # ── View 1: Queue Manager Frame (Default View) ──
        self.queue_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_frame.grid_rowconfigure(1, weight=1)

        q_tool = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        q_tool.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 8))

        self.start_queue_btn = ctk.CTkButton(
            q_tool, text="Download All", image=self.icons["play"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color="#15803d", hover_color="#166534", text_color="white",
            width=130, height=30, corner_radius=6, command=self._start_queue_processing
        )
        self.start_queue_btn.pack(side="left", padx=(0, 6))

        self.btn_clear_all = ctk.CTkButton(
            q_tool, text="Clear All",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=BG_CARD2, hover_color="#7f1d1d", text_color=TEXT_TITLE,
            border_width=1, border_color=BORDER_MAIN,
            width=80, height=30, corner_radius=6, command=self._clear_all_queue
        )
        self.btn_clear_all.pack(side="left", padx=(0, 6))

        # Full View / Expand Screen button (as requested by user)
        self.btn_full_queue_view = ctk.CTkButton(
            q_tool, text="Full View ↗",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, text_color=TEXT_TITLE,
            border_width=1, border_color=BORDER_MAIN,
            width=96, height=30, corner_radius=6, command=self._enter_full_queue_view
        )
        self.btn_full_queue_view.pack(side="left")

        self.queue_stats_lbl = ctk.CTkLabel(
            q_tool, text="Queue: 0 items",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED
        )
        self.queue_stats_lbl.pack(side="right", padx=8)

        # Scrollable items list
        self.queue_scroll = ctk.CTkScrollableFrame(
            self.queue_frame, fg_color=BG_INPUT,
            border_width=1, border_color=BORDER_SUB, corner_radius=6
        )
        self.queue_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # ── View 2: Terminal Log Textbox ──
        self.log_textbox = ctk.CTkTextbox(
            self.main_container,
            font=ctk.CTkFont(family=FONT_CODE, size=10),
            fg_color=BG_TERMINAL, text_color=TEXT_LOG,
            corner_radius=6, border_width=1, border_color=BORDER_SUB,
            wrap="none"
        )
        # Not gridded by default; queue view is shown first.

    def _enter_full_queue_view(self):
        """Expand download queue to full window view for easier viewing and scrolling."""
        self._is_full_queue_view = True
        if hasattr(self, "banner_frame") and self.banner_frame.winfo_ismapped():
            self.banner_frame.grid_remove()
        if hasattr(self, "input_card"):
            self.input_card.grid_remove()
        if hasattr(self, "options_card"):
            self.options_card.grid_remove()
        if hasattr(self, "action_bar"):
            self.action_bar.grid_remove()
        if hasattr(self, "progress_card"):
            self.progress_card.grid_remove()

        self.tab_bar.grid_remove()
        self.full_view_header_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        self._show_queue_view()
        self._refresh_queue_ui()

    def _exit_full_queue_view(self):
        """Restore standard dashboard view."""
        self._is_full_queue_view = False
        self.full_view_header_bar.grid_remove()
        self.tab_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))

        if hasattr(self, "input_card"):
            self.input_card.grid(row=ROW_INPUT, column=0, sticky="ew", padx=18, pady=(8, 4))
        if hasattr(self, "options_card"):
            self.options_card.grid(row=ROW_OPTIONS, column=0, sticky="ew", padx=18, pady=(0, 4))
        if hasattr(self, "action_bar"):
            self.action_bar.grid(row=ROW_ACTIONS, column=0, sticky="ew", padx=18, pady=(3, 3))
        if hasattr(self, "progress_card"):
            self.progress_card.grid(row=ROW_PROGRESS, column=0, sticky="ew", padx=18, pady=(0, 4))

        self._refresh_queue_ui()

    def _show_terminal_view(self):
        self.queue_frame.grid_forget()
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.btn_view_terminal.configure(fg_color=ACCENT_PRIMARY, text_color="white")
        self.btn_view_queue.configure(fg_color=BG_CARD2, text_color=TEXT_BODY)
        self.term_actions.pack(side="right")

    def _show_queue_view(self):
        self.log_textbox.grid_forget()
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.btn_view_queue.configure(fg_color=ACCENT_PRIMARY, text_color="white")
        self.btn_view_terminal.configure(fg_color=BG_CARD2, text_color=TEXT_BODY)
        self.term_actions.pack_forget()
        self._refresh_queue_ui()

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=28)
        self.footer_frame = footer
        footer.grid(row=ROW_FOOTER, column=0, sticky="ew")
        footer.grid_propagate(False)

        self.bridge_badge = ctk.CTkLabel(
            footer, text="Bridge  ·  Standby", image=self.icons["globe"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            text_color=ACCENT_AMBER, fg_color="transparent",
        )
        self.bridge_badge.pack(side="left", padx=14)

        ctk.CTkButton(
            footer,
            text="OmniStream Pro v2.4.0  •  Developed by XMON4U  •  GitHub Repository",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED, fg_color="transparent",
            hover_color=BG_CARD, cursor="hand2",
            command=lambda: webbrowser.open_new_tab("https://github.com/Xmon4u")
        ).pack(side="right", padx=14)

    # ── Bridge Server ─────────────────────────────────────────────────────────
    def _start_bridge_server(self):
        self.bridge = BridgeServer(self)
        success = self.bridge.start()
        if success:
            self._log("[Bridge] Extension bridge active — listening on 127.0.0.1:28795")
            self.bridge_badge.configure(text="Bridge  ·  Active", text_color=ACCENT_EMERALD)
        else:
            self._log("[Bridge] Port 28795 already in use — extension will connect to existing instance.")
            self.bridge_badge.configure(text="Bridge  ·  Connected", text_color=ACCENT_AMBER)

    # ── Log & Event Dispatcher ────────────────────────────────────────────────
    def _log(self, text: str):
        try:
            logger.info(text)
        except Exception:
            pass
        self.log_queue.put(("log", text))

    def _set_progress(self, pct: float, msg: str, item_id: str = None):
        self.log_queue.put(("progress", (pct, msg, item_id)))

    def _format_progress_label(self, pct: float, msg: str) -> str:
        pct = max(0.0, min(100.0, float(pct)))
        base = (msg or "").strip()
        if "drm-protected" in base.lower() or "drm protected" in base.lower():
            return "This stream is DRM-protected and not supported."
        # Engine already sends a rich status line — pass it through unchanged.
        if "% done" in base or "% left" in base or "ETA" in base or "MB/s" in base or "KB/s" in base:
            return base
        if pct >= 100:
            return base or "100.0% done  ·  Complete!"
        if base:
            left = max(0.0, 100.0 - pct)
            return f"{pct:.1f}% done  ·  {left:.1f}% left  ·  {base}"
        left = max(0.0, 100.0 - pct)
        return f"{pct:.1f}% done  ·  {left:.1f}% left"

    def _parse_progress_metrics(self, pct: float, text: str) -> dict:
        """Parse status, percent, size, speed, ETA, and remaining from engine/callback strings."""
        pct = max(0.0, min(100.0, float(pct)))
        clean = (text or "").strip()
        low = clean.lower()

        # Status
        if "drm-protected" in low or "drm protected" in low:
            status = "This stream is DRM-protected and not supported."
        elif pct >= 100.0 or "complete" in low or "saved:" in low:
            status = "Completed"
        elif "abort" in low or "cancel" in low:
            status = "Cancelled"
        elif "failed" in low or "error" in low:
            status = "Failed"
        elif "mux" in low or "merg" in low:
            status = "Muxing & finalizing..."
        elif pct > 0 or "download" in low:
            status = "Downloading..."
        elif "start" in low or "resolv" in low:
            status = "Starting..."
        else:
            status = "Ready"

        # Percent string
        percent_str = f"{int(round(pct))}%"

        # Size / Segments
        size = ""
        # 1. Dual pair: downloaded / total (handles MB, GB, KB, GiB, MiB)
        sz_pair = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]i?B)\s*/\s*(\d+(?:\.\d+)?\s*[KMGT]i?B)', clean, re.IGNORECASE)
        if sz_pair:
            size = f"{sz_pair.group(1).strip()} / {sz_pair.group(2).strip()}"
        else:
            # 2. Number / Number Unit (e.g. 10.5 / 35.0 MB)
            sz_pair2 = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]i?B)', clean, re.IGNORECASE)
            if sz_pair2:
                size = f"{sz_pair2.group(1)} {sz_pair2.group(3)} / {sz_pair2.group(2)} {sz_pair2.group(3)}"
            else:
                # 3. Segments: X / Y segs
                seg_match = re.search(r'(\d+)\s*/\s*(\d+)\s*(?:segs|segments)?', clean)
                if seg_match:
                    size = f"{seg_match.group(1)} / {seg_match.group(2)} segs"
                else:
                    # 4. Single size (downloaded)
                    one_sz = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]i?B)', clean, re.IGNORECASE)
                    if one_sz:
                        size = f"{one_sz.group(1).strip()} downloaded"
                    elif status == "This stream is DRM-protected and not supported.":
                        size = "DRM Protected"
                    elif status == "Completed":
                        size = "Completed"
                    elif status in ("Downloading...", "Muxing & finalizing...", "Starting..."):
                        size = "Calculating..."
                    else:
                        size = "-- / --"

        # Speed
        speed = ""
        speed_match = re.search(r'(\d+(?:\.\d+)?)\s*([KMGT]i?B(?:/s|ps)|B(?:/s|ps))', clean, re.IGNORECASE)
        if speed_match:
            val = float(speed_match.group(1))
            unit = speed_match.group(2).upper().replace('IB', 'B').replace('PS', '/s').replace('/S', '/s')
            if not unit.endswith('/s'):
                unit += '/s'
            speed = f"{val:.1f} {unit}" if unit != "B/s" else f"{val:.0f} B/s"
        elif status in ("Downloading...", "Muxing & finalizing...", "Starting..."):
            speed = "0.0 MB/s"
        else:
            speed = "--"

        # Time / ETA
        time_str = ""
        # 1. Matches formatted ETA e.g. ETA 2m 15s, 1h 20m, 45s left, etc.
        hms_m = re.search(r'(?:ETA:?\s*|left\s*[:\-]?\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?(\d+)s(?:\s*left)?', clean, re.IGNORECASE)
        if hms_m and (hms_m.group(1) or hms_m.group(2) or hms_m.group(3)) and pct < 99.5:
            h = int(hms_m.group(1)) if hms_m.group(1) else 0
            m = int(hms_m.group(2)) if hms_m.group(2) else 0
            s = int(hms_m.group(3)) if hms_m.group(3) else 0
            if h > 0:
                time_str = f"{h}h {m}m left"
            elif m > 0:
                time_str = f"{m}m {s:02d}s left"
            elif s > 0:
                time_str = f"{s}s left"

        if not time_str and pct < 99.5:
            # 2. Matches HH:MM:SS or MM:SS
            col_m = re.search(r'(?:ETA:?\s*|left\s*[:\-]?\s*)?(\d{1,2}):(\d{2})(?::(\d{2}))?', clean, re.IGNORECASE)
            if col_m:
                parts = [int(x) for x in col_m.groups() if x is not None]
                if len(parts) == 3:
                    h, m, s = parts
                    time_str = f"{h}h {m}m left" if h > 0 else f"{m}m {s:02d}s left"
                elif len(parts) == 2:
                    m, s = parts
                    time_str = f"{m}m {s:02d}s left"

        if not time_str:
            if status == "Completed":
                time_str = "Completed"
            elif status in ("Downloading...", "Muxing & finalizing...", "Starting..."):
                time_str = "Calculating..."
            else:
                time_str = "--"

        # Remaining
        left_pct = max(0.0, 100.0 - pct)
        remaining_str = f"{int(round(left_pct))}% remaining"

        return {
            "status": status,
            "percent": percent_str,
            "size": size,
            "speed": speed,
            "time": time_str,
            "left": remaining_str
        }

    def _apply_progress_ui(self, pct: float, status_text: str, item_id: str = None):
        pct = max(0.0, min(100.0, float(pct)))
        label = self._format_progress_label(pct, status_text)
        metrics = self._parse_progress_metrics(pct, status_text)

        # Update the specific item's data
        target_id = item_id
        if target_id:
            for item in self.queue_items:
                if item["id"] == target_id:
                    item["progress_pct"] = pct
                    item["progress_text"] = label
                    item["metrics"] = metrics
                    break

            # Schedule time-based linear interpolation for item progress bar
            prev_target = self._item_target_pct.get(target_id, 0.0)
            if abs(pct - prev_target) > 0.01:
                self._item_anim_start_pct[target_id] = self._item_display_pct.get(target_id, 0.0)
                self._item_target_pct[target_id] = pct
                self._item_anim_start_time[target_id] = time.time()
                self._item_anim_duration[target_id] = 0.3

            if target_id not in self._item_display_pct:
                self._item_display_pct[target_id] = 0.0

            if target_id in self.item_progress_bars:
                _pbar, plbl = self.item_progress_bars[target_id]
                try:
                    plbl.configure(
                        text=label,
                        text_color=ACCENT_CYAN if pct < 100 else ACCENT_EMERALD,
                    )
                except Exception:
                    pass

            if hasattr(self, "item_progress_widgets") and target_id in self.item_progress_widgets:
                w = self.item_progress_widgets[target_id]
                try:
                    if "status_lbl" in w:
                        w["status_lbl"].configure(text=metrics["status"])
                    if "pct_lbl" in w:
                        w["pct_lbl"].configure(
                            text=metrics["percent"],
                            text_color=ACCENT_CYAN if pct < 100 else ACCENT_EMERALD
                        )
                    if "sub_lbl" in w:
                        w["sub_lbl"].configure(text=metrics["size"])
                    if "sub2_lbl" in w:
                        w["sub2_lbl"].configure(
                            text=metrics["speed"] if pct < 100 else "Completed",
                            text_color=ACCENT_CYAN if pct < 100 else ACCENT_EMERALD
                        )
                except Exception:
                    pass

        # Top progress bar: track the most recently active item
        if target_id and (target_id == self._active_item_id or self._active_item_id is None):
            if self._active_item_id is None:
                self._active_item_id = target_id

            if abs(pct - self._target_pct) > 0.01:
                self._anim_start_pct = self._display_pct
                self._target_pct = pct
                self._anim_start_time = time.time()
                self._anim_duration = 0.3

            # Update item title on top card
            active_title = next((it["title"] for it in self.queue_items if it["id"] == target_id), None)
            if active_title:
                try:
                    self.prog_name_lbl.configure(text=active_title)
                except Exception:
                    pass

            try:
                self.prog_status_lbl.configure(text=metrics["status"])
                self.prog_size_lbl.configure(text=metrics["size"])
                self.prog_time_lbl.configure(text=metrics["time"])
                self.prog_speed_lbl.configure(text=metrics["speed"])
                self.prog_left_lbl.configure(text=metrics["left"])
            except Exception:
                pass
        elif not target_id:
            # Direct progress update (e.g. initial status or non-queue downloads)
            if abs(pct - self._target_pct) > 0.01:
                self._anim_start_pct = self._display_pct
                self._target_pct = pct
                self._anim_start_time = time.time()
                self._anim_duration = 0.3

            try:
                self.prog_status_lbl.configure(text=status_text or metrics["status"])
                self.prog_size_lbl.configure(text=metrics["size"])
                self.prog_time_lbl.configure(text=metrics["time"])
                self.prog_speed_lbl.configure(text=metrics["speed"])
                self.prog_left_lbl.configure(text=metrics["left"])
            except Exception:
                pass

    def _tick_progress_animation(self):
        """Smooth Chrome-style bar fill — no bouncing, no indeterminate pulse."""
        try:
            now = time.time()
            # ── Top global progress bar (0.3s linear transition) ─────────────
            if self._display_pct != self._target_pct:
                if self._target_pct == 0.0:
                    self._display_pct = 0.0
                else:
                    elapsed = now - self._anim_start_time
                    if elapsed >= self._anim_duration:
                        self._display_pct = self._target_pct
                    else:
                        ratio = min(1.0, max(0.0, elapsed / self._anim_duration))
                        self._display_pct = self._anim_start_pct + (self._target_pct - self._anim_start_pct) * ratio

                shown = max(0.0, min(1.0, self._display_pct / 100.0))
                try:
                    self.progress_bar.set(shown)
                    pct_int = int(round(self._display_pct))
                    if self._display_pct >= 99.9:
                        self.progress_bar.configure(progress_color=ACCENT_EMERALD)
                        self.prog_percent_lbl.configure(text="100%", text_color=ACCENT_EMERALD)
                    else:
                        self.progress_bar.configure(progress_color=ACCENT_CYAN)
                        self.prog_percent_lbl.configure(text=f"{pct_int}%", text_color=ACCENT_CYAN)
                except Exception:
                    pass

            # ── Per-item progress bars (smooth 0.3s linear fill) ─────────────
            for iid, tgt in list(self._item_target_pct.items()):
                cur = self._item_display_pct.get(iid, 0.0)
                if abs(cur - tgt) < 0.05:  # Skip micro-updates to avoid unnecessary Tk calls
                    continue
                if tgt == 0.0:
                    cur = 0.0
                else:
                    start_p = self._item_anim_start_pct.get(iid, cur)
                    start_t = self._item_anim_start_time.get(iid, now)
                    dur = self._item_anim_duration.get(iid, 0.3)
                    elapsed_i = now - start_t
                    if elapsed_i >= dur:
                        cur = tgt
                    else:
                        ratio_i = min(1.0, max(0.0, elapsed_i / dur))
                        cur = start_p + (tgt - start_p) * ratio_i
                self._item_display_pct[iid] = cur

                shown_i = max(0.0, min(1.0, cur / 100.0))
                if iid in self.item_progress_bars:
                    pbar, _plbl = self.item_progress_bars[iid]
                    try:
                        pbar.set(shown_i)
                        if iid in self._active_downloads:
                            pbar.configure(progress_color=ACCENT_CYAN)
                        elif shown_i >= 0.999:
                            pbar.configure(progress_color=ACCENT_EMERALD)
                    except Exception:
                        pass

                if hasattr(self, "item_progress_widgets") and iid in self.item_progress_widgets:
                    pct_lbl = self.item_progress_widgets[iid].get("pct_lbl")
                    if pct_lbl:
                        try:
                            if cur >= 99.9:
                                pct_lbl.configure(text="100%", text_color=ACCENT_EMERALD)
                            else:
                                pct_lbl.configure(text=f"{int(round(cur))}%", text_color=ACCENT_CYAN)
                        except Exception:
                            pass
        except Exception:
            pass
        # 40ms interval: ~25 fps animation — smooth without CPU waste
        self._progress_anim_job = self.after(40, self._tick_progress_animation)

    @property
    def is_downloading(self) -> bool:
        """True when at least one download is currently active."""
        return bool(self._active_downloads)

    def run_on_main_thread(self, fn):
        """Safely execute a function on the Tkinter main loop thread."""
        self.log_queue.put(("dispatch_fn", fn))

    def _poll_log_queue(self):
        """High-performance event dispatcher: batched log inserts, throttled queue redraws."""
        processed = 0
        log_lines = []
        now = time.time()

        # Drain up to 30 messages per poll to keep UI responsive
        while not self.log_queue.empty() and processed < 30:
            msg_type, data = self.log_queue.get_nowait()
            processed += 1
            if msg_type == "log":
                # Buffer log lines; batch-insert below to minimize Tkinter calls
                log_lines.append(data)
            elif msg_type == "progress":
                pct, status_text, item_id = data
                self._apply_progress_ui(pct, status_text, item_id)
            elif msg_type == "bring_to_foreground":
                self._bring_to_foreground()
            elif msg_type == "bridge_connected":
                self.update_bridge_status(True)
            elif msg_type == "bridge_job":
                self._handle_bridge_job(data)
            elif msg_type == "bridge_batch_jobs":
                self._handle_bridge_batch_jobs(data)
            elif msg_type == "start_queue_requested":
                self._start_queue_processing()
            elif msg_type == "set_mode_requested":
                self.set_download_mode(data.get("mode", "normal"))
            elif msg_type == "set_theme_requested":
                self.set_theme(data.get("theme", "Cyber Slate"))
            elif msg_type == "queue_item_finished":
                self._handle_queue_item_finished(data)
            elif msg_type == "dispatch_fn":
                try:
                    data()
                except Exception as exc:
                    logger.error(f"Error in dispatched fn: {exc}", exc_info=True)

        # Batch-insert all buffered log lines in ONE Tkinter call (prevents UI stutter)
        if log_lines:
            try:
                combined = "\n".join(log_lines) + "\n"
                self.log_textbox.insert("end", combined)
                # Only auto-scroll if textbox is at/near the bottom (avoid fighting user scroll)
                self.log_textbox.see("end")
            except Exception:
                pass

        # Full queue UI redraw: throttled to at most once every 200ms to prevent jank
        if self._queue_dirty and (now - self._last_queue_refresh) >= 0.20:
            self._queue_dirty = False
            self._last_queue_refresh = now
            self._refresh_queue_ui()

        self.after(80, self._poll_log_queue)

    def _set_status(self, state: str):
        def _apply():
            states = {
                "ready":       ("● Ready", ACCENT_EMERALD),
                "downloading": ("● Downloading", ACCENT_CYAN),
                "done":        ("● Complete", ACCENT_EMERALD),
                "error":       ("● Error", ACCENT_ROSE),
                "aborted":     ("● Stopped", ACCENT_AMBER),
            }
            text, color = states.get(state, ("● Ready", ACCENT_EMERALD))
            self.status_badge.configure(text=text, text_color=color)
        self.run_on_main_thread(_apply)

    # ── Dependency Check ──────────────────────────────────────────────────────
    def _start_dependency_check(self):
        def _check():
            self._log("[System] Initializing OmniStream Pro engine dependencies...")
            try:
                n, f = ensure_dependencies(
                    status_callback=lambda s: self._log(f"  {s}"),
                    progress_callback=lambda pct, txt: self._set_progress(pct, txt),
                )
                self._log(f"[Ready] Stream Engine : {n}")
                self._log(f"[Ready] Media Muxer   : {f}\n")
                self._set_status("ready")
                self._set_progress(0, "Ready — all dependencies configured.")
            except Exception as exc:
                self._log(f"[Error] Dependency setup failed: {exc}")
                self._set_status("error")

        threading.Thread(target=_check, daemon=True).start()

    # ── Extension Bridge Event Handlers ───────────────────────────────────────
    def _bring_to_foreground(self):
        try:
            self.deiconify()
            self.lift()
            self.attributes('-topmost', True)
            self.after_idle(self.attributes, '-topmost', False)
            self.focus_force()
        except Exception:
            pass

    def _handle_bridge_job(self, data: dict):
        self._bring_to_foreground()
        title = data.get("title", "").strip()
        curl_or_url = data.get("curl") or data.get("url", "")
        auto_start = data.get("autoStart", False)
        mode = data.get("mode", "")
        netflix_id = data.get("netflixId", "")

        # Check if this is a 1-click subtitle download job from the Chrome extension
        is_sub_job = bool(data.get("isSubtitleJob") or str(data.get("type", "")).lower() == "subtitles")
        if is_sub_job:
            self._log(f"\n[Extension Bridge] Received 1-click Subtitle download request: {title or 'Stream Subtitles'}")
            try:
                self.input_box.delete("1.0", "end")
                self.input_box.insert("1.0", curl_or_url)
                if title and title.lower() not in ("player", "video"):
                    self.filename_entry.delete(0, "end")
                    self.filename_entry.insert(0, title)
            except Exception:
                pass
            self._start_subtitle_download(raw_input=curl_or_url, title=title)
            return

        item = self._add_to_queue(
            raw_input=curl_or_url,
            custom_title=title,
            auto_show_tab=True,
            mode=mode,
            netflix_id=netflix_id
        )
        self._log(f"\n[Extension Bridge] Received stream: {title or 'Video Stream'}")
        if item.get("mode") == "netflix_rename":
            self._log(f"  Mode: Netflix Rename Mode (ID: {item.get('netflix_id') or 'Detecting...'})")
        self._log(f"  Source queued for IDM batch download.")

        if auto_start:
            self._start_download_item(item, is_queue_batch=False)

    def _handle_bridge_batch_jobs(self, data: dict):
        self._bring_to_foreground()
        items = data.get("items", [])
        added_count = 0
        for it in items:
            title = it.get("title", "").strip()
            curl_or_url = it.get("curl") or it.get("url", "")
            mode = it.get("mode", "")
            netflix_id = it.get("netflixId", "")
            if curl_or_url:
                self._add_to_queue(
                    raw_input=curl_or_url,
                    custom_title=title,
                    auto_show_tab=False,
                    mode=mode,
                    netflix_id=netflix_id
                )
                added_count += 1

        self._show_queue_view()
        self._log(f"\n[Extension Bridge] Successfully imported {added_count} streams into Download Queue.")
        self._log(f"  Click 'Download All' to download the entire queue sequentially.")

    # ── Queue Operations ──────────────────────────────────────────────────────
    def _add_to_queue(
        self,
        raw_input: str,
        custom_title: str = "",
        auto_show_tab: bool = False,
        mode: str = "",
        netflix_id: str = ""
    ):
        res_raw = self.res_menu.get().lower()
        if "1080p" in res_raw:
            resolution = "1080p"
        elif "720p" in res_raw:
            resolution = "720p"
        elif "480p" in res_raw:
            resolution = "480p"
        elif "audio only" in res_raw:
            resolution = "audio_only"
        else:
            resolution = "best"

        aud_raw = self.audio_menu.get().lower()
        if "english + hindi" in aud_raw:
            audio_choice = "en_hi"
        elif "english only" in aud_raw:
            audio_choice = "eng"
        elif "hindi only" in aud_raw:
            audio_choice = "hin"
        else:
            audio_choice = "all"

        save_dir = self.folder_entry.get().strip()

        item_mode = mode or self.download_mode

        # Sanitize custom title: remove any stream extensions e.g. .m3u8, .mpd, .mp4
        cleaned_custom = re.sub(r'\.(m3u8|mpd|mp4|webm|mkv|m4s)(\?.*)?$', '', custom_title.strip(), flags=re.IGNORECASE).strip()

        detected_nid = netflix_id or extract_netflix_id(cleaned_custom) or extract_netflix_id(raw_input)
        is_user_explicit_title = bool(cleaned_custom and not cleaned_custom.isdigit() and cleaned_custom.lower() not in ("video", "player"))

        if cleaned_custom:
            display_title = cleaned_custom
        elif item_mode == "netflix_rename" and detected_nid:
            display_title = f"{detected_nid}"
        else:
            display_title = f"OmniStream_{len(self.queue_items) + 1}"

        embed_subs = getattr(self, "embed_subs_var", None)
        is_sub_mode = item_mode in ("sub_merge", "netflix_rename")
        include_subs = is_sub_mode or (embed_subs.get() if embed_subs is not None else False)

        fmt_raw = self.sub_format_menu.get().upper()
        sub_format = "VTT" if "VTT" in fmt_raw else "SRT"

        lang_raw = self.sub_lang_menu.get().lower()
        lang_map = {
            "english": "eng", "hindi": "hin", "arabic": "ara",
            "german": "deu", "spanish": "spa", "french": "fra",
            "portuguese": "por", "russian": "rus", "japanese": "jpn",
            "korean": "kor", "chinese": "zho",
        }
        sub_lang = "all"
        for key, code in lang_map.items():
            if key in lang_raw:
                sub_lang = code
                break

        item = {
            "id": f"q_{int(time.time()*1000)}_{len(self.queue_items)}",
            "title": display_title,
            "user_specified_title": is_user_explicit_title,
            "input": raw_input,
            "save_dir": save_dir,
            "resolution": resolution,
            "audio": audio_choice,
            "include_subtitles": include_subs,
            "sub_format": sub_format,
            "sub_lang": sub_lang,
            "status": "Waiting",
            "saved_file": None,
            "progress_pct": 0.0,
            "progress_text": "Ready in queue",
            "mode": item_mode,
            "netflix_id": detected_nid if item_mode == "netflix_rename" else None,
            "resolved_title": None,
        }
        self.queue_items.append(item)
        self.btn_view_queue.configure(text=f"Download Queue ({len(self.queue_items)})")

        if auto_show_tab:
            self._show_queue_view()
        else:
            self._request_queue_refresh()  # Throttled: avoids re-rendering on every extension link
        return item

    def _request_queue_refresh(self):
        """Mark queue as dirty; actual redraw is throttled in _poll_log_queue (max once per 200ms)."""
        self._queue_dirty = True

    def _refresh_queue_ui(self):
        """Full queue widget rebuild. Called at most ~5x/sec via dirty-flag throttle."""
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()

        self.item_progress_bars.clear()
        if hasattr(self, "item_progress_widgets"):
            self.item_progress_widgets.clear()

        total = len(self.queue_items)
        waiting = len([it for it in self.queue_items if it["status"] == "Waiting"])
        done = len([it for it in self.queue_items if it["status"] == "Completed"])
        active = len(self._active_downloads)
        stats_str = f"Queue: {total} total · {active} active · {waiting} waiting · {done} done"
        self.queue_stats_lbl.configure(text=stats_str)
        if hasattr(self, "full_view_stats_lbl"):
            self.full_view_stats_lbl.configure(text=stats_str)
        self.btn_view_queue.configure(text=f"Download Queue ({total})")

        if not self.queue_items:
            empty = ctk.CTkLabel(
                self.queue_scroll,
                text="The Download Queue is empty.\n\nCapture media links using the OmniStream Pro Chrome Extension\nor paste cURL/links above and click 'Add to Queue'.\n\nWhen links are added, click 'Download All' to batch download like IDM.",
                font=ctk.CTkFont(family=FONT_MAIN, size=12),
                text_color=TEXT_MUTED, pady=50
            )
            empty.pack(expand=True)
            return

        status_colors = {
            "Waiting":     (ACCENT_AMBER, "#78350f"),
            "Downloading": (ACCENT_GLOW, "#1e3a8a"),
            "Completed":   (ACCENT_EMERALD, "#064e3b"),
            "Failed":      (ACCENT_ROSE, "#7f1d1d"),
            "Paused":      (TEXT_BODY, "#334155")
        }

        for item in self.queue_items:
            card = ctk.CTkFrame(self.queue_scroll, fg_color=BG_CARD2, corner_radius=8, border_width=1, border_color=BORDER_SUB)
            card.pack(fill="x", padx=4, pady=4)
            card.grid_columnconfigure(1, weight=1)

            # Left status pill
            s_color, s_bg = status_colors.get(item["status"], (TEXT_BODY, BG_CARD))
            pill = ctk.CTkLabel(
                card, text=f" {item['status']} ",
                font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                text_color=s_color, fg_color=s_bg, corner_radius=6, padx=8, pady=3
            )
            pill.grid(row=0, column=0, rowspan=2, padx=10, pady=8, sticky="w")

            # Center details
            detail_frame = ctk.CTkFrame(card, fg_color="transparent")
            detail_frame.grid(row=0, column=1, sticky="ew", padx=4, pady=(6, 2))

            title_row = ctk.CTkFrame(detail_frame, fg_color="transparent")
            title_row.pack(fill="x", anchor="w")

            if item.get("mode") == "netflix_rename":
                ctk.CTkLabel(
                    title_row, text=" NETFLIX ",
                    font=ctk.CTkFont(family=FONT_MAIN, size=9, weight="bold"),
                    fg_color="#881337", text_color="#fecdd3", corner_radius=4, padx=5, pady=1
                ).pack(side="left", padx=(0, 6))
            elif item.get("mode") == "sub_merge" or item.get("include_subtitles"):
                ctk.CTkLabel(
                    title_row, text=" SUB MERGE ",
                    font=ctk.CTkFont(family=FONT_MAIN, size=9, weight="bold"),
                    fg_color="#0f766e", text_color="#ccfbf1", corner_radius=4, padx=5, pady=1
                ).pack(side="left", padx=(0, 6))

            raw_title = str(item.get("title", ""))
            display_title = (raw_title[:65] + "…") if len(raw_title) > 68 else raw_title
            title_lbl = ctk.CTkLabel(
                title_row, text=display_title,
                font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
                text_color=TEXT_TITLE, anchor="w"
            )
            title_lbl.pack(side="left", anchor="w")

            # Show Edit button only for completed items with a saved file
            if item["status"] == "Completed" and item.get("saved_file") and os.path.exists(item.get("saved_file", "")):
                ctk.CTkButton(
                    title_row,
                    text="", image=self.icons["edit"],
                    width=24, height=20,
                    fg_color="transparent", hover_color=BORDER_MAIN,
                    corner_radius=4,
                    command=lambda it=item: self._rename_file_dialog(it)
                ).pack(side="left", padx=(6, 0))

            info_str = f"Quality: {item['resolution']} | Audio: {item['audio']} | Folder: {os.path.basename(item['save_dir'])}"
            ctk.CTkLabel(
                detail_frame, text=info_str,
                font=ctk.CTkFont(family=FONT_MAIN, size=10),
                text_color=TEXT_MUTED, anchor="w"
            ).pack(anchor="w")

            # Center progress bar row
            prog_row = ctk.CTkFrame(card, fg_color="transparent")
            prog_row.grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 6))
            prog_row.grid_columnconfigure(0, weight=1)

            stored_pct = float(item.get("progress_pct") or 0.0)
            metrics = item.get("metrics") or self._parse_progress_metrics(stored_pct, item.get("progress_text") or "")

            # Mini top bar: status on left, bold percent on right
            top_prog = ctk.CTkFrame(prog_row, fg_color="transparent")
            top_prog.pack(fill="x", pady=(0, 2))
            top_prog.grid_columnconfigure(0, weight=1)

            if item["status"] == "Completed":
                status_color = ACCENT_EMERALD
            elif item["status"] == "Downloading":
                status_color = ACCENT_CYAN
            elif item["status"] == "Failed":
                status_color = ACCENT_ROSE
            else:
                status_color = TEXT_MUTED

            item_status_lbl = ctk.CTkLabel(
                top_prog, text=metrics["status"],
                font=ctk.CTkFont(family=FONT_MAIN, size=10),
                text_color=status_color, anchor="w"
            )
            item_status_lbl.grid(row=0, column=0, sticky="w")

            pct_color = ACCENT_EMERALD if item["status"] == "Completed" else (
                ACCENT_CYAN if item["status"] == "Downloading" else TEXT_MUTED
            )
            item_pct_lbl = ctk.CTkLabel(
                top_prog, text=f"{int(round(stored_pct))}%",
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                text_color=pct_color, anchor="e"
            )
            item_pct_lbl.grid(row=0, column=1, sticky="e")

            item_pbar = ctk.CTkProgressBar(
                prog_row, height=5, corner_radius=3,
                progress_color=ACCENT_CYAN if item["status"] == "Downloading" else (
                    ACCENT_EMERALD if item["status"] == "Completed" else BG_INPUT
                ),
                fg_color=BG_INPUT
            )
            item_pbar.pack(fill="x", pady=(2, 2))
            if item["status"] == "Completed":
                item_pbar.set(1.0)
            elif item["status"] == "Downloading":
                item_pbar.set(max(0.01, min(1.0, stored_pct / 100.0)))
            else:
                item_pbar.set(0.0)

            # Details row below bar: Left (Size & Speed) | Right (Time & Remaining)
            sub_row = ctk.CTkFrame(prog_row, fg_color="transparent")
            sub_row.pack(fill="x", pady=(1, 0))
            sub_row.grid_columnconfigure(0, weight=1)
            sub_row.grid_columnconfigure(1, weight=1)

            # Exactly 2 indicators: Size (left) & Speed (right)
            left_detail = metrics["size"]
            right_detail = metrics["speed"] if item["status"] == "Downloading" else ("Completed" if item["status"] == "Completed" else "")

            item_sub_lbl = ctk.CTkLabel(
                sub_row, text=left_detail,
                font=ctk.CTkFont(family=FONT_MAIN, size=9, weight="bold"),
                text_color=TEXT_TITLE if item["status"] == "Downloading" else TEXT_MUTED, anchor="w"
            )
            item_sub_lbl.grid(row=0, column=0, sticky="w")

            item_sub2_lbl = ctk.CTkLabel(
                sub_row, text=right_detail,
                font=ctk.CTkFont(family=FONT_MAIN, size=9, weight="bold"),
                text_color=ACCENT_CYAN if item["status"] == "Downloading" else (ACCENT_EMERALD if item["status"] == "Completed" else TEXT_MUTED),
                anchor="e"
            )
            item_sub2_lbl.grid(row=0, column=1, sticky="e")

            self.item_progress_bars[item["id"]] = (item_pbar, item_status_lbl)
            if not hasattr(self, "item_progress_widgets"):
                self.item_progress_widgets = {}
            self.item_progress_widgets[item["id"]] = {
                "pbar": item_pbar,
                "status_lbl": item_status_lbl,
                "pct_lbl": item_pct_lbl,
                "sub_lbl": item_sub_lbl,
                "sub2_lbl": item_sub2_lbl,
            }

            # Right action buttons
            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.grid(row=0, column=2, rowspan=2, padx=8, pady=6, sticky="e")

            if item["status"] in ("Waiting", "Failed", "Paused"):
                ctk.CTkButton(
                    btn_box, text="Download", image=self.icons["download"], compound="left", width=108, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
                    command=lambda it=item: self._start_download_item(it, is_queue_batch=False)
                ).pack(side="left", padx=3)
            elif item["status"] == "Downloading":
                # Per-item Cancel button
                ctk.CTkButton(
                    btn_box, text="Cancel", image=self.icons["stop"], compound="left", width=90, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color="#881337", hover_color="#9f1239", text_color="#fecdd3",
                    command=lambda it=item: self._cancel_item(it)
                ).pack(side="left", padx=3)
            elif item["status"] == "Completed" and item.get("saved_file") and os.path.exists(item["saved_file"]):
                ctk.CTkButton(
                    btn_box, text="Play", image=self.icons["play"], compound="left", width=78, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color="#065f46", hover_color="#047857", text_color="white",
                    command=lambda it=item: os.startfile(it["saved_file"])
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    btn_box, text="", image=self.icons["folder_sm"], width=32, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=11),
                    fg_color=BG_CARD, hover_color=BORDER_MAIN, text_color=TEXT_BODY,
                    command=lambda it=item: os.startfile(os.path.dirname(it["saved_file"]))
                ).pack(side="left", padx=2)

            # Remove button: cancel if downloading, and remove from queue
            ctk.CTkButton(
                btn_box, text="", image=self.icons["close"], width=28, height=26,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                fg_color=BG_CARD, hover_color="#7f1d1d", text_color="#fca5a5",
                command=lambda it=item: self._cancel_and_remove(it)
            ).pack(side="left", padx=2)

    def _rename_file_dialog(self, item: dict):
        """Open an inline rename dialog for a completed download item."""
        saved_file = item.get("saved_file", "")
        if not saved_file or not os.path.exists(saved_file):
            messagebox.showerror("Rename Error", "File not found on disk.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Rename File")
        dialog.geometry("480x190")
        dialog.resizable(False, False)
        dialog.configure(fg_color=BG_ROOT)
        dialog.transient(self)
        dialog.grab_set()
        apply_window_icon(dialog, BASE_DIR)

        # Center over parent
        try:
            dialog.update_idletasks()
            px = self.winfo_x() + (self.winfo_width() // 2) - 240
            py = self.winfo_y() + (self.winfo_height() // 2) - 95
            dialog.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=22, pady=18)

        ctk.CTkLabel(
            frame, text="Rename File",
            font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        ).pack(anchor="w", pady=(0, 6))

        current_stem = os.path.splitext(os.path.basename(saved_file))[0]
        # Clean any trailing .m3u8 or .mpd from stem
        current_stem = re.sub(r'\.(m3u8|mpd)$', '', current_stem, flags=re.I)
        ext = os.path.splitext(saved_file)[1]  # e.g. .mkv

        ctk.CTkLabel(
            frame, text="New filename (without extension):",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED, anchor="w"
        ).pack(anchor="w", pady=(0, 4))

        name_entry = ctk.CTkEntry(
            frame, fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=34, text_color=TEXT_TITLE,
            font=ctk.CTkFont(family=FONT_MAIN, size=12), corner_radius=8
        )
        name_entry.pack(fill="x", pady=(0, 14))
        name_entry.insert(0, current_stem)
        name_entry.select_range(0, "end")
        name_entry.focus()

        def _do_rename():
            new_name = name_entry.get().strip()
            if not new_name:
                messagebox.showwarning("Rename", "Please enter a filename.", parent=dialog)
                return
            # Strip trailing extension if user typed it
            import re as _re
            new_name = _re.sub(r'\.(mkv|mp4|m3u8|mpd)$', '', new_name, flags=_re.I).strip()
            new_name = _re.sub(r'[\\/*?"<>|:]', "", new_name).strip()
            if not new_name:
                messagebox.showwarning("Rename", "Invalid filename.", parent=dialog)
                return

            new_path = os.path.join(os.path.dirname(saved_file), new_name + ext)
            abs_new = os.path.abspath(new_path)
            abs_saved = os.path.abspath(saved_file)

            if abs_new == abs_saved:
                dialog.destroy()
                return

            is_case_change = (abs_new.lower() == abs_saved.lower())

            if not is_case_change and os.path.exists(new_path):
                if not messagebox.askyesno("Rename",
                        f"A file named '{new_name + ext}' already exists.\nOverwrite it?",
                        parent=dialog):
                    return
                try:
                    os.remove(new_path)
                except Exception:
                    pass

            try:
                if is_case_change:
                    # Windows NTFS requires a two-step rename when only letter casing changes
                    temp_path = os.path.join(
                        os.path.dirname(saved_file),
                        f"__omni_ren_{int(time.time()*1000)}_{new_name}{ext}"
                    )
                    os.rename(saved_file, temp_path)
                    os.rename(temp_path, new_path)
                else:
                    os.rename(saved_file, new_path)

                item["saved_file"] = new_path
                item["title"] = new_name
                self._log(f"[Rename] '{os.path.basename(saved_file)}' → '{new_name + ext}'")
                dialog.destroy()
                self._refresh_queue_ui()
            except Exception as exc:
                messagebox.showerror("Rename Failed",
                    f"Could not rename the file:\n{exc}", parent=dialog)

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row, text="Rename", image=self.icons["edit"], compound="left",
            width=120, height=32, corner_radius=8,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER, text_color="white",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            command=_do_rename
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Cancel", width=80, height=32, corner_radius=8,
            fg_color="transparent", hover_color=BG_CARD2,
            text_color=TEXT_MUTED, font=ctk.CTkFont(family=FONT_MAIN, size=11),
            command=dialog.destroy
        ).pack(side="left")

        dialog.bind("<Return>", lambda e: _do_rename())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def _cancel_and_remove(self, item):
        """Cancel the download if active, and remove the item from queue."""
        item_id = item["id"]
        if item_id in self._active_downloads:
            self._cancel_item(item)
        if item in self.queue_items:
            self.queue_items.remove(item)
            self._item_target_pct.pop(item_id, None)
            self._item_display_pct.pop(item_id, None)

        if item_id == self._active_item_id:
            other_active = [aid for aid in self._active_downloads if aid != item_id]
            if other_active:
                self._active_item_id = other_active[0]
                other_it = next((it for it in self.queue_items if it["id"] == self._active_item_id), None)
                if other_it:
                    try:
                        self.prog_name_lbl.configure(text=other_it["title"])
                        other_pct = float(other_it.get("progress_pct") or 0.0)
                        self._target_pct = other_pct
                        self._display_pct = other_pct
                        self.progress_bar.set(max(0.0, min(1.0, other_pct / 100.0)))
                        self.prog_percent_lbl.configure(text=f"{int(round(other_pct))}%", text_color=ACCENT_CYAN)
                    except Exception:
                        pass
            else:
                self._active_item_id = None
                self._target_pct = 0.0
                self._display_pct = 0.0
                self.progress_bar.set(0.0)
                try:
                    self.prog_name_lbl.configure(text="No active download")
                    self.prog_status_lbl.configure(text="Ready")
                    self.prog_percent_lbl.configure(text="0%", text_color=TEXT_MUTED)
                    self.prog_speed_lbl.configure(text="0.0 MB/s")
                    self.prog_time_lbl.configure(text="--")
                    self.prog_size_lbl.configure(text="0 MB")
                    self.prog_left_lbl.configure(text="--")
                except Exception:
                    pass

        self._request_queue_refresh()  # Throttled redraw after cancel/remove

    def _remove_queue_item(self, item):
        self._cancel_and_remove(item)

    def _cancel_item(self, item):
        """Cancel a specific downloading item without affecting others."""
        item_id = item["id"]
        engine = self._active_downloads.get(item_id)
        if engine:
            self._log(f"\n[Action] Cancelling: {item['title']}")
            engine.abort()

    def _clear_all_queue(self):
        # Only remove items that are NOT currently downloading
        non_active = [it for it in self.queue_items if it["id"] not in self._active_downloads]
        for it in non_active:
            self._item_target_pct.pop(it["id"], None)
            self._item_display_pct.pop(it["id"], None)
        self.queue_items = [it for it in self.queue_items if it["id"] in self._active_downloads]
        if not self._active_downloads:
            self.is_queue_running = False
            self.start_queue_btn.configure(text="Download All", state="normal")
        self._request_queue_refresh()  # Throttled

    def _start_queue_processing(self):
        waiting_items = [it for it in self.queue_items if it["status"] in ("Waiting", "Failed", "Paused")]
        if not waiting_items:
            messagebox.showinfo("Queue", "No waiting items in the queue.")
            return

        self.is_queue_running = True
        self.start_queue_btn.configure(text="Downloading…", state="disabled")
        # Start up to 3 downloads concurrently
        MAX_CONCURRENT_QUEUE = 3
        count = 0
        for it in waiting_items:
            if it["id"] not in self._active_downloads:
                self._start_download_item(it, is_queue_batch=True)
                count += 1
                if count >= MAX_CONCURRENT_QUEUE:
                    break

    def _handle_queue_item_finished(self, data: dict):
        item_id = data.get("id")
        status = data.get("status")
        saved_file = data.get("saved_file")
        is_queue_batch = data.get("is_queue_batch", False)

        # Remove from active downloads
        self._active_downloads.pop(item_id, None)

        for it in self.queue_items:
            if it["id"] == item_id:
                it["status"] = status
                if saved_file:
                    it["saved_file"] = saved_file
                if status == "Completed":
                    it["progress_pct"] = 100.0
                    it["progress_text"] = "100% done  ·  Finished"
                    self._item_target_pct[item_id] = 100.0
                elif status == "Failed":
                    it["progress_text"] = it.get("progress_text") or "Cancelled / Failed"
                break

        # Update top progress bar if this was the active item
        if item_id == self._active_item_id:
            if self._active_downloads:
                # Hand off to another active download
                self._active_item_id = next(iter(self._active_downloads))
                other_it = next((it for it in self.queue_items if it["id"] == self._active_item_id), None)
                if other_it:
                    try:
                        self.prog_name_lbl.configure(text=other_it["title"])
                        other_pct = float(other_it.get("progress_pct") or 0.0)
                        self._target_pct = other_pct
                        self._display_pct = other_pct
                        self.progress_bar.set(max(0.0, min(1.0, other_pct / 100.0)))
                        self.prog_percent_lbl.configure(text=f"{int(round(other_pct))}%", text_color=ACCENT_CYAN)
                    except Exception:
                        pass
            else:
                self._active_item_id = None
                if status == "Completed":
                    self._target_pct = 100.0
                    self._display_pct = 100.0
                    self.progress_bar.set(1.0)
                    try:
                        self.prog_status_lbl.configure(text="Download complete!")
                        self.prog_percent_lbl.configure(text="100%", text_color=ACCENT_EMERALD)
                        self.prog_time_lbl.configure(text="Completed")
                        self.prog_speed_lbl.configure(text="--")
                        self.prog_left_lbl.configure(text="0% remaining")
                        if saved_file:
                            self.prog_name_lbl.configure(text=os.path.basename(saved_file))
                            self.prog_size_lbl.configure(text="Saved successfully")
                    except Exception:
                        pass
                else:
                    self._target_pct = 0.0
                    self._display_pct = 0.0
                    self.progress_bar.set(0.0)
                    try:
                        self.prog_status_lbl.configure(text=f"Download {status.lower()}")
                        self.prog_percent_lbl.configure(text="0%", text_color=ACCENT_ROSE if status == "Failed" else TEXT_MUTED)
                        self.prog_speed_lbl.configure(text="--")
                        self.prog_time_lbl.configure(text="--")
                        self.prog_size_lbl.configure(text="--")
                        self.prog_left_lbl.configure(text="--")
                    except Exception:
                        pass

        self._refresh_queue_ui()

        # Update header status badge
        if not self._active_downloads:
            self._set_status("done" if status == "Completed" else "aborted")
            self.after(0, lambda: self.start_btn.configure(
                state="normal", fg_color=ACCENT_PRIMARY,
                text="Start Download", image=self.icons["play"]
            ))
            self.after(0, lambda: self.abort_btn.configure(state="disabled"))

        # Queue batch: check for more waiting items or completion
        if is_queue_batch and self.is_queue_running:
            MAX_CONCURRENT_QUEUE = 3
            waiting_items = [it for it in self.queue_items
                             if it["status"] in ("Waiting", "Failed", "Paused") and it["id"] not in self._active_downloads]
            while waiting_items and len(self._active_downloads) < MAX_CONCURRENT_QUEUE:
                next_it = waiting_items.pop(0)
                self._start_download_item(next_it, is_queue_batch=True)

            if not waiting_items and not self._active_downloads:
                self.is_queue_running = False
                self.start_queue_btn.configure(text="Download All", state="normal")
                completed = sum(1 for it in self.queue_items if it["status"] == "Completed")
                failed = sum(1 for it in self.queue_items if it["status"] == "Failed")
                if failed:
                    messagebox.showinfo("Queue Complete",
                        f"Queue finished: {completed} completed, {failed} failed.")
                else:
                    messagebox.showinfo("Queue Complete",
                        "All items in the download queue have been saved successfully!")

    # ── User Actions ──────────────────────────────────────────────────────────
    def _paste_clipboard(self):
        try:
            content = self.clipboard_get().strip()
            self.input_box.delete("1.0", "end")
            self.input_box.insert("end", content)
        except Exception:
            messagebox.showwarning("Clipboard", "Could not read from system clipboard.")

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if folder:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)

    def _abort_download(self):
        """Abort ALL active downloads (Stop button in main bar)."""
        if self._active_downloads:
            self._log("\n[Action] Stopping all active downloads...")
            for engine in list(self._active_downloads.values()):
                try:
                    engine.abort()
                except Exception:
                    pass
            self.is_queue_running = False
            self.start_queue_btn.configure(text="Download All", state="normal")

    def _start_download(self):
        """Start Download button handler — adds input to queue and begins immediately."""
        raw_input = self.input_box.get("1.0", "end").strip()
        if not raw_input:
            messagebox.showwarning("Missing Input", "Please paste a cURL command or direct M3U8 link first.")
            return
        item = self._add_to_queue(raw_input=raw_input,
                                  custom_title=self.filename_entry.get().strip(),
                                  auto_show_tab=True,
                                  mode=self.download_mode)
        # Clear input box and filename for next item
        self.input_box.delete("1.0", "end")
        self.filename_entry.delete(0, "end")
        self._start_download_item(item, is_queue_batch=False)

    # ── Subtitle-Only Download ─────────────────────────────────────────────────
    def _start_subtitle_download(self, raw_input: Optional[str] = None, title: Optional[str] = None):
        """Download Subtitles button handler — downloads only subtitle tracks (no video/audio)."""
        if not raw_input:
            raw_input = self.input_box.get("1.0", "end").strip()
        if not raw_input:
            messagebox.showwarning(
                "Missing Input",
                "Please paste a cURL command or direct M3U8/MPD stream link first.\n\n"
                "To get the stream link, play the video in Chrome and capture it via the OmniStream extension."
            )
            return

        # Read subtitle options from dropdowns
        fmt_raw = self.sub_format_menu.get().upper()
        sub_format = "VTT" if "VTT" in fmt_raw else "SRT"

        lang_raw = self.sub_lang_menu.get().lower()
        lang_map = {
            "english": "eng", "hindi": "hin", "arabic": "ara",
            "german": "deu", "spanish": "spa", "french": "fra",
            "portuguese": "por", "russian": "rus", "japanese": "jpn",
            "korean": "kor", "chinese": "zho",
        }
        sub_lang = "all"
        for key, code in lang_map.items():
            if key in lang_raw:
                sub_lang = code
                break

        save_name = title or self.filename_entry.get().strip()
        save_dir  = self.folder_entry.get().strip() or DEFAULT_SAVE_DIR

        self._log(f"\n[Subtitle Download] Starting subtitle-only extraction...")
        self._log(f"  Format   : {sub_format}")
        self._log(f"  Language : {'All Available' if sub_lang == 'all' else sub_lang}")
        self._log(f"  Save To  : {save_dir}")

        # Unique id for this subtitle task so it can be stopped via Stop button
        sub_item_id = f"sub_{int(time.time() * 1000)}"
        engine = OmniStreamEngine()
        self._active_downloads[sub_item_id] = engine

        self._set_progress(0.0, "Starting subtitle download\u2026  \xb7  0% done  \xb7  100% left")
        self.abort_btn.configure(state="normal")
        try:
            self.subtitle_btn.configure(state="disabled", text="Downloading Subtitles\u2026")
        except Exception:
            pass
        self._set_status("downloading")

        def _progress_cb(pct: float, msg: str):
            self._set_progress(pct, msg)

        saved_subs_ref = []

        def _worker():
            try:
                saved_subs = engine.run_subtitle_download(
                    input_text=raw_input,
                    save_name=save_name,
                    save_dir=save_dir,
                    sub_format=sub_format,
                    sub_lang=sub_lang,
                    log_callback=self._log,
                    progress_callback=_progress_cb,
                )
                saved_subs_ref.extend(saved_subs)
                count = len(saved_subs)
                names = "\n".join(f"  \u2022 {os.path.basename(p)}" for p in saved_subs)
                self._log(f"\n[Subtitle Download] \u2705 {count} subtitle file(s) saved successfully!")
                for p in saved_subs:
                    self._log(f"  {os.path.basename(p)}")
                _progress_cb(100.0, f"Subtitles saved: {count} file(s)")
                self.run_on_main_thread(lambda c=count, n=names, d=save_dir: messagebox.showinfo(
                    "Subtitle Download Complete",
                    f"{c} subtitle file(s) saved!\n\nFolder: {d}\n\n{n}"
                ))
            except RuntimeError as exc:
                err = str(exc)
                is_abort = "abort" in err.lower() or "cancel" in err.lower()
                is_drm = "drm-protected" in err.lower() or "drm protected" in err.lower() or "drm" in err.lower()
                is_no_subs = "no subtitle" in err.lower() or "no stream found" in err.lower()
                if is_drm:
                    label = "DRM Protected"
                    msg = "This stream is DRM-protected and not supported."
                elif is_abort:
                    label = "Cancelled"
                    msg = "Cancelled"
                elif is_no_subs:
                    label = "No Subtitles"
                    msg = "No Subtitles in stream"
                else:
                    label = "Subtitle Download Failed"
                    msg = f"Failed: {err[:80]}"
                self._log(f"\n[{label}] {err}")
                _progress_cb(0.0, msg)
                if is_drm:
                    self.run_on_main_thread(lambda e=err: messagebox.showerror("DRM Protected Stream", e))
                elif is_no_subs:
                    self.run_on_main_thread(lambda e=err: messagebox.showinfo("No Subtitles Available", e))
                elif not is_abort:
                    self.run_on_main_thread(lambda e=err: messagebox.showerror("Subtitle Download Failed", e))
            except Exception as exc:
                self._log(f"\n[Unexpected Error] {exc}")
                _progress_cb(0.0, "An unexpected error occurred.")
                self.run_on_main_thread(lambda e=str(exc): messagebox.showerror("Unexpected Error", e))
            finally:
                self._active_downloads.pop(sub_item_id, None)
                def _restore():
                    try:
                        self.subtitle_btn.configure(state="normal", text="Download Subtitles")
                    except Exception:
                        pass
                    if not self._active_downloads:
                        self._set_status("done" if saved_subs_ref else "error")
                        self.abort_btn.configure(state="disabled")
                self.run_on_main_thread(_restore)

        threading.Thread(target=_worker, daemon=True).start()

    def _start_download_item(self, item: dict, is_queue_batch: bool = False):
        item_id = item["id"]

        # Already downloading this item? Skip.
        if item_id in self._active_downloads:
            return

        # Create a fresh engine instance per download
        engine = OmniStreamEngine()
        self._active_downloads[item_id] = engine

        item["status"] = "Downloading"
        item["progress_pct"] = 0.0
        item["progress_text"] = "Downloading…  ·  0% done  ·  100% left"
        item["metrics"] = {
            "status": "Downloading...",
            "percent": "0%",
            "size": "Calculating...",
            "speed": "0.0 MB/s",
            "time": "Calculating...",
            "left": "100% remaining",
        }
        self._item_target_pct[item_id] = 0.0
        self._item_display_pct[item_id] = 0.0

        # Top progress bar: assign to first download or keep existing
        if self._active_item_id is None:
            self._active_item_id = item_id
            self._display_pct = 0.0
            self._target_pct = 0.0
            self._anim_start_pct = 0.0
            self._anim_start_time = time.time()
            self.progress_bar.set(0.0)
            self.progress_bar.configure(progress_color=ACCENT_CYAN)
            try:
                self.prog_name_lbl.configure(text=item.get("title") or "Video Stream")
                self.prog_status_lbl.configure(text="Downloading...")
                self.prog_percent_lbl.configure(text="0%", text_color=ACCENT_CYAN)
                self.prog_size_lbl.configure(text="Calculating...")
                self.prog_time_lbl.configure(text="Calculating...")
                self.prog_speed_lbl.configure(text="0.0 MB/s")
                self.prog_left_lbl.configure(text="100% remaining")
            except Exception:
                pass

        self._request_queue_refresh()  # Throttled: safe to defer this slightly

        # Keep start button enabled so more downloads can be started concurrently
        self.start_btn.configure(state="normal", fg_color=ACCENT_PRIMARY, text="Start Download", image=self.icons["play"])
        self.abort_btn.configure(state="normal")
        self._set_status("downloading")

        def _progress_cb(pct: float, msg: str):
            self._set_progress(pct, msg, item_id)

        def _worker():
            status = "Completed"
            saved_out = None
            try:
                item_mode = item.get("mode") or self.download_mode
                is_netflix_mode = (item_mode == "netflix_rename")
                netflix_id = None
                resolved_title = None

                if is_netflix_mode:
                    if item.get("user_specified_title"):
                        self._log(f"\n[Netflix Mode] User custom title preserved: '{item['title']}'")
                    else:
                        netflix_id = item.get("netflix_id") or extract_netflix_id(item["title"]) or extract_netflix_id(item["input"])
                        if netflix_id:
                            self._log(f"\n[Netflix Mode] Detected Netflix ID: {netflix_id}")
                            self._log(f"  Searching online for official movie/series title...")
                            _progress_cb(0.0, "Resolving title…  ·  0% done  ·  100% left")
                            resolved_title = resolve_netflix_title(netflix_id, log_callback=self._log)
                            if resolved_title:
                                item["resolved_title"] = resolved_title
                                self._log(f"  [Netflix Mode] Identified title: '{resolved_title}'")
                            else:
                                self._log(f"  [Netflix Mode] Notice: Could not resolve title online. Original name will be kept.")
                        else:
                            self._log(f"\n[Netflix Mode] Notice: No Netflix ID detected in source.")

                self._log(f"\n[Task] Starting download: {item['title']}")
                saved_out = engine.run_download(
                    input_text=item["input"],
                    save_name=item["title"] if item["title"] not in ("", "Video") else "",
                    save_dir=item["save_dir"],
                    resolution=item["resolution"],
                    audio_choice=item["audio"],
                    include_subtitles=item.get("include_subtitles", True),
                    sub_format=item.get("sub_format", "SRT"),
                    sub_lang=item.get("sub_lang", "all"),
                    log_callback=self._log,
                    progress_callback=_progress_cb,
                )

                # Post-download Netflix rename step
                if is_netflix_mode and saved_out and os.path.exists(saved_out) and not item.get("user_specified_title"):
                    target_rename = resolved_title or item.get("resolved_title")
                    if not target_rename and netflix_id:
                        target_rename = resolve_netflix_title(netflix_id, log_callback=self._log)

                    if target_rename:
                        orig_dir = os.path.dirname(saved_out)
                        orig_ext = os.path.splitext(saved_out)[1]
                        unique_dest = get_non_conflicting_path(orig_dir, f"{target_rename}{orig_ext}")
                        try:
                            os.rename(saved_out, unique_dest)
                            self._log(f"\n[Netflix Rename] Auto-renamed successfully:")
                            self._log(f"  Original : {os.path.basename(saved_out)}")
                            self._log(f"  Renamed  : {os.path.basename(unique_dest)}")
                            saved_out = unique_dest
                            item["title"] = target_rename
                        except Exception as ren_exc:
                            self._log(f"  [Netflix Rename] Warning: Rename failed ({ren_exc}). Original file kept.")
                    else:
                        self._log(f"\n[Netflix Rename] Original filename preserved: {os.path.basename(saved_out)}")

                basename = os.path.basename(saved_out) if saved_out else "output file"
                _progress_cb(100.0, f"Saved: {basename}")
                if not is_queue_batch:
                    self.run_on_main_thread(lambda p=saved_out: messagebox.showinfo(
                        "Download Complete", f"File saved successfully.\n\n{p}"))
            except RuntimeError as exc:
                err = str(exc)
                is_abort = "abort" in err.lower() or "cancel" in err.lower()
                is_drm = "drm-protected" in err.lower() or "drm protected" in err.lower() or "drm" in err.lower()
                if is_drm:
                    status = "Failed"
                    progress_msg = "This stream is DRM-protected and not supported."
                    item["progress_text"] = progress_msg
                    if "metrics" in item and isinstance(item["metrics"], dict):
                        item["metrics"]["status"] = "This stream is DRM-protected and not supported."
                elif is_abort:
                    status = "Cancelled"
                    progress_msg = "Cancelled"
                else:
                    status = "Failed"
                    progress_msg = f"Failed: {err[:80]}"
                self._log(f"\n[{status}] {err}")
                _progress_cb(0.0, progress_msg)
                if not is_queue_batch and not is_abort:
                    err_title = "DRM Protected Stream" if is_drm else "Download Failed"
                    self.run_on_main_thread(lambda e=err, t=err_title: messagebox.showerror(t, e))
            except Exception as exc:
                status = "Failed"
                self._log(f"\n[Unexpected Error] {exc}")
                _progress_cb(0.0, "An unexpected error occurred.")
                if not is_queue_batch:
                    self.run_on_main_thread(lambda e=str(exc): messagebox.showerror("Unexpected Error", e))
            finally:
                self.log_queue.put(("queue_item_finished", {
                    "id": item_id,
                    "status": status,
                    "saved_file": saved_out,
                    "is_queue_batch": is_queue_batch
                }))

        threading.Thread(target=_worker, daemon=True).start()


_single_instance_mutex = None


def _check_single_instance() -> bool:
    """Ensure only one instance runs using a Win32 Named Mutex; focus existing if already open."""
    global _single_instance_mutex
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183

        mutex_name = "Local\\OmniStreamPro_App_SingleInstance_Mutex"
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        last_err = kernel32.GetLastError()
        if last_err == ERROR_ALREADY_EXISTS:
            # Another instance is already running — send focus request via bridge server
            try:
                import urllib.request
                _token = ""
                try:
                    from extension_manager import get_or_create_bridge_token
                    _token = get_or_create_bridge_token()
                except Exception:
                    pass
                _hdrs = {"Content-Type": "application/json", "Host": "127.0.0.1:28795"}
                if _token:
                    _hdrs["X-OmniStream-Token"] = _token
                req = urllib.request.Request(
                    "http://127.0.0.1:28795/focus",
                    data=b"{}",
                    headers=_hdrs,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=0.8):
                    pass
            except Exception:
                pass
            return False

        # First instance — retain mutex handle for lifetime of process
        _single_instance_mutex = handle
    except Exception:
        pass
    return True


if __name__ == "__main__":
    if not _check_single_instance():
        sys.exit(0)
    app = OmniStreamApp()
    app.mainloop()
