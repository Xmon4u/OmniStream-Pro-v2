## OmniStream Pro v2.2.0 — Concurrent Downloads & Smooth Progress

Release notes for the desktop app + Chrome extension suite.

---

### ✨ What's new in v2.2.0

#### ⚡ Concurrent Multi-File Downloads
- **Simultaneous Downloads** — Start multiple downloads at the same time. No more "A download is already in progress" error. Each file downloads independently in its own engine instance.
- **Individual Cancel** — Every actively-downloading item shows a dedicated **Cancel** button. Cancel one download without affecting the others.
- **Parallel Download All** — "Download All" now launches all waiting items concurrently instead of sequentially.
- **Smart Queue Cleanup** — "Clear All" only removes waiting/completed items; active downloads are preserved.

#### 🎞️ Smooth Chrome-Style Progress Animation
- **No More Bouncing Bar** — The indeterminate bounce/pulse animation (3%–15% oscillation) has been removed.
- **Smooth Linear Fill** — Progress bars now use a smooth ease-out fill, just like Chrome's download bar — advancing steadily with real download data.
- **Per-Item Progress** — Each download card in the queue has its own independent progress bar that fills smoothly and accurately.
- **Live Speed & ETA** — Each item shows real-time download speed (KB/s / MB/s) and estimated time remaining.

---

### Previous: v2.1.0 Features

#### 🔗 Chrome Extension
- **Copy Button** — Every detected stream now shows a **Copy** button next to the **Download** button. Click it to instantly copy the download link to your clipboard without opening the desktop app.

#### 🖊️ Edit Title / Rename
- **Inline File Rename** — After a download completes, a **pencil (✏)** icon appears next to the filename in the Download Queue. Click it to rename the file directly from the software — the file on disk is renamed instantly with the new title.

#### 🧹 Auto-Cleanup (Temp & Intermediate Files)
- After a successful mux, OmniStream Pro automatically deletes all intermediate segment files (separate video/audio tracks, `.m4a`, `.aac`, `.ts`, `.mp4` fragments) that N_m3u8DL-RE leaves behind.
- Only the **final merged MKV** (with all audio tracks embedded) is kept. No manual cleanup needed.

#### 🎞️ Final Video — Multi-Audio Preserved
- All audio tracks (Hindi, English, Spanish, etc.) are merged into a single MKV container. The intermediate per-language audio files are removed after muxing. The final video retains every audio track and is fully renameable.

#### ⚡ Download Progress & Speed Fix
- **Accurate Real-Time Progress**: Displays real-time download percentage completed (`XX.X% done`) and remaining (`XX.X% left`).
- **Download Speed Indicator**: Shows live download speed dynamically formatted in MB/s or KB/s (e.g. `12.4 MB/s`).
- **Estimated Time Remaining (ETA)**: Calculates and displays precise remaining time until completion (`ETA 1m 23s`).
- **Smooth Animated Progress Bar**: Animation line advances proportionally and smoothly with actual download progress, turning emerald green on completion.
- **ANSI Escape Strip & Multi-Track Weighting**: Output is cleanly parsed and normalized across concurrent video and audio streams.

#### 🗑️ Control Panel Integration & Native Uninstaller
- **Windows Control Panel & Settings Integration**: Installs with full registration under Windows `Programs and Features` and `Installed Apps`.
- **Dedicated Uninstaller (`uninstall.exe`)**: Built-in native uninstaller with confirmation prompt, safe process termination, shortcut cleanup, registry removal, and disk cleanup.
- **Start Menu Uninstall Shortcut**: Provides a direct "Uninstall OmniStream Pro" shortcut in Start Menu.

---

### Previous: v2.0.2 Features

- Rounded borderless desktop window with custom caption buttons (Windows).
- App logo + line icons in the desktop UI (no emoji icons).
- Chrome extension install into the profile you are using.
- Minimal extension popup: God Mode scan, player list, Download to desktop.
- Live download timeline: percent done / left, ETA, speed, and progress-bar animation.
- Cleaner desktop UI: removed duplicate Chrome/queue buttons; Clear Logs kept on the Terminal tab.
- Stronger stream capture (`webRequest.onBeforeRequest` + God Mode deep scan).

---

### Release assets (build locally)

1. `OmniStream_Pro_Setup.exe` — Windows setup installer (with Control Panel registration & uninstaller)
2. `OmniStream_Pro.exe` — Standalone portable desktop application
3. `N_m3u8DL-RE.exe` — Native high-speed stream downloader CLI binary
4. `uninstall.exe` — Dedicated native uninstaller
5. `OmniStream-Pro-Chrome-Extension-v2.2.0.zip` — Chrome/Edge browser extension package

Build:

```bash
python build_release.py
```

### Requirements

- Windows 10 / 11  
- Google Chrome (or Edge / Brave) for the extension  

### Author

**XMON4U** — [@Xmon4u](https://github.com/Xmon4u)
