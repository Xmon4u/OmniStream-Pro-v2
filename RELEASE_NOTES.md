## ⚡ OmniStream Pro v2.0.0 — Universal Stream Downloader & Extension Suite

We are thrilled to release **OmniStream Pro v2.0.0**, introducing seamless browser-to-desktop link forwarding, an IDM-grade batch download queue, multi-audio MKV multiplexing, and God Mode deep scanning!

---

### ✨ What's New in v2.0.0

- 🚀 **IDM-Grade Batch Download Queue**:
  - Automatically queue video links transferred from the browser extension or pasted manually.
  - Prominent **"▶ Download All (Start Queue)"** button downloads all queued items sequentially with real-time speed, percentage, ETA, and progress metrics.
  - Controls to Pause/Stop Queue, Clear Finished, or remove individual items.
  - One-click **"▶ Play"** and **"📁 Open Folder"** for finished videos.

- ⚡ **Direct Extension-to-Desktop Bridge**:
  - Browser extension talks directly to the desktop app on `127.0.0.1:28795`.
  - **"🚀 Send All to App"**: Send all detected video streams on the active page to the desktop queue in a single click.
  - **"⚡ Send to App"**: Send individual detected streams with all original request headers, referers, cookies, and tokens.
  - Remote "Start App Queue" trigger from the extension popup.

- 🎧 **Lossless Multi-Audio MKV Multiplexing**:
  - Preserves every available audio language track (English, Hindi, Bengali, etc.) in HLS/M3U8 master playlists.
  - Automatically multiplexes video and all audio tracks into a single clean `.mkv` file.

- 🌐 **Dual-Mode Media Engine**:
  - Supports adaptive HLS (`.m3u8`) and DASH (`.mpd`) playlists.
  - Supports direct streaming video links (`.mp4`, `.mkv`, `.webm`, `.mp3`).

- 🛡️ **God Mode Deep Probe & Anti-DevTools Neutralizer**:
  - Deep DOM scanner and player stimulator that surfaces hidden or obfuscated streams.
  - Bypasses anti-debugger loops and restores F12, DevTools shortcuts, and right-click menus.

- 📦 **100% Portable & Self-Contained**:
  - Single standalone `.exe` for Windows 10 & 11—no installation required.
  - Auto-checks and provisions `N_m3u8DL-RE` and `ffmpeg` if not already present.

---

### 📦 Release Assets

1. **`OmniStream_Pro.exe`**: Standalone Windows Desktop Application (v2.0.0).
2. **`OmniStream-Pro-Chrome-Extension-v2.0.0.zip`**: Chrome / Edge / Brave Browser Extension (Manifest V3).

---

### 👤 Author
Developed with ❤️ by **XMON4U** ([@Xmon4u](https://github.com/Xmon4u)).
