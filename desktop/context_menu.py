"""
OmniStream Pro - Queue Context Menu & Item Actions
Provides right-click context menu, item action callbacks, and properties dialog.
"""

import os
import subprocess
import sys
import tkinter as tk
from typing import Any, Callable, Dict, Optional
import customtkinter as ctk

from database import get_db


class QueueContextMenu:
    """Right-click context menu for download queue items."""

    def __init__(
        self,
        master: tk.Misc,
        on_pause: Callable[[str], None],
        on_resume: Callable[[str], None],
        on_restart: Callable[[str], None],
        on_cancel: Callable[[str], None],
        on_remove: Callable[[str], None],
        on_rename: Callable[[str, str], None],
        on_properties: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_move_up: Optional[Callable[[str], None]] = None,
        on_move_down: Optional[Callable[[str], None]] = None,
    ):
        self.master = master
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_restart = on_restart
        self.on_cancel = on_cancel
        self.on_remove = on_remove
        self.on_rename = on_rename
        self.on_properties = on_properties or self.show_properties_dialog
        self.on_move_up = on_move_up
        self.on_move_down = on_move_down

        self.menu = tk.Menu(
            master,
            tearoff=0,
            bg="#161922",
            fg="#f3f4f6",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            activeborderwidth=0,
            bd=1,
            relief="solid",
            font=("Segoe UI", 9)
        )
        self.current_item: Optional[Dict[str, Any]] = None

    def show(self, event, item: Dict[str, Any]):
        """Pop up the context menu populated and configured for the given item."""
        self.current_item = item
        status = (item.get("status") or "").lower()
        item_id = str(item.get("id"))
        filepath = item.get("final_path") or ""
        file_exists = bool(filepath and os.path.exists(filepath))

        self.menu.delete(0, tk.END)

        # 1. Open File
        self.menu.add_command(
            label="  ▶ Open File",
            command=lambda: self.open_file(item),
            state=tk.NORMAL if (status == "completed" and file_exists) else tk.DISABLED
        )

        # 2. Open File Location
        self.menu.add_command(
            label="  📁 Open File Location",
            command=lambda: self.open_file_location(item),
            state=tk.NORMAL if (file_exists or (item.get("save_dir") and os.path.isdir(item.get("save_dir")))) else tk.DISABLED
        )

        self.menu.add_separator()

        # 3. Pause
        self.menu.add_command(
            label="  ⏸ Pause",
            command=lambda: self.on_pause(item_id),
            state=tk.NORMAL if status == "downloading" else tk.DISABLED
        )

        # 4. Resume
        self.menu.add_command(
            label="  ▶ Resume",
            command=lambda: self.on_resume(item_id),
            state=tk.NORMAL if status in ("paused", "waiting") else tk.DISABLED
        )

        # 5. Restart
        self.menu.add_command(
            label="  🔄 Restart",
            command=lambda: self.on_restart(item_id),
            state=tk.NORMAL if status in ("completed", "failed", "cancelled", "paused") else tk.DISABLED
        )

        # 6. Cancel
        self.menu.add_command(
            label="  ⏹ Cancel Download",
            command=lambda: self.on_cancel(item_id),
            state=tk.NORMAL if status in ("downloading", "waiting") else tk.DISABLED
        )

        self.menu.add_separator()

        # 7. Rename
        self.menu.add_command(
            label="  ✏ Rename...",
            command=lambda: self.show_rename_dialog(item),
            state=tk.NORMAL if status != "downloading" else tk.DISABLED
        )

        # 8. Copy Link
        self.menu.add_command(
            label="  📋 Copy Download Link",
            command=lambda: self.copy_link(item),
            state=tk.NORMAL if bool(item.get("source_url") or item.get("raw_input")) else tk.DISABLED
        )

        # 9. Remove
        self.menu.add_command(
            label="  🗑 Remove from Queue",
            command=lambda: self.on_remove(item_id),
            state=tk.NORMAL if status != "downloading" else tk.DISABLED
        )

        if self.on_move_up or self.on_move_down:
            self.menu.add_separator()
            if self.on_move_up:
                self.menu.add_command(
                    label="  ▲ Move Up",
                    command=lambda: self.on_move_up(item_id),
                    state=tk.NORMAL if status != "downloading" else tk.DISABLED
                )
            if self.on_move_down:
                self.menu.add_command(
                    label="  ▼ Move Down",
                    command=lambda: self.on_move_down(item_id),
                    state=tk.NORMAL if status != "downloading" else tk.DISABLED
                )

        self.menu.add_separator()

        # 10. Properties
        self.menu.add_command(
            label="  ℹ Properties",
            command=lambda: self.on_properties(item),
            state=tk.NORMAL
        )

        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def open_file(self, item: Dict[str, Any]):
        """Open completed media file with default system player."""
        filepath = item.get("final_path") or ""
        if filepath and os.path.exists(filepath):
            try:
                os.startfile(os.path.abspath(filepath))
            except Exception as e:
                print(f"[ContextMenu] Error opening file: {e}")

    def open_file_location(self, item: Dict[str, Any]):
        """Open Windows Explorer and highlight the downloaded file if it exists."""
        filepath = item.get("final_path") or ""
        if filepath and os.path.exists(filepath):
            try:
                abs_p = os.path.abspath(filepath)
                subprocess.Popen(["explorer.exe", f"/select,{abs_p}"])
                return
            except Exception as e:
                print(f"[ContextMenu] explorer /select failed: {e}")

        save_dir = item.get("save_dir") or ""
        if save_dir and os.path.isdir(save_dir):
            try:
                os.startfile(os.path.abspath(save_dir))
            except Exception as e:
                print(f"[ContextMenu] Error opening folder: {e}")

    def copy_link(self, item: Dict[str, Any]):
        """Copy the stream URL or raw input to system clipboard."""
        url = item.get("source_url") or item.get("raw_input") or ""
        if url:
            self.master.clipboard_clear()
            self.master.clipboard_append(url)
            self.master.update()

    def show_rename_dialog(self, item: Dict[str, Any]):
        """Modal dialog to rename queue item and optional disk file."""
        dialog = ctk.CTkToplevel(self.master)
        dialog.title("Rename Download Item")
        dialog.geometry("450x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0e1117")
        dialog.transient(self.master)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        try:
            x = self.master.winfo_rootx() + (self.master.winfo_width() // 2) - 225
            y = self.master.winfo_rooty() + (self.master.winfo_height() // 2) - 110
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        title_lbl = ctk.CTkLabel(
            dialog,
            text="Rename Download Item",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#f3f4f6"
        )
        title_lbl.pack(pady=(16, 8), padx=20, anchor="w")

        desc_lbl = ctk.CTkLabel(
            dialog,
            text="Enter a new title. If the file has finished downloading, the physical file will also be renamed:",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
            wraplength=410,
            justify="left"
        )
        desc_lbl.pack(pady=(0, 12), padx=20, anchor="w")

        curr_title = item.get("title") or item.get("save_name") or ""
        entry = ctk.CTkEntry(
            dialog,
            height=36,
            corner_radius=8,
            fg_color="#181c24",
            border_color="#374151",
            text_color="#ffffff",
            font=ctk.CTkFont(size=12)
        )
        entry.insert(0, curr_title)
        entry.pack(fill="x", padx=20, pady=(0, 16))
        entry.focus_set()
        entry.select_range(0, tk.END)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        def do_rename():
            new_val = entry.get().strip()
            if new_val and new_val != curr_title:
                dialog.destroy()
                self.on_rename(str(item.get("id")), new_val)
            else:
                dialog.destroy()

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Changes",
            command=do_rename,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        save_btn.pack(side="right", padx=(8, 0))

        cancel_btn = ctk.CTkButton(
            btn_row,
            text="Cancel",
            command=dialog.destroy,
            fg_color="#374151",
            hover_color="#4b5563",
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12)
        )
        cancel_btn.pack(side="right")

        dialog.bind("<Return>", lambda e: do_rename())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def show_properties_dialog(self, item: Dict[str, Any]):
        """Modal dialog displaying comprehensive metadata and file info."""
        dialog = ctk.CTkToplevel(self.master)
        dialog.title(f"Item Properties - {item.get('title') or 'Download'}")
        dialog.geometry("540x480")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0e1117")
        dialog.transient(self.master)
        dialog.grab_set()

        try:
            x = self.master.winfo_rootx() + (self.master.winfo_width() // 2) - 270
            y = self.master.winfo_rooty() + (self.master.winfo_height() // 2) - 240
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        title_lbl = ctk.CTkLabel(
            dialog,
            text="Download Item Properties",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#60a5fa"
        )
        title_lbl.pack(pady=(16, 12), padx=20, anchor="w")

        info_scroll = ctk.CTkScrollableFrame(
            dialog,
            fg_color="#13161c",
            border_color="#1f242d",
            border_width=1,
            corner_radius=8
        )
        info_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Format size if available
        size_display = "Unknown"
        final_p = item.get("final_path") or ""
        if final_p and os.path.exists(final_p):
            try:
                sz = os.path.getsize(final_p)
                if sz >= 1024 * 1024 * 1024:
                    size_display = f"{sz / (1024**3):.2f} GB ({sz:,} bytes)"
                else:
                    size_display = f"{sz / (1024**2):.1f} MB ({sz:,} bytes)"
            except Exception:
                pass
        elif item.get("file_size"):
            size_display = str(item.get("file_size"))

        fields = [
            ("Title", item.get("title") or "N/A"),
            ("Status", (item.get("status") or "N/A").capitalize()),
            ("Progress", f"{item.get('progress', 0.0):.1f}%"),
            ("Download Mode", (item.get("download_mode") or "normal").upper()),
            ("Resolution", item.get("resolution") or "1080p"),
            ("Audio Tracks", item.get("audio_choice") or "all"),
            ("Subtitles", "Embedded MKV" if item.get("include_subtitles") else "None"),
            ("File Size", size_display),
            ("Destination", item.get("final_path") or item.get("save_dir") or "N/A"),
            ("Stream URL", item.get("source_url") or "N/A"),
            ("Date Added", item.get("created_at") or "N/A"),
            ("Date Completed", item.get("completed_at") or "Not completed"),
        ]

        if item.get("error_message"):
            fields.append(("Last Error", item.get("error_message")))

        for label, val in fields:
            row = ctk.CTkFrame(info_scroll, fg_color="transparent")
            row.pack(fill="x", pady=4, padx=4)

            lbl = ctk.CTkLabel(
                row,
                text=label + ":",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#9ca3af",
                width=110,
                anchor="w"
            )
            lbl.pack(side="left", anchor="n")

            val_lbl = ctk.CTkLabel(
                row,
                text=str(val),
                font=ctk.CTkFont(size=11),
                text_color="#f3f4f6",
                justify="left",
                wraplength=350,
                anchor="w"
            )
            val_lbl.pack(side="left", fill="x", expand=True)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        close_btn = ctk.CTkButton(
            btn_row,
            text="Close",
            command=dialog.destroy,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        close_btn.pack(side="right")
