## OmniStream Pro v2.1.0 — Universal Stream Downloader & Extension Suite

Release notes for the desktop app + Chrome extension suite.

---

### ✨ What's new in v2.1.0

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

1. `OmniStream_Pro.exe` — portable desktop app  
2. `OmniStream_Pro_Setup.exe` — Windows installer (optional)  
3. `OmniStream-Pro-Chrome-Extension-v2.1.0.zip` — Load unpacked after unzip

Build:

```bash
python build_release.py
```

### Requirements

- Windows 10 / 11  
- Google Chrome (or Edge / Brave) for the extension  

### Author

**XMON4U** — [@Xmon4u](https://github.com/Xmon4u)
