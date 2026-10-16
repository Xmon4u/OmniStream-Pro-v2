"""
OmniStream Pro v2.0.0 — Professional Windows Setup Installer
Installs OmniStream Pro, deploys the Chrome extension, checks extension status,
creates Desktop and Start Menu shortcuts, and launches the app.
Author: XMON4U (https://github.com/Xmon4u)
"""

import os
import sys
import shutil
import subprocess
import glob
import json
try:
    import webbrowser
except ImportError:
    webbrowser = None
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

# Ensure desktop module can be imported properly both during dev and when packaged
if getattr(sys, 'frozen', False):
    INSTALLER_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    INSTALLER_DIR = os.path.dirname(os.path.abspath(__file__))

DESKTOP_DIR = os.path.join(INSTALLER_DIR, "desktop")
sys.path.insert(0, DESKTOP_DIR)
sys.path.insert(0, INSTALLER_DIR)

from extension_manager import (
    get_app_data_dir,
    get_deployed_extension_dir,
    deploy_extension_files,
    is_extension_installed,
    mark_extension_installed,
    invalidate_extension_cache,
    open_chrome_extensions,
    open_extension_folder,
    launch_browser_with_extension,
    is_chrome_running
)
from ui_icons import apply_window_icon, build_icon_set

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_ROOT        = "#080c14"
BG_CARD        = "#101827"
BG_CARD2       = "#0f172a"
BG_INPUT       = "#060911"
ACCENT_PRIMARY = "#6366f1"
ACCENT_HOVER   = "#4f46e5"
ACCENT_CYAN    = "#06b6d4"
ACCENT_EMERALD = "#10b981"
ACCENT_GLOW    = "#38bdf8"
BORDER_MAIN    = "#1e293b"
BORDER_SUB     = "#162032"
TEXT_TITLE     = "#f8fafc"
TEXT_BODY      = "#94a3b8"
TEXT_MUTED     = "#64748b"
FONT_MAIN      = "Segoe UI"
FONT_CODE      = "Cascadia Code"


def create_windows_shortcut(target_exe: str, shortcut_path: str, icon_path: str = ""):
    """Create a native Windows .lnk shortcut using PowerShell WScript.Shell."""
    try:
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{shortcut_path}'); "
            f"$s.TargetPath = '{target_exe}'; "
            f"$s.WorkingDirectory = '{os.path.dirname(target_exe)}'; "
        )
        if icon_path and os.path.exists(icon_path):
            ps_cmd += f"$s.IconLocation = '{icon_path}'; "
        ps_cmd += "$s.Save()"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True, creationflags=0x08000000)
        return True
    except Exception:
        return False


class OmniStreamInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("OmniStream Pro Setup")
        self.geometry("640x510")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)

        icon_dir = DESKTOP_DIR if os.path.isfile(os.path.join(DESKTOP_DIR, "app_icon.png")) else INSTALLER_DIR
        apply_window_icon(self, icon_dir)
        self.icons = build_icon_set(icon_dir)

        self.install_dir = get_app_data_dir()
        self.create_desktop_sc = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header Banner
        header = ctk.CTkFrame(self, fg_color="#0c1220", corner_radius=0, height=80)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        ctk.CTkLabel(header, text="", image=self.icons["logo_sm"]).place(x=16, y=16)

        ctk.CTkLabel(
            header, text="OmniStream Pro v2.0 Setup",
            font=ctk.CTkFont(family=FONT_MAIN, size=18, weight="bold"),
            text_color=TEXT_TITLE
        ).place(x=78, y=16)

        ctk.CTkLabel(
            header, text="High-Speed Stream Downloader & Extension Suite Installation",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_MUTED
        ).place(x=78, y=42)

        # Main Body Container
        self.main_body = ctk.CTkFrame(self, fg_color="transparent")
        self.main_body.grid(row=1, column=0, sticky="nsew", padx=24, pady=16)

        self._show_step_welcome()

        # Footer Button Bar
        self.footer = ctk.CTkFrame(self, fg_color="#0c1220", corner_radius=0, height=56)
        self.footer.grid(row=2, column=0, sticky="ew")
        self.footer.grid_propagate(False)

        self.cancel_btn = ctk.CTkButton(
            self.footer, text="Cancel", width=90, height=34,
            fg_color=BG_CARD, hover_color=BORDER_MAIN, text_color=TEXT_BODY,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), corner_radius=6,
            command=self.destroy
        )
        self.cancel_btn.pack(side="right", padx=(8, 20), pady=11)

        self.next_btn = ctk.CTkButton(
            self.footer, text="Install Now", width=120, height=34,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER, text_color="white",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"), corner_radius=6,
            command=self._start_installation
        )
        self.next_btn.pack(side="right", pady=11)

    def _show_step_welcome(self):
        for widget in self.main_body.winfo_children():
            widget.destroy()

        ctk.CTkLabel(
            self.main_body,
            text="Welcome to the OmniStream Pro Installation Wizard",
            font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        ).pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            self.main_body,
            text="This wizard will set up OmniStream Pro on your system and deploy the Chrome extension.",
            font=ctk.CTkFont(family=FONT_MAIN, size=11),
            text_color=TEXT_BODY, anchor="w"
        ).pack(fill="x", pady=(0, 14))

        # Destination Box
        card = ctk.CTkFrame(self.main_body, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
        card.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            card, text="Installation Location:",
            font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
            text_color=ACCENT_GLOW
        ).pack(anchor="w", padx=14, pady=(12, 4))

        loc_entry = ctk.CTkEntry(
            card, fg_color=BG_INPUT, border_color=BORDER_SUB, border_width=1,
            height=32, text_color="#c8deff", font=ctk.CTkFont(family=FONT_CODE, size=10), corner_radius=6
        )
        loc_entry.pack(fill="x", padx=14, pady=(0, 12))
        loc_entry.insert(0, self.install_dir)
        loc_entry.configure(state="readonly")

        # Options Box
        opt_card = ctk.CTkFrame(self.main_body, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
        opt_card.pack(fill="x", pady=(0, 10))

        ctk.CTkCheckBox(
            opt_card, text="Create Desktop Shortcut", variable=self.create_desktop_sc,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_TITLE,
            checkbox_height=18, checkbox_width=18, corner_radius=4,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER
        ).pack(anchor="w", padx=14, pady=10)

        ctk.CTkCheckBox(
            opt_card, text="Launch OmniStream Pro after installation", variable=self.launch_after,
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_TITLE,
            checkbox_height=18, checkbox_width=18, corner_radius=4,
            fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER
        ).pack(anchor="w", padx=14, pady=(0, 10))

    def _start_installation(self):
        self.next_btn.configure(state="disabled", text="Installing...")
        self.cancel_btn.configure(state="disabled")

        for widget in self.main_body.winfo_children():
            widget.destroy()

        ctk.CTkLabel(
            self.main_body, text="Installing OmniStream Pro...",
            font=ctk.CTkFont(family=FONT_MAIN, size=14, weight="bold"),
            text_color=TEXT_TITLE, anchor="w"
        ).pack(fill="x", pady=(0, 8))

        self.pbar = ctk.CTkProgressBar(self.main_body, height=8, corner_radius=4, progress_color=ACCENT_CYAN, fg_color=BG_INPUT)
        self.pbar.pack(fill="x", pady=(0, 10))
        self.pbar.set(0.1)

        self.status_lbl = ctk.CTkLabel(
            self.main_body, text="Extracting core files and binaries...",
            font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_MUTED, anchor="w"
        )
        self.status_lbl.pack(fill="x")

        self.after(300, self._perform_install_steps)

    def _perform_install_steps(self):
        try:
            target_dir = self.install_dir
            os.makedirs(target_dir, exist_ok=True)

            # 1. Copy desktop application files
            self.status_lbl.configure(text="Installing application engine...")
            self.pbar.set(0.3)
            self.update_idletasks()

            for item in [
                "main_gui.py",
                "core_engine.py",
                "bridge_server.py",
                "setup_dependencies.py",
                "extension_manager.py",
                "ui_icons.py",
                "window_chrome.py",
                "app_icon.ico",
                "app_icon.png",
            ]:
                src = os.path.join(DESKTOP_DIR, item)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(target_dir, item))

            # Copy bin directory
            src_bin = os.path.join(DESKTOP_DIR, "bin")
            dst_bin = os.path.join(target_dir, "bin")
            if os.path.exists(src_bin):
                os.makedirs(dst_bin, exist_ok=True)
                for b in os.listdir(src_bin):
                    s = os.path.join(src_bin, b)
                    d = os.path.join(dst_bin, b)
                    if os.path.isfile(s) and not os.path.exists(d):
                        shutil.copy2(s, d)

            # Copy compiled executable if present
            target_exe = os.path.join(target_dir, "OmniStream_Pro.exe")
            candidate_exes = [
                os.path.join(DESKTOP_DIR, "OmniStream_Pro.exe"),
                os.path.join(DESKTOP_DIR, "dist", "OmniStream_Pro.exe"),
                os.path.join(INSTALLER_DIR, "desktop", "OmniStream_Pro.exe"),
                os.path.join(INSTALLER_DIR, "desktop", "dist", "OmniStream_Pro.exe"),
                os.path.join(INSTALLER_DIR, "OmniStream_Pro.exe"),
                os.path.join(INSTALLER_DIR, "dist", "OmniStream_Pro.exe"),
            ]
            for cand in candidate_exes:
                if os.path.isfile(cand):
                    try:
                        shutil.copy2(cand, target_exe)
                        break
                    except Exception:
                        pass

            # 2. Deploy Chrome Extension
            self.status_lbl.configure(text="Deploying browser extension...")
            self.pbar.set(0.6)
            self.update_idletasks()
            deployed_ext_dir = deploy_extension_files()

            # 3. Create Shortcuts
            self.status_lbl.configure(text="Creating desktop & start menu shortcuts...")
            self.pbar.set(0.8)
            self.update_idletasks()

            target_run = target_exe if os.path.exists(target_exe) else sys.executable
            desktop_folder = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
            icon_file = os.path.join(target_dir, "app_icon.ico")

            if self.create_desktop_sc.get():
                create_windows_shortcut(
                    target_exe=target_run,
                    shortcut_path=os.path.join(desktop_folder, "OmniStream Pro.lnk"),
                    icon_path=icon_file
                )

            # Start Menu shortcut
            appdata_roaming = os.environ.get("APPDATA", "")
            if appdata_roaming:
                start_menu_dir = os.path.join(appdata_roaming, "Microsoft", "Windows", "Start Menu", "Programs", "OmniStream Pro")
                os.makedirs(start_menu_dir, exist_ok=True)
                create_windows_shortcut(
                    target_exe=target_run,
                    shortcut_path=os.path.join(start_menu_dir, "OmniStream Pro.lnk"),
                    icon_path=icon_file
                )

            # 4. Check Extension Status
            self.pbar.set(1.0)
            self.status_lbl.configure(text="Finalizing setup...")
            self.update_idletasks()

            self._show_step_finish(deployed_ext_dir)
        except Exception as e:
            messagebox.showerror("Installation Error", f"Installation failed: {e}")
            self.destroy()

    def _show_step_finish(self, deployed_ext_dir: str):
        for widget in self.main_body.winfo_children():
            widget.destroy()

        invalidate_extension_cache()
        ext_already_installed = is_extension_installed()

        ctk.CTkLabel(
            self.main_body, text="Installation Completed Successfully!",
            font=ctk.CTkFont(family=FONT_MAIN, size=15, weight="bold"),
            text_color=ACCENT_EMERALD, anchor="w"
        ).pack(fill="x", pady=(0, 6))

        if ext_already_installed:
            card = ctk.CTkFrame(self.main_body, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
            card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                card, text="Chrome extension detected", image=self.icons["check"], compound="left",
                font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
                text_color=ACCENT_EMERALD
            ).pack(anchor="w", padx=14, pady=(12, 4))
            ctk.CTkLabel(
                card, text="The browser extension is already installed. You're ready to capture & download streams!",
                font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY
            ).pack(anchor="w", padx=14, pady=(0, 12))
        else:
            card = ctk.CTkFrame(self.main_body, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_MAIN)
            card.pack(fill="x", pady=10)

            ctk.CTkLabel(
                card, text="Browser extension setup", image=self.icons["extension"], compound="left",
                font=ctk.CTkFont(family=FONT_MAIN, size=12, weight="bold"),
                text_color=ACCENT_GLOW
            ).pack(anchor="w", padx=14, pady=(10, 4))

            ext_status_var = {"lbl": None}

            ext_status_lbl = ctk.CTkLabel(
                card, text="🔄 Preparing to launch Chrome with Extension...",
                font=ctk.CTkFont(family=FONT_MAIN, size=11), text_color=TEXT_BODY, anchor="w"
            )
            ext_status_lbl.pack(fill="x", padx=14, pady=(0, 6))
            ext_status_var["lbl"] = ext_status_lbl

            def _update_status(msg: str):
                try:
                    ext_status_var["lbl"].configure(text=msg)
                except Exception:
                    pass

            def _do_launch(btn=None):
                import threading
                if btn:
                    btn.configure(state="disabled")
                _update_status("🔄 Launching Chrome with OmniStream Extension...")

                def _bg():
                    ok = launch_browser_with_extension()
                    if ok:
                        self.after(0, lambda: _update_status(
                            "Chrome launched. Use that window for streaming."
                        ))
                        if btn:
                            self.after(0, lambda: btn.configure(
                                text="Extension active", image=self.icons["check"], fg_color="#065f46", state="disabled"
                            ))
                    else:
                        self.after(0, lambda: _update_status(
                            "Auto-launch failed. Use the buttons below to set it up."
                        ))
                        if btn:
                            self.after(0, lambda: btn.configure(state="normal"))
                threading.Thread(target=_bg, daemon=True).start()

            launch_btn = ctk.CTkButton(
                card, text="Launch Chrome", image=self.icons["chrome"], compound="left", height=34,
                fg_color=ACCENT_PRIMARY, hover_color=ACCENT_HOVER,
                font=ctk.CTkFont(family=FONT_MAIN, size=11, weight="bold"),
                corner_radius=8
            )
            launch_btn.configure(command=lambda: _do_launch(launch_btn))
            launch_btn.pack(fill="x", padx=14, pady=(0, 8))

            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.pack(fill="x", padx=14, pady=(0, 10))

            ctk.CTkButton(
                btn_box, text="Open chrome://extensions", width=180, height=30,
                fg_color=BG_CARD2, hover_color=BORDER_MAIN, text_color=TEXT_TITLE,
                border_width=1, border_color=BORDER_SUB, font=ctk.CTkFont(family=FONT_MAIN, size=10),
                command=open_chrome_extensions
            ).pack(side="left", padx=(0, 6))

            ctk.CTkButton(
                btn_box, text="Open Extension Folder", width=160, height=30,
                fg_color=BG_CARD2, hover_color=BORDER_MAIN, text_color=TEXT_TITLE,
                border_width=1, border_color=BORDER_SUB, font=ctk.CTkFont(family=FONT_MAIN, size=10),
                command=open_extension_folder
            ).pack(side="left")

            # Auto-trigger after a short delay so the UI renders first
            self.after(800, lambda: _do_launch(launch_btn))

        # Update footer buttons
        self.cancel_btn.pack_forget()
        self.next_btn.configure(
            state="normal", text="Finish", fg_color=ACCENT_EMERALD, hover_color="#047857",
            command=self._finish_and_launch
        )


    def _finish_and_launch(self):
        target_exe = os.path.join(self.install_dir, "OmniStream_Pro.exe")
        if self.launch_after.get():
            if os.path.exists(target_exe):
                subprocess.Popen([target_exe])
            else:
                main_py = os.path.join(self.install_dir, "main_gui.py")
                if os.path.exists(main_py):
                    subprocess.Popen([sys.executable, main_py])
        self.destroy()


if __name__ == "__main__":
    app = OmniStreamInstaller()
    app.mainloop()
