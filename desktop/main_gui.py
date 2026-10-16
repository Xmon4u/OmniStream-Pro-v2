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
from tkinter import filedialog, messagebox

import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core_engine import OmniStreamEngine, DEFAULT_SAVE_DIR
from setup_dependencies import ensure_dependencies
from bridge_server import BridgeServer
from extension_manager import (
    deploy_extension_files,
    is_extension_installed,
    mark_extension_installed,
    get_deployed_extension_dir,
    open_chrome_extensions,
    open_extension_folder
)

# CustomTkinter Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Color Palette & Design Tokens ─────────────────────────────────────────────
BG_ROOT        = "#080c14"
BG_HEADER      = "#0c1220"
BG_CARD        = "#101827"
BG_CARD2       = "#0f172a"
BG_INPUT       = "#060911"
BG_TERMINAL    = "#04070d"
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
ROW_INPUT    = 1
ROW_OPTIONS  = 2
ROW_ACTIONS  = 3
ROW_PROGRESS = 4
ROW_CONTAINER= 5
ROW_FOOTER   = 6


class ExtensionSetupDialog(ctk.CTkToplevel):
    """Professional setup modal for Chrome extension onboarding."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Chrome Extension Setup — OmniStream Pro")
        self.geometry("580x420")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        icon_path = os.path.join(BASE_DIR, "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.transient(parent)
        self.grab_set()

        try:
            self.update_idletasks()
            px = parent.winfo_x() + (parent.winfo_width() // 2) - 290
            py = parent.winfo_y() + (parent.winfo_height() // 2) - 210
            self.geometry(f"+{max(0, px)}+{max(0, py)}")
        except Exception:
            pass

        self._build_content()

    def _build_content(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=22, pady=18)

        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        icon_box = ctk.CTkFrame(header, fg_color=ACCENT_PRIMARY, width=38, height=38, corner_radius=10)
        icon_box.pack(side="left", padx=(0, 12))
        icon_box.grid_propagate(False)
        ctk.CTkLabel(icon_box, text="⚡", font=ctk.CTkFont(size=18), text_color="white").place(relx=0.5, rely=0.5, anchor="center")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            title_box, text="Browser Extension Setup",
            font=ctk.CTkFont(family=FONT_MAIN, size=15, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box, text="Connect Google Chrome to enable 1-click video stream capture.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED, anchor="w"
        ).pack(anchor="w")

        # Instruction Card
        card = ctk.CTkFrame(container, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
        card.pack(fill="x", pady=(0, 14))

        step1 = ctk.CTkFrame(card, fg_color="transparent")
        step1.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            step1, text="Step 1:", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            step1, text="Click 'Open Extensions Page' below and turn ON 'Developer mode'.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY
        ).pack(side="left")

        step2 = ctk.CTkFrame(card, fg_color="transparent")
        step2.pack(fill="x", padx=14, pady=(2, 6))
        ctk.CTkLabel(
            step2, text="Step 2:", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            step2, text="Click 'Load unpacked' and select this extension folder:",
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY
        ).pack(side="left")

        ext_dir = get_deployed_extension_dir()
        path_box = ctk.CTkFrame(card, fg_color="transparent")
        path_box.pack(fill="x", padx=14, pady=(2, 14))

        self.path_entry = ctk.CTkEntry(
            path_box,
            fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=32, text_color="#c8deff",
            font=ctk.CTkFont(family=FONT_CODE, size=10), corner_radius=6
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.path_entry.insert(0, ext_dir)
        self.path_entry.configure(state="readonly")

        self.btn_copy_path = ctk.CTkButton(
            path_box, text="Copy Path", width=80, height=32,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY, font=ctk.CTkFont(family=FONT_MAIN, size=11),
            corner_radius=6, command=self._copy_path
        )
        self.btn_copy_path.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            path_box, text="📁", width=36, height=32,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY, font=ctk.CTkFont(size=12),
            corner_radius=6, command=open_extension_folder
        ).pack(side="left")

        # Bottom Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(
            btn_row, text="🌐  Open Extensions Page", width=190, height=36,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            corner_radius=8, command=open_chrome_extensions
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="✓  I've Installed It", width=145, height=36,
            fg_color="#065f46", hover_color="#047857",
            text_color="#a7f3d0", font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            corner_radius=8, command=self._confirm_installed
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Remind Me Later", width=120, height=36,
            fg_color="transparent", hover_color=BG_CARD2,
            text_color=TEXT_MUTED, font=ctk.CTkFont(family=FONT_MAIN, size=11),
            corner_radius=8, command=self.destroy
        ).pack(side="right")

    def _copy_path(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(get_deployed_extension_dir())
            self.btn_copy_path.configure(text="Copied!")
            self.after(1500, lambda: self.btn_copy_path.configure(text="Copy Path"))
        except Exception:
            pass

    def _confirm_installed(self):
        mark_extension_installed()
        self.destroy()


class OmniStreamApp(ctk.CTk):
    """OmniStream Pro v2.0.0 Main Application Window."""

    def __init__(self):
        super().__init__()
        self.title("OmniStream Pro v2.0 — IDM-Grade Stream Downloader")
        self.geometry("1060x880")
        self.minsize(960, 780)
        self.configure(fg_color=BG_ROOT)

        icon_path = os.path.join(BASE_DIR, "app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.engine           = OmniStreamEngine()
        self.log_queue        = queue.Queue()
        self.is_downloading   = False
        self.queue_items      = []  # list of dicts
        self.is_queue_running = False
        self.current_item_id  = None
        self.item_progress_bars = {}  # item_id -> (CTkProgressBar, CTkLabel)

        self._build_ui()
        self._poll_log_queue()
        self._start_dependency_check()
        self._start_bridge_server()
        self.after(600, self._check_extension_prompt)

    def _check_extension_prompt(self):
        try:
            deploy_extension_files()
            if not is_extension_installed():
                ExtensionSetupDialog(self)
        except Exception:
            pass

    # ── UI Layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(ROW_CONTAINER, weight=1)

        self._build_header()
        self._build_input_card()
        self._build_options_card()
        self._build_action_buttons()
        self._build_progress_row()
        self._build_container_and_queue()
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=76)
        hdr.grid(row=ROW_HEADER, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        # Icon box
        icon_box = ctk.CTkFrame(hdr, fg_color=ACCENT_PRIMARY, width=44, height=44, corner_radius=12)
        icon_box.grid(row=0, column=0, rowspan=2, padx=(20, 14), pady=16)
        icon_box.grid_propagate(False)
        ctk.CTkLabel(icon_box, text="⚡", font=ctk.CTkFont(size=22), text_color="white").place(relx=0.5, rely=0.5, anchor="center")

        # Title & Extension Bridge status
        title_box = ctk.CTkFrame(hdr, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="sw", pady=(14, 0))

        ctk.CTkLabel(
            title_box, text="OmniStream Pro  •  Multi-Audio Stream Downloader",
            font=ctk.CTkFont(family=FONT_MAIN, size=18, weight="bold"),
            text_color=TEXT_TITLE
        ).pack(side="left")

        ctk.CTkLabel(
            title_box, text=" v2.0.0 ",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            fg_color="#1e1b4b", text_color="#a5b4fc", corner_radius=6
        ).pack(side="left", padx=(8, 10))

        self.bridge_badge = ctk.CTkLabel(
            title_box, text="🌐 Extension Bridge: Active (127.0.0.1:28795)",
            font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
            text_color=ACCENT_EMERALD, fg_color=BG_CARD,
            corner_radius=12, padx=10, pady=2
        )
        self.bridge_badge.pack(side="left")

        # Subtitle
        ctk.CTkLabel(
            hdr,
            text="IDM-Grade Batch Queue  ·  Lossless Multi-Audio MKV  ·  Browser Extension Integration  ·  16x Acceleration",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_BODY, anchor="w"
        ).grid(row=1, column=1, sticky="nw", pady=(2, 12))

        # Status badge
        self.status_badge = ctk.CTkLabel(
            hdr, text="  ●  Initializing Engine",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=ACCENT_AMBER,
            fg_color=BG_CARD, corner_radius=20, padx=16, pady=6
        )
        self.status_badge.grid(row=0, column=2, rowspan=2, padx=20, pady=16)

    # ── Card 1: Input Source ──────────────────────────────────────────────────
    def _build_input_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=12, border_width=1, border_color=BORDER_MAIN)
        card.grid(row=ROW_INPUT, column=0, sticky="ew", padx=18, pady=(10, 5))
        card.grid_columnconfigure(0, weight=1)

        # Top row
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(10, 5))

        ctk.CTkLabel(
            top, text="Stream Source",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(side="left")

        ctk.CTkLabel(
            top, text="  Paste cURL command or direct M3U8/MP4 link, or send automatically from extension",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
            text_color=TEXT_MUTED
        ).pack(side="left")

        # Top Buttons
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="right")

        ctk.CTkButton(
            btn_row, text="Clear", width=62, height=28,
            fg_color=BG_CARD2, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=6,
            command=self._clear_input
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            btn_row, text="📋  Paste", width=95, height=28,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), corner_radius=6,
            command=self._paste_clipboard
        ).pack(side="right")

        # Input Box
        self.input_box = ctk.CTkTextbox(
            card, height=64,
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
        bar.grid_columnconfigure(0, weight=3)
        bar.grid_columnconfigure(1, weight=2)
        bar.grid_columnconfigure(2, weight=1)
        bar.grid_columnconfigure(3, weight=1)

        # Start Download
        self.start_btn = ctk.CTkButton(
            bar,
            text="▶   Start Download & Mux",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
            text_color="white",
            command=self._start_download
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        # Add to Queue
        self.add_queue_btn = ctk.CTkButton(
            bar,
            text="📥  Add to Queue",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#065f46", hover_color="#047857",
            text_color="#a7f3d0",
            command=self._add_current_to_queue
        )
        self.add_queue_btn.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        # Abort Button
        self.abort_btn = ctk.CTkButton(
            bar,
            text="■  Stop",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            height=40, corner_radius=10,
            fg_color="#881337", hover_color="#9f1239",
            text_color="#fecdd3",
            state="disabled",
            command=self._abort_download
        )
        self.abort_btn.grid(row=0, column=2, sticky="ew", padx=(0, 6))

        # Open Output Folder
        ctk.CTkButton(
            bar,
            text="📁  Folder",
            font=ctk.CTkFont(family=FONT_MAIN, size=12),
            height=40, corner_radius=10,
            fg_color=BG_CARD, hover_color=BORDER_MAIN,
            border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_BODY,
            command=self._open_output_folder
        ).grid(row=0, column=3, sticky="ew")

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
            text="Ready — Paste a stream source above or send links from browser extension.",
            font=ctk.CTkFont(family=FONT_MAIN, size=10),
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
            btn_box, text="📥 IDM Download Queue (0)", width=175, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=ACCENT_PRIMARY, text_color="white", corner_radius=6,
            command=self._show_queue_view
        )
        self.btn_view_queue.pack(side="left", padx=(0, 6))

        self.btn_view_terminal = ctk.CTkButton(
            btn_box, text="🖥️ Terminal Logs", width=125, height=28,
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=BG_CARD2, text_color=TEXT_BODY, corner_radius=6,
            command=self._show_terminal_view
        )
        self.btn_view_terminal.pack(side="left")

        # Right side actions
        self.term_actions = ctk.CTkFrame(tab_bar, fg_color="transparent")
        self.term_actions.pack(side="right")

        ctk.CTkButton(
            self.term_actions, text="Clear Logs", width=70, height=24,
            font=ctk.CTkFont(size=10), fg_color=BG_CARD2,
            hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_MUTED, corner_radius=5,
            command=lambda: self.log_textbox.delete("1.0", "end")
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            self.term_actions, text="Copy Logs", width=70, height=24,
            font=ctk.CTkFont(size=10), fg_color=BG_CARD2,
            hover_color=BORDER_MAIN, border_width=1, border_color=BORDER_SUB,
            text_color=TEXT_MUTED, corner_radius=5,
            command=self._copy_logs
        ).pack(side="right")

        # ── View 1: Queue Manager Frame (Default View) ──
        self.queue_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_frame.grid_rowconfigure(1, weight=1)

        # IDM-style Queue Toolbar
        q_tool = ctk.CTkFrame(self.queue_frame, fg_color="transparent")
        q_tool.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 8))

        self.start_queue_btn = ctk.CTkButton(
            q_tool, text="▶  Download All (Start Queue)",
            font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
            fg_color="#059669", hover_color="#047857", text_color="white",
            height=32, corner_radius=8, command=self._start_queue_processing
        )
        self.start_queue_btn.pack(side="left", padx=(0, 8))

        self.stop_queue_btn = ctk.CTkButton(
            q_tool, text="⏸ Stop Queue",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            fg_color=BG_CARD2, hover_color="#881337", text_color="#fca5a5",
            border_width=1, border_color=BORDER_SUB,
            height=32, corner_radius=8, command=self._stop_queue_processing
        )
        self.stop_queue_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            q_tool, text="🧹 Clear Finished",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=BG_CARD2, hover_color=BORDER_MAIN, text_color=TEXT_BODY,
            border_width=1, border_color=BORDER_SUB,
            height=32, corner_radius=8, command=self._clear_finished_queue
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            q_tool, text="🗑️ Clear All",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            fg_color=BG_CARD2, hover_color="#7f1d1d", text_color="#fca5a5",
            border_width=1, border_color=BORDER_SUB,
            height=32, corner_radius=8, command=self._clear_all_queue
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

    def _show_queue_view(self):
        self.log_textbox.grid_forget()
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.btn_view_queue.configure(fg_color=ACCENT_PRIMARY, text_color="white")
        self.btn_view_terminal.configure(fg_color=BG_CARD2, text_color=TEXT_BODY)
        self._refresh_queue_ui()

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=28)
        footer.grid(row=ROW_FOOTER, column=0, sticky="ew")
        footer.grid_propagate(False)

        ctk.CTkButton(
            footer,
            text="OmniStream Pro v2.0.0  •  Developed by XMON4U  •  GitHub Repository",
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
            self._log("[Bridge] Localhost extension bridge active on 127.0.0.1:28795")
            self.bridge_badge.configure(text="🌐 Extension Bridge: Active (Port 28795)", text_color=ACCENT_EMERALD)
        else:
            self._log("[Bridge] Port 28795 in use by existing instance.")
            self.bridge_badge.configure(text="🌐 Bridge: Secondary", text_color=ACCENT_AMBER)

    # ── Log & Event Dispatcher ────────────────────────────────────────────────
    def _log(self, text: str):
        self.log_queue.put(("log", text))

    def _set_progress(self, pct: float, msg: str):
        self.log_queue.put(("progress", (pct, msg)))

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
                self.progress_bar.set(max(0.0, min(1.0, pct / 100.0)))
                self.progress_lbl.configure(text=status_text)
                if self.current_item_id and self.current_item_id in self.item_progress_bars:
                    pbar, plbl = self.item_progress_bars[self.current_item_id]
                    try:
                        pbar.set(max(0.0, min(1.0, pct / 100.0)))
                        plbl.configure(text=status_text)
                    except Exception:
                        pass
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
        states = {
            "ready":       ("  ●  Engine Ready",     ACCENT_EMERALD),
            "downloading": ("  ●  Downloading...",   ACCENT_CYAN),
            "done":        ("  ●  Task Complete",    ACCENT_EMERALD),
            "error":       ("  ●  Task Error",       ACCENT_ROSE),
            "aborted":     ("  ●  Stopped",          ACCENT_AMBER),
        }
        text, color = states.get(state, ("  ●  Ready", ACCENT_EMERALD))
        self.status_badge.configure(text=text, text_color=color)

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

    # ── Queue Operations (IDM Experience) ─────────────────────────────────────
    def _add_current_to_queue(self):
        raw_input = self.input_box.get("1.0", "end").strip()
        if not raw_input:
            messagebox.showwarning("Missing Input", "Please paste a cURL command or M3U8 link first.")
            return

        filename = self.filename_entry.get().strip()
        self._add_to_queue(raw_input=raw_input, custom_title=filename, auto_show_tab=True)
        messagebox.showinfo("Queue", f"Added to Download Queue:\n{filename or 'Video Stream'}")

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
            "saved_file": None
        }
        self.queue_items.append(item)
        self.btn_view_queue.configure(text=f"📥 IDM Download Queue ({len(self.queue_items)})")

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
        self.btn_view_queue.configure(text=f"📥 IDM Download Queue ({total})")

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
                prog_row, height=4, corner_radius=2,
                progress_color=ACCENT_CYAN, fg_color=BG_INPUT
            )
            item_pbar.grid(row=0, column=0, sticky="ew", pady=(2, 2))
            item_pbar.set(1.0 if item["status"] == "Completed" else 0.0)

            item_plbl = ctk.CTkLabel(
                prog_row,
                text="Finished" if item["status"] == "Completed" else ("Failed" if item["status"] == "Failed" else "Ready in queue"),
                font=ctk.CTkFont(family=FONT_MAIN, size=9),
                text_color=ACCENT_EMERALD if item["status"] == "Completed" else TEXT_MUTED,
                anchor="w"
            )
            item_plbl.grid(row=1, column=0, sticky="w")

            self.item_progress_bars[item["id"]] = (item_pbar, item_plbl)

            # Right action buttons
            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.grid(row=0, column=2, rowspan=2, padx=8, pady=6, sticky="e")

            if item["status"] in ("Waiting", "Failed", "Paused"):
                ctk.CTkButton(
                    btn_box, text="▶ Download", width=80, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
                    command=lambda it=item: self._download_single_queue_item(it)
                ).pack(side="left", padx=3)
            elif item["status"] == "Completed" and item.get("saved_file") and os.path.exists(item["saved_file"]):
                ctk.CTkButton(
                    btn_box, text="▶ Play", width=55, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=10, weight="bold"),
                    fg_color="#065f46", hover_color="#047857", text_color="white",
                    command=lambda it=item: os.startfile(it["saved_file"])
                ).pack(side="left", padx=2)
                ctk.CTkButton(
                    btn_box, text="📁", width=32, height=26,
                    font=ctk.CTkFont(family=FONT_MAIN, size=11),
                    fg_color=BG_CARD, hover_color=BORDER_MAIN, text_color=TEXT_BODY,
                    command=lambda it=item: os.startfile(os.path.dirname(it["saved_file"]))
                ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_box, text="✕", width=28, height=26,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                fg_color=BG_CARD, hover_color="#7f1d1d", text_color="#fca5a5",
                command=lambda it=item: self._remove_queue_item(it)
            ).pack(side="left", padx=2)

    def _remove_queue_item(self, item):
        if item in self.queue_items:
            self.queue_items.remove(item)
            self._refresh_queue_ui()

    def _clear_finished_queue(self):
        self.queue_items = [it for it in self.queue_items if it["status"] != "Completed"]
        self._refresh_queue_ui()

    def _clear_all_queue(self):
        if self.is_queue_running:
            messagebox.showwarning("Queue Busy", "The queue is currently running. Stop it first.")
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
        self.start_queue_btn.configure(text="⏳ Downloading Queue...", state="disabled")
        first_item = waiting_items[0]
        self._start_download_item(first_item, is_queue_batch=True)

    def _stop_queue_processing(self):
        self.is_queue_running = False
        self.start_queue_btn.configure(text="▶  Download All (Start Queue)", state="normal")
        if self.is_downloading:
            self._abort_download()

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
                break

        self._refresh_queue_ui()

        if is_queue_batch and self.is_queue_running:
            waiting = [it for it in self.queue_items if it["status"] == "Waiting"]
            if waiting:
                next_item = waiting[0]
                self._start_download_item(next_item, is_queue_batch=True)
            else:
                self.is_queue_running = False
                self.start_queue_btn.configure(text="▶  Download All (Start Queue)", state="normal")
                messagebox.showinfo("IDM Queue Finished", "All streams in the download queue have been downloaded & muxed successfully!")

    # ── User Actions ──────────────────────────────────────────────────────────
    def _paste_clipboard(self):
        try:
            content = self.clipboard_get().strip()
            self.input_box.delete("1.0", "end")
            self.input_box.insert("end", content)
        except Exception:
            messagebox.showwarning("Clipboard", "Could not read from system clipboard.")

    def _clear_input(self):
        self.input_box.delete("1.0", "end")

    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.folder_entry.get())
        if folder:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)

    def _open_output_folder(self):
        path = self.folder_entry.get().strip()
        if os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showerror("Folder Not Found", f"The folder does not exist:\n{path}")

    def _copy_logs(self):
        logs = self.log_textbox.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(logs)

    def _abort_download(self):
        if self.is_downloading:
            self._log("\n[Action] Sending stop signal to download engine...")
            self.engine.abort()
            self.is_queue_running = False
            self.start_queue_btn.configure(text="▶  Download All (Start Queue)", state="normal")

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
            "saved_file": None
        }
        self._start_download_item(item, is_queue_batch=False)

    def _start_download_item(self, item: dict, is_queue_batch: bool = False):
        self.is_downloading = True
        self.current_item_id = item["id"]
        item["status"] = "Downloading"
        self._refresh_queue_ui()

        self.start_btn.configure(state="disabled", fg_color="#312e81", text="⏳  Downloading...")
        self.abort_btn.configure(state="normal")
        self._set_status("downloading")
        self.progress_bar.set(0)

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
                self._set_progress(100.0, f"Saved: {os.path.basename(saved_out)}")
                if not is_queue_batch:
                    messagebox.showinfo("Download Complete", f"File saved successfully.\n\n{saved_out}")
            except RuntimeError as exc:
                err = str(exc)
                status = "Failed"
                self._set_status("aborted" if "aborted" in err.lower() else "error")
                self._log(f"\n[Error] {err}")
                self._set_progress(0, f"Failed: {err[:100]}")
                if not is_queue_batch and "aborted" not in err.lower():
                    messagebox.showerror("Download Failed", err)
            except Exception as exc:
                status = "Failed"
                self._set_status("error")
                self._log(f"\n[Unexpected Error] {exc}")
                self._set_progress(0, "An unexpected error occurred.")
                if not is_queue_batch:
                    messagebox.showerror("Unexpected Error", str(exc))
            finally:
                self.is_downloading = False
                self.current_item_id = None
                self.start_btn.configure(state="normal", fg_color=ACCENT_PRIMARY, text="▶   Start Download & Mux")
                self.abort_btn.configure(state="disabled")
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
