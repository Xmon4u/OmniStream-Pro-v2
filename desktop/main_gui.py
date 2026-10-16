"""
OmniStream Pro v2.0.0
Universal Multi-Audio HLS/M3U8 Stream Downloader & Multiplexer
Features: IDM-Style Batch Queue, "Download All", Extension Bridge, and Multi-Audio MKV Muxing.
Author: XMON4U (https://github.com/Xmon4u)
"""

import math
import os
import sys
import queue
import time
import threading
import webbrowser
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
    get_last_launch_error
)

# CustomTkinter Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Color Palette & Design Tokens ─────────────────────────────────────────────
BG_ROOT        = "#080c14"
BG_HEADER      = "#0b1220"
BG_CARD        = "#0f172a"
BG_CARD2       = "#131d33"
BG_INPUT       = "#060911"
BG_TERMINAL    = "#030712"
ACCENT_PRIMARY = "#6366f1"
ACCENT_HOVER   = "#4f46e5"
ACCENT_CYAN    = "#06b6d4"
ACCENT_GLOW    = "#38bdf8"
ACCENT_EMERALD = "#10b981"
ACCENT_ROSE    = "#f43f5e"
ACCENT_AMBER   = "#f59e0b"
BORDER_MAIN    = "#1e293b"
BORDER_SUB     = "#162032"
TEXT_TITLE     = "#f8fafc"
TEXT_BODY      = "#94a3b8"
TEXT_MUTED     = "#64748b"
TEXT_LOG       = "#38bdf8"
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
                if mode:
                    self.btn_launch.configure(text="Chrome opened — adding the extension")
                    self._poll_connection()
                else:
                    self.btn_launch.configure(text=err or "Could not add the extension")
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
                self.after(0, lambda: (
                    self.btn_launch.configure(text=label, fg_color="#065f46"),
                    self.parent._poll_auto_setup_connection(0) if hasattr(self.parent, "_poll_auto_setup_connection") else None
                ))
            else:
                self.after(0, lambda: (
                    open_chrome_extensions(),
                    open_extension_folder()
                ))
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
        self.title("OmniStream Pro v2.0 — IDM-Grade Stream Downloader")

        # Responsive sizing: use 80% of screen, but cap to comfortable defaults
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        win_w = min(1020, max(900, int(sw * 0.75)))
        win_h = min(780, max(680, int(sh * 0.80)))
        x = (sw - win_w) // 2
        y = max(0, (sh - win_h) // 2 - 20)
        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.minsize(860, 640)
        self.configure(fg_color=BG_ROOT)
        self.overrideredirect(True)

        apply_window_icon(self, BASE_DIR)
        self.icons = build_icon_set(BASE_DIR)
        self._chrome = RoundedFrame(self, radius=18)

        self.engine           = OmniStreamEngine()
        self.log_queue        = queue.Queue()
        self.is_downloading   = False
        self.queue_items      = []  # list of dicts
        self.is_queue_running = False
        self.current_item_id  = None
        self.item_progress_bars = {}  # item_id -> (CTkProgressBar, CTkLabel)
        self._display_pct = 0.0
        self._target_pct = 0.0
        self._progress_pulse_on = False
        self._progress_anim_job = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self.after(30, self._finish_window_chrome)
        self._poll_log_queue()
        self._tick_progress_animation()
        self._start_dependency_check()
        self._start_bridge_server()
        self.after(800, self._check_extension_prompt)

    def _on_close(self):
        """Gracefully stop bridge server and clean up before exit."""
        try:
            if hasattr(self, 'bridge') and self.bridge:
                self.bridge.stop()
        except Exception:
            pass
        self.destroy()

    def _check_extension_prompt(self):
        def _bg_check():
            try:
                deployed = deploy_extension_files()
                copy_path_to_clipboard(deployed)
                if extension_is_live():
                    self.after(0, lambda: self.update_bridge_status(True))
                else:
                    self.after(0, self._auto_setup_extension)
            except Exception:
                pass
        threading.Thread(target=_bg_check, daemon=True).start()

    def _auto_setup_extension(self):
        """Maximum Automation: Smart multi-strategy Chrome extension auto-setup."""
        self._log("[Auto-Setup] Initiating automated Chrome extension setup...")

        def _bg_launch():
            browser_exe = get_browser_executable()
            if not browser_exe:
                self.after(0, lambda: self.show_banner(
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
                self.after(0, lambda m=msg: (
                    self._log(f"[Auto-Setup] {m}"),
                    self.show_banner(m, level="info", show_btn=False),
                    self._poll_auto_setup_connection(attempts=0)
                ))
            else:
                err = get_last_launch_error() or "Chrome could not load the extension."
                self.after(0, lambda e=err: (
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
                self.after(0, lambda: (
                    self.show_banner(
                        "Chrome extension connected. Ready to capture streams.",
                        level="success", show_btn=False
                    ),
                    self.update_bridge_status(True),
                    self.after(4000, self.hide_banner)
                ))
                return
            # Poll for up to 30 seconds (first 10 checks every 2s, then every 5s)
            delay = 2000 if attempts < 10 else 5000
            max_attempts = 20
            if attempts < max_attempts:
                self.after(delay, lambda: self._poll_auto_setup_connection(attempts + 1))
            else:
                self.after(0, lambda: self.show_banner(
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
        hdr = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=64)
        hdr.grid(row=ROW_HEADER, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="", image=self.icons["logo"]).grid(
            row=0, column=0, padx=(16, 10), pady=8
        )

        title_box = ctk.CTkFrame(hdr, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", pady=8)

        ctk.CTkLabel(
            title_box, text="OmniStream Pro",
            font=ctk.CTkFont(family=FONT_MAIN, size=16, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

        ctk.CTkLabel(
            title_box, text=" v2.0 PRO ",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            fg_color="#1e1b4b", text_color="#a5b4fc", corner_radius=6
        ).pack(side="left", padx=(8, 0))

        header_actions = ctk.CTkFrame(hdr, fg_color="transparent")
        header_actions.grid(row=0, column=2, padx=(8, 8), pady=0, sticky="e")

        # Status badge only — Chrome/extension setup uses the banner when needed
        self.status_badge = ctk.CTkLabel(
            header_actions, text="Engine Ready",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=ACCENT_EMERALD,
            fg_color=BG_CARD, corner_radius=18, padx=14, pady=6
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

    def _caption_btn(self, parent, glyph, command, danger=False):
        hover = "#e11d48" if danger else "#1e293b"
        button = ctk.CTkButton(
            parent, text=glyph, width=46, height=32,
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
            self.after(0, _ui)
        threading.Thread(target=_bg, daemon=True).start()

    def update_bridge_status(self, is_active: bool):
        """Update extension bridge connection status badge."""
        if is_active:
            self.bridge_badge.configure(text="Bridge  ·  Active", text_color=ACCENT_EMERALD)
        else:
            self.bridge_badge.configure(text="Bridge  ·  Standby", text_color=ACCENT_AMBER)

    # ── Card 1: Input Source ──────────────────────────────────────────────────
    def _build_input_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER_MAIN)
        card.grid(row=ROW_INPUT, column=0, sticky="ew", padx=18, pady=(10, 5))
        card.grid_columnconfigure(0, weight=1)

        # Top row
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(10, 5))

        ctk.CTkLabel(
            top, text="Stream source", image=self.icons["stream"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(side="left")

        ctk.CTkLabel(
            top, text="  Auto-parses cURL bash/cmd, M3U8, MPD, MP4, and MKV links",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED
        ).pack(side="left")

        ctk.CTkButton(
            top, text="Paste", image=self.icons["paste"], compound="left", width=92, height=28,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), corner_radius=6,
            command=self._paste_clipboard
        ).pack(side="right")

        # Input Box
        self.input_box = ctk.CTkTextbox(
            card, height=66,
            font=ctk.CTkFont(family=FONT_CODE, size=10),
            fg_color=BG_INPUT, text_color="#c8deff",
            border_width=1, border_color=BORDER_SUB, corner_radius=8
        )
        self.input_box.pack(fill="x", padx=16, pady=(0, 10))

    # ── Card 2: Configuration ─────────────────────────────────────────────────
    def _build_options_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER_MAIN)
        card.grid(row=ROW_OPTIONS, column=0, sticky="ew", padx=18, pady=(0, 5))
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(3, weight=1)

        def lbl(row, col, text):
            ctk.CTkLabel(
                card, text=text,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                text_color=TEXT_BODY
            ).grid(row=row, column=col, sticky="w", padx=(16, 8), pady=6)

        entry_kw = dict(
            fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=32, text_color=TEXT_TITLE,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=8
        )
        menu_kw = dict(
            fg_color=BG_INPUT, button_color=BORDER_MAIN,
            button_hover_color=ACCENT_PRIMARY,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_MAIN,
            height=32,
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_TITLE, corner_radius=8
        )

        # Row 0: Title & Resolution
        lbl(0, 0, "Title (optional)")
        self.filename_entry = ctk.CTkEntry(
            card, placeholder_text="Leave blank to auto-detect", **entry_kw
        )
        self.filename_entry.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=6)

        lbl(0, 2, "Resolution")
        self.res_menu = ctk.CTkOptionMenu(
            card,
            values=["1080p (Full HD - Recommended)", "720p (HD Quality)", "480p (SD Quality)", "Best Available", "Audio Only (No Video)"],
            **menu_kw
        )
        self.res_menu.set("1080p (Full HD - Recommended)")
        self.res_menu.grid(row=0, column=3, sticky="ew", padx=(0, 16), pady=6)

        # Row 1: Save Folder & Audio Selection
        lbl(1, 0, "Save Folder")
        fr = ctk.CTkFrame(card, fg_color="transparent")
        fr.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=6)
        fr.grid_columnconfigure(0, weight=1)

        self.folder_entry = ctk.CTkEntry(fr, **entry_kw)
        self.folder_entry.grid(row=0, column=0, sticky="ew")
        self.folder_entry.insert(0, DEFAULT_SAVE_DIR)

        ctk.CTkButton(
            fr, text="Browse", width=68, height=32,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=8,
            command=self._browse_folder
        ).grid(row=0, column=1, padx=(6, 0))

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
        self.audio_menu.grid(row=1, column=3, sticky="ew", padx=(0, 16), pady=6)

    # ── Action Buttons ────────────────────────────────────────────────────────
    def _build_action_buttons(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=ROW_ACTIONS, column=0, sticky="ew", padx=18, pady=(4, 4))
        bar.grid_columnconfigure(0, weight=1, minsize=240)
        bar.grid_columnconfigure(1, weight=0, minsize=100)

        self.start_btn = ctk.CTkButton(
            bar,
            text="Start Download", image=self.icons["play"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white",
            command=self._start_download
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.abort_btn = ctk.CTkButton(
            bar,
            text="Stop", image=self.icons["stop"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#881337", hover_color="#9f1239",
            text_color="#fecdd3",
            state="disabled",
            command=self._abort_download
        )
        self.abort_btn.grid(row=0, column=1, sticky="ew")

    # ── Progress Row ──────────────────────────────────────────────────────────
    def _build_progress_row(self):
        prog = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, border_width=1, border_color=BORDER_MAIN)
        prog.grid(row=ROW_PROGRESS, column=0, sticky="ew", padx=18, pady=(0, 5))
        prog.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            prog, height=6, corner_radius=3,
            progress_color=ACCENT_CYAN, fg_color=BG_INPUT
        )
        self.progress_bar.pack(fill="x", padx=14, pady=(8, 3))
        self.progress_bar.set(0)

        self.progress_lbl = ctk.CTkLabel(
            prog,
            text="Ready — Paste a stream URL above or send links from the Chrome extension.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED, anchor="w"
        )
        self.progress_lbl.pack(anchor="w", padx=14, pady=(0, 6))

    # ── Container & Queue View (IDM Experience) ───────────────────────────────
    def _build_container_and_queue(self):
        self.main_container = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER_MAIN)
        self.main_container.grid(row=ROW_CONTAINER, column=0, sticky="nsew", padx=18, pady=(0, 5))
        self.main_container.grid_rowconfigure(1, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # Tab Selector Bar
        tab_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        tab_bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))

        # Switch Buttons
        btn_box = ctk.CTkFrame(tab_bar, fg_color="transparent")
        btn_box.pack(side="left")

        self.btn_view_queue = ctk.CTkButton(
            btn_box, text="Download Queue (0)", image=self.icons["queue"], compound="left", width=188, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=ACCENT_PRIMARY, text_color="white", corner_radius=6,
            command=self._show_queue_view
        )
        self.btn_view_queue.pack(side="left", padx=(0, 6))

        self.btn_view_terminal = ctk.CTkButton(
            btn_box, text="Terminal", image=self.icons["terminal"], compound="left", width=120, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=BG_CARD2, text_color=TEXT_BODY, corner_radius=6,
            command=self._show_terminal_view
        )
        self.btn_view_terminal.pack(side="left")

        # Terminal-only actions (hidden on Queue view)
        self.term_actions = ctk.CTkFrame(tab_bar, fg_color="transparent")
        ctk.CTkButton(
            self.term_actions, text="Clear Logs", width=86, height=24,
            font=ctk.CTkFont(size=10), fg_color=BG_CARD2,
            hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_MUTED, corner_radius=5,
            command=lambda: self.log_textbox.delete("1.0", "end")
        ).pack(side="right")

        # ── View 1: Queue Manager Frame (Default View) ──
        self.queue_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_frame.grid_rowconfigure(1, weight=1)

        q_tool = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        q_tool.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 8))

        self.start_queue_btn = ctk.CTkButton(
            q_tool, text="Download All", image=self.icons["play"], compound="left",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            fg_color="#059669", hover_color="#047857", text_color="white",
            width=150, height=32, corner_radius=8, command=self._start_queue_processing
        )
        self.start_queue_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            q_tool, text="Clear All",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=BG_CARD2, hover_color="#7f1d1d", text_color="#fca5a5",
            border_width=1, border_color=BORDER_SUB,
            width=80, height=32, corner_radius=8, command=self._clear_all_queue
        ).pack(side="left")

        self.queue_stats_lbl = ctk.CTkLabel(
            q_tool, text="Queue: 0 items",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED
        )
        self.queue_stats_lbl.pack(side="right", padx=8)

        # Scrollable items list
        self.queue_scroll = ctk.CTkScrollableFrame(
            self.queue_frame, fg_color=BG_INPUT,
            border_width=1, border_color=BORDER_SUB, corner_radius=8
        )
        self.queue_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # ── View 2: Terminal Log Textbox ──
        self.log_textbox = ctk.CTkTextbox(
            self.main_container,
            font=ctk.CTkFont(family=FONT_CODE, size=10),
            fg_color=BG_TERMINAL, text_color=TEXT_LOG,
            corner_radius=8, border_width=1, border_color=BORDER_SUB,
            wrap="none"
        )
        # Not gridded by default; queue view is shown first.

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
            text="OmniStream Pro v2.0.2  •  Developed by XMON4U  •  GitHub Repository",
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
        self.log_queue.put(("log", text))

    def _set_progress(self, pct: float, msg: str):
        self.log_queue.put(("progress", (pct, msg)))

    def _format_progress_label(self, pct: float, msg: str) -> str:
        pct = max(0.0, min(100.0, float(pct)))
        left = max(0.0, 100.0 - pct)
        base = (msg or "").strip()
        # Engine already sends a rich status line — keep it when present.
        if "% done" in base or "% left" in base:
            return base
        if pct >= 100:
            return base or "100% done  ·  Complete"
        if base:
            return f"{pct:.0f}% done  ·  {left:.0f}% left  ·  {base}"
        return f"{pct:.0f}% done  ·  {left:.0f}% left"

    def _apply_progress_ui(self, pct: float, status_text: str):
        pct = max(0.0, min(100.0, float(pct)))
        self._target_pct = pct
        self._progress_pulse_on = self.is_downloading and pct < 1.0
        label = self._format_progress_label(pct, status_text)
        try:
            self.progress_lbl.configure(text=label)
        except Exception:
            pass

        if self.current_item_id:
            for item in self.queue_items:
                if item["id"] == self.current_item_id:
                    item["progress_pct"] = pct
                    item["progress_text"] = label
                    break
            if self.current_item_id in self.item_progress_bars:
                _pbar, plbl = self.item_progress_bars[self.current_item_id]
                try:
                    plbl.configure(
                        text=label,
                        text_color=ACCENT_CYAN if pct < 100 else ACCENT_EMERALD,
                    )
                except Exception:
                    pass

    def _tick_progress_animation(self):
        """Smooth bar fill + gentle pulse while waiting for the first % update."""
        try:
            if self._progress_pulse_on and self.is_downloading:
                # Soft indeterminate pulse between ~4% and ~18% until real progress arrives.
                phase = (time.time() * 2.4) % (2 * math.pi)
                pulse = 0.04 + 0.14 * (0.5 + 0.5 * math.sin(phase))
                shown = pulse
            else:
                # Ease displayed value toward target for a live timeline feel.
                delta = self._target_pct - self._display_pct
                if abs(delta) < 0.15:
                    self._display_pct = self._target_pct
                else:
                    self._display_pct += delta * 0.22
                shown = max(0.0, min(1.0, self._display_pct / 100.0))

            self.progress_bar.set(shown)
            if self.current_item_id and self.current_item_id in self.item_progress_bars:
                pbar, _plbl = self.item_progress_bars[self.current_item_id]
                try:
                    pbar.set(shown)
                    # Cyan glow while active
                    if self.is_downloading:
                        pbar.configure(progress_color=ACCENT_CYAN)
                except Exception:
                    pass
        except Exception:
            pass
        self._progress_anim_job = self.after(40, self._tick_progress_animation)

    def _poll_log_queue(self):
        processed = 0
        while not self.log_queue.empty() and processed < 50:
            msg_type, data = self.log_queue.get_nowait()
            processed += 1
            if msg_type == "log":
                self.log_textbox.insert("end", data + "\n")
                self.log_textbox.see("end")
            elif msg_type == "progress":
                pct, status_text = data
                self._apply_progress_ui(pct, status_text)
            elif msg_type == "bridge_connected":
                self.update_bridge_status(True)
            elif msg_type == "bridge_job":
                self._handle_bridge_job(data)
            elif msg_type == "bridge_batch_jobs":
                self._handle_bridge_batch_jobs(data)
            elif msg_type == "start_queue_requested":
                self._start_queue_processing()
            elif msg_type == "queue_item_finished":
                self._handle_queue_item_finished(data)

        self.after(60, self._poll_log_queue)

    def _set_status(self, state: str):
        def _apply():
            states = {
                "ready":       ("Engine Ready", ACCENT_EMERALD),
                "downloading": ("Downloading", ACCENT_CYAN),
                "done":        ("Task Complete", ACCENT_EMERALD),
                "error":       ("Task Error", ACCENT_ROSE),
                "aborted":     ("Stopped", ACCENT_AMBER),
            }
            text, color = states.get(state, ("Ready", ACCENT_EMERALD))
            self.status_badge.configure(text=text, text_color=color)
        self.after(0, _apply)

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

        item = self._add_to_queue(raw_input=curl_or_url, custom_title=title, auto_show_tab=True)
        self._log(f"\n[Extension Bridge] Received stream: {title or 'Video Stream'}")
        self._log(f"  Source queued for IDM batch download.")

        if auto_start and not self.is_downloading:
            self._start_download_item(item, is_queue_batch=False)

    def _handle_bridge_batch_jobs(self, data: dict):
        self._bring_to_foreground()
        items = data.get("items", [])
        added_count = 0
        for it in items:
            title = it.get("title", "").strip()
            curl_or_url = it.get("curl") or it.get("url", "")
            if curl_or_url:
                self._add_to_queue(raw_input=curl_or_url, custom_title=title, auto_show_tab=False)
                added_count += 1

        self._show_queue_view()
        self._log(f"\n[Extension Bridge] Successfully imported {added_count} streams into Download Queue.")
        self._log(f"  Click 'Download All' to download the entire queue sequentially.")

    # ── Queue Operations ──────────────────────────────────────────────────────
    def _add_to_queue(self, raw_input: str, custom_title: str = "", auto_show_tab: bool = False):
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
        display_title = custom_title or f"OmniStream_{len(self.queue_items) + 1}"

        item = {
            "id": f"q_{int(time.time()*1000)}_{len(self.queue_items)}",
            "title": display_title,
            "input": raw_input,
            "save_dir": save_dir,
            "resolution": resolution,
            "audio": audio_choice,
            "status": "Waiting",
            "saved_file": None,
            "progress_pct": 0.0,
            "progress_text": "Ready in queue",
        }
        self.queue_items.append(item)
        self.btn_view_queue.configure(text=f"Download Queue ({len(self.queue_items)})")

        if auto_show_tab:
            self._show_queue_view()
        else:
            self._refresh_queue_ui()
        return item

    def _refresh_queue_ui(self):
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()

        self.item_progress_bars.clear()

        total = len(self.queue_items)
        waiting = len([it for it in self.queue_items if it["status"] == "Waiting"])
        done = len([it for it in self.queue_items if it["status"] == "Completed"])
        self.queue_stats_lbl.configure(text=f"Queue: {total} total · {waiting} waiting · {done} done")
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

            ctk.CTkLabel(
                detail_frame, text=item["title"],
                font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
                text_color=TEXT_TITLE, anchor="w"
            ).pack(anchor="w")

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

            item_pbar = ctk.CTkProgressBar(
                prog_row, height=6, corner_radius=3,
                progress_color=ACCENT_CYAN if item["status"] == "Downloading" else (
                    ACCENT_EMERALD if item["status"] == "Completed" else BG_INPUT
                ),
                fg_color=BG_INPUT
            )
            item_pbar.grid(row=0, column=0, sticky="ew", pady=(2, 2))
            stored_pct = float(item.get("progress_pct") or 0.0)
            if item["status"] == "Completed":
                item_pbar.set(1.0)
            elif item["status"] == "Downloading":
                item_pbar.set(max(0.02, min(1.0, stored_pct / 100.0)))
            else:
                item_pbar.set(0.0)

            if item["status"] == "Completed":
                prog_text = item.get("progress_text") or "100% done  ·  Finished"
                prog_color = ACCENT_EMERALD
            elif item["status"] == "Failed":
                prog_text = item.get("progress_text") or "Failed"
                prog_color = ACCENT_ROSE
            elif item["status"] == "Downloading":
                prog_text = item.get("progress_text") or "Starting…  ·  0% done  ·  100% left"
                prog_color = ACCENT_CYAN
            else:
                prog_text = "Ready in queue"
                prog_color = TEXT_MUTED

            item_plbl = ctk.CTkLabel(
                prog_row,
                text=prog_text,
                font=ctk.CTkFont(family=FONT_MAIN, size=9),
                text_color=prog_color,
                anchor="w"
            )
            item_plbl.grid(row=1, column=0, sticky="w")

            self.item_progress_bars[item["id"]] = (item_pbar, item_plbl)

            # Right action buttons
            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.grid(row=0, column=2, rowspan=2, padx=8, pady=6, sticky="e")

            if item["status"] in ("Waiting", "Failed", "Paused"):
                ctk.CTkButton(
                    btn_box, text="Download", image=self.icons["download"], compound="left", width=108, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
                    command=lambda it=item: self._download_single_queue_item(it)
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

            ctk.CTkButton(
                btn_box, text="", image=self.icons["close"], width=28, height=26,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                fg_color=BG_CARD, hover_color="#7f1d1d", text_color="#fca5a5",
                command=lambda it=item: self._remove_queue_item(it)
            ).pack(side="left", padx=2)

    def _remove_queue_item(self, item):
        if item in self.queue_items:
            self.queue_items.remove(item)
            self._refresh_queue_ui()

    def _clear_all_queue(self):
        if self.is_queue_running or self.is_downloading:
            messagebox.showwarning("Queue Busy", "Stop the current download first.")
            return
        self.queue_items = []
        self._refresh_queue_ui()

    def _download_single_queue_item(self, item):
        if self.is_downloading:
            messagebox.showwarning("Busy", "A download is already in progress.")
            return
        self._start_download_item(item, is_queue_batch=False)

    def _start_queue_processing(self):
        if self.is_downloading:
            messagebox.showwarning("Busy", "A download is already running.")
            return

        waiting_items = [it for it in self.queue_items if it["status"] in ("Waiting", "Failed", "Paused")]
        if not waiting_items:
            messagebox.showinfo("Queue", "No waiting items in the queue.")
            return

        self.is_queue_running = True
        self.start_queue_btn.configure(text="Downloading", state="disabled")
        first_item = waiting_items[0]
        self._start_download_item(first_item, is_queue_batch=True)

    def _handle_queue_item_finished(self, data: dict):
        item_id = data.get("id")
        status = data.get("status")
        saved_file = data.get("saved_file")
        is_queue_batch = data.get("is_queue_batch", False)

        for it in self.queue_items:
            if it["id"] == item_id:
                it["status"] = status
                if saved_file:
                    it["saved_file"] = saved_file
                if status == "Completed":
                    it["progress_pct"] = 100.0
                    it["progress_text"] = "100% done  ·  Finished"
                elif status == "Failed":
                    it["progress_text"] = it.get("progress_text") or "Failed"
                break

        self._progress_pulse_on = False
        if not self.is_downloading:
            self._target_pct = 100.0 if status == "Completed" else self._target_pct
            self._display_pct = self._target_pct

        self._refresh_queue_ui()

        if is_queue_batch and self.is_queue_running:
            waiting = [it for it in self.queue_items if it["status"] == "Waiting"]
            if waiting:
                next_item = waiting[0]
                self._start_download_item(next_item, is_queue_batch=True)
            else:
                self.is_queue_running = False
                self.start_queue_btn.configure(text="Download All", state="normal")
                messagebox.showinfo("Queue Complete", "All items in the download queue have been saved successfully!")

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
        if self.is_downloading:
            self._log("\n[Action] Sending stop signal to download engine...")
            self.engine.abort()
            self.is_queue_running = False
            self.start_queue_btn.configure(text="Download All", state="normal")

    def _start_download(self):
        if self.is_downloading:
            return

        raw_input = self.input_box.get("1.0", "end").strip()
        if not raw_input:
            messagebox.showwarning("Missing Input", "Please paste a cURL command or direct M3U8 link first.")
            return

        filename = self.filename_entry.get().strip()
        save_dir = self.folder_entry.get().strip()

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

        item = {
            "id": "direct_input",
            "title": filename or "Video",
            "input": raw_input,
            "save_dir": save_dir,
            "resolution": resolution,
            "audio": audio_choice,
            "status": "Downloading",
            "saved_file": None,
            "progress_pct": 0.0,
            "progress_text": "Starting…  ·  0% done  ·  100% left",
        }
        self._start_download_item(item, is_queue_batch=False)

    def _start_download_item(self, item: dict, is_queue_batch: bool = False):
        self.is_downloading = True
        self.current_item_id = item["id"]
        item["status"] = "Downloading"
        item["progress_pct"] = 0.0
        item["progress_text"] = "Starting…  ·  0% done  ·  100% left"
        self._display_pct = 0.0
        self._target_pct = 0.0
        self._progress_pulse_on = True
        self._refresh_queue_ui()

        self.start_btn.configure(state="disabled", fg_color="#312e81", text="Downloading")
        self.abort_btn.configure(state="normal")
        self._set_status("downloading")
        self.progress_bar.set(0.02)
        self.progress_lbl.configure(text=item["progress_text"])
        self._set_progress(0.0, item["progress_text"])

        def _worker():
            status = "Completed"
            saved_out = None
            try:
                self._log(f"\n[Task] Starting download: {item['title']}")
                saved_out = self.engine.run_download(
                    input_text=item["input"],
                    save_name=item["title"] if item["title"] != "Video" else "",
                    save_dir=item["save_dir"],
                    resolution=item["resolution"],
                    audio_choice=item["audio"],
                    log_callback=self._log,
                    progress_callback=self._set_progress,
                )
                self._set_status("done")
                basename = os.path.basename(saved_out) if saved_out else "output file"
                self._set_progress(100.0, f"Saved: {basename}")
                if not is_queue_batch:
                    self.after(0, lambda p=saved_out: messagebox.showinfo("Download Complete", f"File saved successfully.\n\n{p}"))
            except RuntimeError as exc:
                err = str(exc)
                status = "Failed"
                self._set_status("aborted" if "aborted" in err.lower() else "error")
                self._log(f"\n[Error] {err}")
                self._set_progress(0, f"Failed: {err[:100]}")
                if not is_queue_batch and "aborted" not in err.lower():
                    self.after(0, lambda e=err: messagebox.showerror("Download Failed", e))
            except Exception as exc:
                status = "Failed"
                self._set_status("error")
                self._log(f"\n[Unexpected Error] {exc}")
                self._set_progress(0, "An unexpected error occurred.")
                if not is_queue_batch:
                    self.after(0, lambda e=str(exc): messagebox.showerror("Unexpected Error", e))
            finally:
                self.is_downloading = False
                self.current_item_id = None
                self.after(0, lambda: self.start_btn.configure(state="normal", fg_color=ACCENT_PRIMARY, text="Start Download", image=self.icons["play"]))
                self.after(0, lambda: self.abort_btn.configure(state="disabled"))
                self.log_queue.put(("queue_item_finished", {
                    "id": item["id"],
                    "status": status,
                    "saved_file": saved_out,
                    "is_queue_batch": is_queue_batch
                }))

        threading.Thread(target=_worker, daemon=True).start()


if __name__ == "__main__":
    app = OmniStreamApp()
    app.mainloop()
