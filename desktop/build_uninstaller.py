"""
Compiler script for OmniStream Pro native uninstaller (uninstall.exe).
Uses the Windows built-in Microsoft .NET Framework C# compiler (csc.exe).
Zero extra external dependencies, compiles instantly, runs on any Windows 10/11 system.
"""

import os
import sys
import subprocess

DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(DESKTOP_DIR, "uninstaller.cs")
OUT_FILE = os.path.join(DESKTOP_DIR, "uninstall.exe")
ICON_FILE = os.path.join(DESKTOP_DIR, "app_icon.ico")

def find_csc():
    candidates = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def build():
    csc = find_csc()
    if not csc:
        raise RuntimeError("Microsoft .NET C# compiler (csc.exe) not found on system.")

    cmd = [
        csc,
        "/target:winexe",
        f"/out:{OUT_FILE}",
        "/optimize+",
        "/platform:anycpu",
        "/reference:System.dll,System.Windows.Forms.dll,System.Drawing.dll",
    ]

    if os.path.isfile(ICON_FILE):
        cmd.append(f"/win32icon:{ICON_FILE}")

    cmd.append(SRC_FILE)

    print(f"Compiling {OUT_FILE} using {csc}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Compilation failed:\n{res.stdout}\n{res.stderr}")
        return False

    size_kb = os.path.getsize(OUT_FILE) / 1024
    print(f"[SUCCESS] Compiled {OUT_FILE} ({size_kb:.1f} KB)")
    return True

if __name__ == "__main__":
    ok = build()
    sys.exit(0 if ok else 1)
