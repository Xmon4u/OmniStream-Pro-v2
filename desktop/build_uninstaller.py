"""
Compiler script for OmniStream Pro native uninstaller (uninstall.exe).
Uses the Windows built-in Microsoft .NET Framework C# compiler (csc.exe).
Auto-discovers csc.exe across all .NET Framework versions and Visual Studio
installations. Zero extra external dependencies. Runs on any Windows 10/11 system.
"""

import os
import sys
import subprocess
import glob

DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE    = os.path.join(DESKTOP_DIR, "uninstaller.cs")
OUT_FILE    = os.path.join(DESKTOP_DIR, "uninstall.exe")
ICON_FILE   = os.path.join(DESKTOP_DIR, "app_icon.ico")

# ─── Console color helpers ────────────────────────────────────────────────────
def _green(s):  return f"\033[92m{s}\033[0m"
def _red(s):    return f"\033[91m{s}\033[0m"
def _cyan(s):   return f"\033[96m{s}\033[0m"
def _yellow(s): return f"\033[93m{s}\033[0m"

def _enable_ansi():
    """Enable ANSI color codes on Windows 10+ console."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

# ─── Compiler Discovery ───────────────────────────────────────────────────────
def find_csc():
    """
    Locate csc.exe with broad fallback:
      1. Fixed .NET Framework 4.x paths (most common)
      2. Glob across all Framework / Framework64 version folders
      3. Visual Studio 2022 / 2019 / 2017 / 2015 Roslyn compiler
      4. PATH environment
    """
    # --- Priority 1: Standard .NET Framework 4.x (fastest check) ---
    explicit = [
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework64\v3.5\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v3.5\csc.exe",
    ]
    for path in explicit:
        if os.path.isfile(path):
            return path

    # --- Priority 2: Glob all Framework versions ---
    for pattern in [
        r"C:\Windows\Microsoft.NET\Framework64\v*\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v*\csc.exe",
    ]:
        matches = sorted(glob.glob(pattern), reverse=True)  # newest first
        for m in matches:
            if os.path.isfile(m):
                return m

    # --- Priority 3: Visual Studio Roslyn compiler (2022 / 2019 / 2017 / 2015) ---
    vs_roots = [
        r"C:\Program Files\Microsoft Visual Studio",
        r"C:\Program Files (x86)\Microsoft Visual Studio",
    ]
    vs_editions = ["Enterprise", "Professional", "Community", "BuildTools"]
    vs_years    = ["2022", "2019", "2017", "2015"]
    for root in vs_roots:
        for year in vs_years:
            for edition in vs_editions:
                candidate = os.path.join(
                    root, year, edition,
                    "MSBuild", "Current", "Bin", "Roslyn", "csc.exe"
                )
                if os.path.isfile(candidate):
                    return candidate
                # Older layout
                candidate2 = os.path.join(
                    root, year, edition,
                    "MSBuild", "15.0", "Bin", "Roslyn", "csc.exe"
                )
                if os.path.isfile(candidate2):
                    return candidate2

    # --- Priority 4: Glob VS installations broadly ---
    for pattern in [
        r"C:\Program Files\Microsoft Visual Studio\*\*\MSBuild\*\Bin\Roslyn\csc.exe",
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\MSBuild\*\Bin\Roslyn\csc.exe",
    ]:
        matches = sorted(glob.glob(pattern), reverse=True)
        for m in matches:
            if os.path.isfile(m):
                return m

    # --- Priority 5: PATH ---
    import shutil
    found = shutil.which("csc")
    if found:
        return found

    return None


# ─── Build ────────────────────────────────────────────────────────────────────
def build():
    _enable_ansi()

    print(_cyan("─" * 60))
    print(_cyan("  OmniStream Pro — Uninstaller Builder"))
    print(_cyan("─" * 60))

    # Verify source file exists
    if not os.path.isfile(SRC_FILE):
        print(_red(f"[ERROR] Source file not found: {SRC_FILE}"))
        return False

    # Find compiler
    print("  Searching for C# compiler (csc.exe)...")
    csc = find_csc()
    if not csc:
        print(_red(
            "[ERROR] Microsoft .NET C# compiler (csc.exe) not found.\n"
            "  Please install one of:\n"
            "    • .NET Framework 4.x (built-in on Windows 10/11)\n"
            "    • Visual Studio 2019/2022 with 'Desktop development with C++' workload\n"
            "    • Build Tools for Visual Studio 2022 (free)"
        ))
        return False
    print(f"  Compiler : {_green(csc)}")
    print(f"  Source   : {SRC_FILE}")
    print(f"  Output   : {OUT_FILE}")
    if os.path.isfile(ICON_FILE):
        print(f"  Icon     : {ICON_FILE}")

    # Build command
    cmd = [
        csc,
        "/target:winexe",
        f"/out:{OUT_FILE}",
        "/optimize+",
        "/platform:anycpu",
        "/warn:0",          # suppress warnings for clean output
        "/nologo",
        "/reference:System.dll,System.Windows.Forms.dll,System.Drawing.dll",
    ]
    if os.path.isfile(ICON_FILE):
        cmd.append(f"/win32icon:{ICON_FILE}")
    cmd.append(SRC_FILE)

    print("\n  Compiling...")
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=DESKTOP_DIR,
    )

    if res.returncode != 0:
        print(_red(f"\n[FAILED] Compilation error (exit code {res.returncode}):"))
        if res.stdout.strip():
            print(res.stdout.strip())
        if res.stderr.strip():
            print(res.stderr.strip())
        return False

    # Verify output
    if not os.path.isfile(OUT_FILE):
        print(_red("[ERROR] Compiler exited 0 but output file was not created."))
        return False

    size_kb = os.path.getsize(OUT_FILE) / 1024
    print(_green(f"\n[SUCCESS] uninstall.exe compiled successfully!"))
    print(f"  File : {OUT_FILE}")
    print(f"  Size : {size_kb:.1f} KB")
    print(_cyan("─" * 60))
    return True


if __name__ == "__main__":
    ok = build()
    sys.exit(0 if ok else 1)
