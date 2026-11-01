"""
OmniStream Pro - Notification & Background Automation Manager
Handles Windows 10/11 Toast Notifications, Sound, and Post-Queue Completion Actions (Sleep, Shutdown with Cancel dialog).
"""

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Optional
import customtkinter as ctk

try:
    import winsound
except ImportError:
    winsound = None


class NotificationManager:
    """Manages OS notifications, audio cues, and system completion actions."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = NotificationManager()
        return cls._instance

    def __init__(self):
        self._countdown_active = False

    def play_sound(self):
        """Play a subtle notification chime."""
        if winsound:
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

    def show_toast(self, title: str, message: str, file_path: Optional[str] = None):
        """Show native Windows 10/11 toast notification asynchronously without blocking."""
        def _send():
            try:
                # Escape XML/PowerShell characters
                safe_title = (
                    title.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "''")
                )
                safe_msg = (
                    message.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "''")
                )

                ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("OmniStream Pro")
$notifier.Show($toast)
"""
                creationflags = 0x08000000 if sys.platform == "win32" else 0
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    timeout=8
                )
            except Exception as e:
                # Fallback to sound if toast fails
                self.play_sound()

        threading.Thread(target=_send, daemon=True).start()

    def handle_completion_action(self, action: str, master: Optional[tk.Misc] = None):
        """
        Execute post-queue completion action:
        - 'none' / 'do_nothing': No action
        - 'sound': Play completion audio
        - 'sleep': Put PC to sleep
        - 'shutdown': Schedule 60-second shutdown with visual cancel dialog
        """
        action = (action or "none").lower()

        if action in ("none", "do_nothing"):
            return

        if action == "sound":
            self.play_sound()
            return

        if action == "sleep":
            self.play_sound()
            time.sleep(1)
            try:
                subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            except Exception as e:
                print(f"[NotificationManager] Failed to put PC to sleep: {e}")
            return

        if action == "shutdown":
            self.play_sound()
            self._schedule_shutdown_with_dialog(master)

    def _schedule_shutdown_with_dialog(self, master: Optional[tk.Misc]):
        """Schedule PC shutdown in 60s and display visual countdown modal with Cancel button."""
        try:
            # Issue OS shutdown command with 60 second delay
            subprocess.run(
                ["shutdown.exe", "/s", "/t", "60", "/c", "OmniStream Pro: All downloads finished. Shutting down in 60s."],
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )
        except Exception as e:
            print(f"[NotificationManager] Error scheduling shutdown: {e}")
            return

        if not master:
            return

        # Show countdown dialog
        dialog = ctk.CTkToplevel(master)
        dialog.title("System Shutdown Scheduled")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0e1117")
        dialog.transient(master)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        try:
            x = master.winfo_rootx() + (master.winfo_width() // 2) - 210
            y = master.winfo_rooty() + (master.winfo_height() // 2) - 110
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        title_lbl = ctk.CTkLabel(
            dialog,
            text="⚠️ System Shutdown Warning",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ef4444"
        )
        title_lbl.pack(pady=(16, 8), padx=20)

        seconds_left = [60]

        count_lbl = ctk.CTkLabel(
            dialog,
            text="OmniStream Pro has completed the download queue.\nYour computer will shut down in 60 seconds.",
            font=ctk.CTkFont(size=12),
            text_color="#e5e7eb",
            justify="center"
        )
        count_lbl.pack(pady=(0, 16), padx=20)

        timer_var = tk.StringVar(value="Shutting down in: 60s")
        timer_badge = ctk.CTkLabel(
            dialog,
            textvariable=timer_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#f59e0b"
        )
        timer_badge.pack(pady=(0, 16))

        def abort_shutdown():
            seconds_left[0] = -1
            try:
                subprocess.run(
                    ["shutdown.exe", "/a"],
                    creationflags=0x08000000 if sys.platform == "win32" else 0
                )
            except Exception:
                pass
            dialog.destroy()

        cancel_btn = ctk.CTkButton(
            dialog,
            text="Cancel Shutdown",
            command=abort_shutdown,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            height=36,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        cancel_btn.pack(pady=(0, 16))

        def tick():
            if seconds_left[0] <= 0:
                return
            seconds_left[0] -= 1
            if seconds_left[0] > 0:
                timer_var.set(f"Shutting down in: {seconds_left[0]}s")
                dialog.after(1000, tick)
            else:
                dialog.destroy()

        dialog.after(1000, tick)

