"""
OmniStream Pro - Settings Modal Dialog
Comprehensive configuration for Concurrency, Speed Limits, Auto-Organization,
Tray, Notifications, Network Retry, and Database Backup/Restore.
"""

import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, Optional
import customtkinter as ctk

from settings_manager import SettingsManager
from database import get_db


class SettingsDialog(ctk.CTkToplevel):
    """Modern dark modal settings dialog matching OmniStream Cyber Slate styling."""

    def __init__(
        self,
        parent: tk.Misc,
        current_theme: str = "Cyber Slate",
        on_saved: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        super().__init__(parent)
        self.settings_mgr = SettingsManager.get_instance()
        self.current_settings = self.settings_mgr.get_all()
        self.on_saved = on_saved

        self.title("OmniStream Pro - Preferences & Settings")
        self.geometry("680x680")
        self.minsize(620, 560)
        self.configure(fg_color="#0d1117")
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 340
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 340
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="#161b22", height=54, corner_radius=0)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_lbl = ctk.CTkLabel(
            header,
            text="⚙️ Preferences & Engine Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f0f6fc",
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        # Scrollable container for settings sections
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=16)

        # Section 1: Engine & Concurrency
        self._build_section_header(scroll, "⚡ Download Engine & Concurrency")

        # Concurrency
        conc_row = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        conc_row.pack(fill="x", pady=(0, 10), padx=2)

        ctk.CTkLabel(
            conc_row,
            text="Simultaneous Downloads:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e5e7eb"
        ).pack(side="left", padx=16, pady=12)

        curr_conc = str(self.current_settings.get("max_concurrent", 2))
        conc_opts = ["1", "2", "3", "5", "Unlimited"]
        default_val = "Unlimited" if curr_conc in ("0", "unlimited") else curr_conc
        if default_val not in conc_opts:
            default_val = "2"

        self.conc_var = tk.StringVar(value=default_val)
        self.conc_menu = ctk.CTkSegmentedButton(
            conc_row,
            values=conc_opts,
            variable=self.conc_var,
            selected_color="#2563eb",
            selected_hover_color="#1d4ed8",
            unselected_color="#21262d",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.conc_menu.pack(side="right", padx=16, pady=10)

        # Speed Limit
        speed_row = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        speed_row.pack(fill="x", pady=(0, 10), padx=2)

        ctk.CTkLabel(
            speed_row,
            text="Speed Limit per Download:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e5e7eb"
        ).pack(side="left", padx=16, pady=12)

        curr_speed = self.current_settings.get("speed_limit", "unlimited")
        speed_opts = ["Unlimited", "2 MB/s", "5 MB/s", "10 MB/s", "Custom"]
        speed_val_map = {"unlimited": "Unlimited", "2M": "2 MB/s", "5M": "5 MB/s", "10M": "10 MB/s"}
        init_speed = speed_val_map.get(str(curr_speed).upper(), "Custom" if curr_speed not in ("unlimited", "") else "Unlimited")

        self.speed_var = tk.StringVar(value=init_speed)
        self.speed_menu = ctk.CTkOptionMenu(
            speed_row,
            values=speed_opts,
            variable=self.speed_var,
            fg_color="#21262d",
            button_color="#2563eb",
            button_hover_color="#1d4ed8",
            font=ctk.CTkFont(size=11),
            width=130,
            command=self._on_speed_choice
        )
        self.speed_menu.pack(side="right", padx=16, pady=10)

        self.custom_speed_entry = ctk.CTkEntry(
            speed_row,
            placeholder_text="e.g. 15M",
            width=80,
            font=ctk.CTkFont(size=11),
            fg_color="#090d13",
            border_color="#30363d"
        )
        if init_speed == "Custom":
            self.custom_speed_entry.insert(0, str(curr_speed))
            self.custom_speed_entry.pack(side="right", padx=(0, 8), pady=10)

        # Save Directory
        dir_row = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        dir_row.pack(fill="x", pady=(0, 14), padx=2)

        ctk.CTkLabel(
            dir_row,
            text="Default Save Folder:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e5e7eb"
        ).pack(anchor="w", padx=16, pady=(10, 4))

        dir_sub = ctk.CTkFrame(dir_row, fg_color="transparent")
        dir_sub.pack(fill="x", padx=16, pady=(0, 12))

        self.dir_entry = ctk.CTkEntry(
            dir_sub,
            font=ctk.CTkFont(size=11),
            fg_color="#090d13",
            border_color="#30363d"
        )
        self.dir_entry.insert(0, self.current_settings.get("default_save_dir", ""))
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            dir_sub,
            text="Browse...",
            width=80,
            command=self._browse_dir,
            fg_color="#21262d",
            hover_color="#30363d",
            font=ctk.CTkFont(size=11)
        )
        browse_btn.pack(side="right")

        # Section 2: Organization & Safety
        self._build_section_header(scroll, "📁 Media Organization & Safety")

        org_box = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        org_box.pack(fill="x", pady=(0, 14), padx=2)

        self.smart_org_var = tk.BooleanVar(value=bool(self.current_settings.get("smart_organization", False)))
        smart_org_chk = ctk.CTkCheckBox(
            org_box,
            text="Media Organization (Sort Movies & TV Shows into folders)",
            variable=self.smart_org_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        smart_org_chk.pack(anchor="w", padx=16, pady=(12, 6))

        self.dup_var = tk.BooleanVar(value=bool(self.current_settings.get("duplicate_detection", True)))
        dup_chk = ctk.CTkCheckBox(
            org_box,
            text="Duplicate Detection (Warn if a stream is already present in queue)",
            variable=self.dup_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        dup_chk.pack(anchor="w", padx=16, pady=6)

        self.space_var = tk.BooleanVar(value=bool(self.current_settings.get("check_disk_space", True)))
        space_chk = ctk.CTkCheckBox(
            org_box,
            text="Low Disk Space Protection (Warn if free space on destination drive < 2 GB)",
            variable=self.space_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        space_chk.pack(anchor="w", padx=16, pady=(6, 12))

        # Section 3: Reliability & Auto-Retry
        self._build_section_header(scroll, "🔁 Network Reliability & Retry")

        net_box = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        net_box.pack(fill="x", pady=(0, 14), padx=2)

        net_top = ctk.CTkFrame(net_box, fg_color="transparent")
        net_top.pack(fill="x", padx=16, pady=(10, 6))

        self.retry_var = tk.BooleanVar(value=bool(self.current_settings.get("auto_retry_network", True)))
        retry_chk = ctk.CTkCheckBox(
            net_top,
            text="Auto-Retry on Network Disconnect (Exponential backoff: 5s, 15s, 30s)",
            variable=self.retry_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        retry_chk.pack(side="left")

        self.retry_count_var = tk.StringVar(value=str(self.current_settings.get("max_retries", 3)))
        ctk.CTkOptionMenu(
            net_top,
            values=["1", "3", "5", "10"],
            variable=self.retry_count_var,
            width=70,
            fg_color="#21262d",
            button_color="#2563eb",
            font=ctk.CTkFont(size=11)
        ).pack(side="right")
        ctk.CTkLabel(net_top, text="Retries:", font=ctk.CTkFont(size=11), text_color="#9ca3af").pack(side="right", padx=(0, 8))

        # Section 4: Notifications & Actions
        self._build_section_header(scroll, "🔔 Notifications & Actions")

        bg_box = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        bg_box.pack(fill="x", pady=(0, 14), padx=2)

        self.toast_var = tk.BooleanVar(value=bool(self.current_settings.get("toast_notification", True)))
        toast_chk = ctk.CTkCheckBox(
            bg_box,
            text="Windows 10/11 Native Toast Notifications on completion",
            variable=self.toast_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        toast_chk.pack(anchor="w", padx=16, pady=(12, 6))

        self.sound_var = tk.BooleanVar(value=bool(self.current_settings.get("sound_on_complete", True)))
        sound_chk = ctk.CTkCheckBox(
            bg_box,
            text="Play audio sound chime on download complete",
            variable=self.sound_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        sound_chk.pack(anchor="w", padx=16, pady=6)

        self.tray_var = tk.BooleanVar(value=bool(self.current_settings.get("minimize_to_tray_on_close", False)))
        tray_chk = ctk.CTkCheckBox(
            bg_box,
            text="Minimize to System Tray when closing window [X]",
            variable=self.tray_var,
            font=ctk.CTkFont(size=11),
            fg_color="#2563eb",
            hover_color="#1d4ed8"
        )
        tray_chk.pack(anchor="w", padx=16, pady=6)

        # Queue Completion Action
        act_row = ctk.CTkFrame(bg_box, fg_color="transparent")
        act_row.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkLabel(
            act_row,
            text="When All Downloads Finish:",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#e5e7eb"
        ).pack(side="left")

        act_map = {
            "none": "Do Nothing",
            "sound": "Play Sound",
            "sleep": "Put PC to Sleep",
            "shutdown": "Shut Down PC (60s countdown)"
        }
        rev_act_map = {v: k for k, v in act_map.items()}
        curr_act = self.current_settings.get("queue_completion_action", "none")
        init_act = act_map.get(curr_act, "Do Nothing")

        self.action_var = tk.StringVar(value=init_act)
        self.action_menu = ctk.CTkOptionMenu(
            act_row,
            values=list(act_map.values()),
            variable=self.action_var,
            fg_color="#21262d",
            button_color="#2563eb",
            font=ctk.CTkFont(size=11),
            width=200
        )
        self.action_menu.pack(side="right")

        # Section 5: Database Maintenance & Backup
        self._build_section_header(scroll, "💾 Database & Queue Backup")

        db_box = ctk.CTkFrame(scroll, fg_color="#161b22", corner_radius=8)
        db_box.pack(fill="x", pady=(0, 16), padx=2)

        db_desc = ctk.CTkLabel(
            db_box,
            text="Persist your queue, export download lists to JSON, or backup the SQLite database.",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af"
        )
        db_desc.pack(anchor="w", padx=16, pady=(12, 8))

        btn_grid = ctk.CTkFrame(db_box, fg_color="transparent")
        btn_grid.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkButton(
            btn_grid,
            text="Export Queue (JSON)",
            command=self._export_queue_json,
            fg_color="#21262d",
            hover_color="#30363d",
            font=ctk.CTkFont(size=11),
            height=30
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_grid,
            text="Import Queue (JSON)",
            command=self._import_queue_json,
            fg_color="#21262d",
            hover_color="#30363d",
            font=ctk.CTkFont(size=11),
            height=30
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_grid,
            text="Backup Database",
            command=self._backup_db,
            fg_color="#21262d",
            hover_color="#30363d",
            font=ctk.CTkFont(size=11),
            height=30
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_grid,
            text="Restore Database",
            command=self._restore_db,
            fg_color="#21262d",
            hover_color="#30363d",
            font=ctk.CTkFont(size=11),
            height=30
        ).pack(side="left")

        # Bottom Bar with Save & Cancel
        bottom_bar = ctk.CTkFrame(self, fg_color="#161b22", height=54, corner_radius=0)
        bottom_bar.pack(fill="x", side="bottom")
        bottom_bar.pack_propagate(False)

        save_btn = ctk.CTkButton(
            bottom_bar,
            text="Save Settings",
            command=self._save_settings,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        save_btn.pack(side="right", padx=20, pady=10)

        cancel_btn = ctk.CTkButton(
            bottom_bar,
            text="Cancel",
            command=self.destroy,
            fg_color="#21262d",
            hover_color="#30363d",
            height=34,
            corner_radius=6,
            font=ctk.CTkFont(size=12)
        )
        cancel_btn.pack(side="right", padx=(0, 10), pady=10)

    def _build_section_header(self, parent: ctk.CTkScrollableFrame, text: str):
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        )
        lbl.pack(anchor="w", pady=(8, 6), padx=4)

    def _on_speed_choice(self, choice: str):
        if choice == "Custom":
            if not self.custom_speed_entry.winfo_ismapped():
                self.custom_speed_entry.pack(side="right", padx=(0, 8), pady=10)
        else:
            if self.custom_speed_entry.winfo_ismapped():
                self.custom_speed_entry.pack_forget()

    def _browse_dir(self):
        cur = self.dir_entry.get().strip()
        sel = filedialog.askdirectory(initialdir=cur if os.path.isdir(cur) else None)
        if sel:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, os.path.normpath(sel))

    def _export_queue_json(self):
        fpath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            initialfile="omnistream_queue.json"
        )
        if fpath:
            db = get_db()
            ok = db.export_queue_to_json(fpath)
            if ok:
                messagebox.showinfo("Export Successful", f"Queue exported successfully to:\n{fpath}", parent=self)
            else:
                messagebox.showerror("Export Failed", "Failed to export queue.", parent=self)

    def _import_queue_json(self):
        fpath = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if fpath:
            db = get_db()
            count = db.import_queue_from_json(fpath)
            messagebox.showinfo("Import Complete", f"Imported {count} items into download queue.", parent=self)

    def _backup_db(self):
        db = get_db()
        path = db.create_db_backup()
        if path:
            messagebox.showinfo("Backup Created", f"SQLite Database backup created at:\n{path}", parent=self)
        else:
            messagebox.showerror("Backup Failed", "Could not create database backup.", parent=self)

    def _restore_db(self):
        fpath = filedialog.askopenfilename(filetypes=[("Backup Files", "*.bak;*.db")])
        if fpath:
            if messagebox.askyesno("Confirm Restore", "Restoring from backup will replace the current queue. Continue?", parent=self):
                db = get_db()
                ok = db.restore_db_backup(fpath)
                if ok:
                    messagebox.showinfo("Restore Successful", "Database restored successfully. Changes will take effect on refresh.", parent=self)
                else:
                    messagebox.showerror("Restore Failed", "Could not restore database from selected file.", parent=self)

    def _save_settings(self):
        # 1. Concurrency
        conc_str = self.conc_var.get()
        conc_val = 0 if conc_str == "Unlimited" else int(conc_str)

        # 2. Speed
        speed_sel = self.speed_var.get()
        if speed_sel == "Unlimited":
            speed_val = "unlimited"
        elif speed_sel == "2 MB/s":
            speed_val = "2M"
        elif speed_sel == "5 MB/s":
            speed_val = "5M"
        elif speed_sel == "10 MB/s":
            speed_val = "10M"
        else:
            speed_val = self.custom_speed_entry.get().strip() or "unlimited"

        # 3. Actions
        rev_act_map = {
            "Do Nothing": "none",
            "Play Sound": "sound",
            "Put PC to Sleep": "sleep",
            "Shut Down PC (60s countdown)": "shutdown"
        }
        completion_action = rev_act_map.get(self.action_var.get(), "none")

        new_settings = {
            "max_concurrent": conc_val,
            "speed_limit": speed_val,
            "default_save_dir": self.dir_entry.get().strip(),
            "smart_organization": self.smart_org_var.get(),
            "duplicate_detection": self.dup_var.get(),
            "check_disk_space": self.space_var.get(),
            "auto_retry_network": self.retry_var.get(),
            "max_retries": int(self.retry_count_var.get()),
            "toast_notification": self.toast_var.get(),
            "sound_on_complete": self.sound_var.get(),
            "minimize_to_tray_on_close": self.tray_var.get(),
            "queue_completion_action": completion_action,
        }

        self.settings_mgr.update(new_settings)

        if self.on_saved:
            self.on_saved(new_settings)

        self.destroy()

