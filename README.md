# OmniStream Pro v2.0.2 — Universal Stream Downloader & Extension Suite

<div align="center">

![OmniStream Pro Banner](desktop/app_icon.png)

### Universal Multi-Audio HLS/M3U8 Stream Downloader & Browser Bridge

**High-performance stream download suite with concurrent multi-track audio preservation, browser extension integration, and batch queue processing.**

[![Release](https://img.shields.io/badge/Release-v2.0.2-6366f1?style=for-the-badge&logo=github)](https://github.com/Xmon4u/OmniStream-Pro-v2/releases)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-06b6d4?style=for-the-badge&logo=windows)](https://github.com/Xmon4u/OmniStream-Pro-v2)
[![Extension](https://img.shields.io/badge/Chrome%20Extension-Manifest%20V3-10b981?style=for-the-badge&logo=googlechrome)](extension)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=for-the-badge)](LICENSE)

</div>

---

## Overview

**OmniStream Pro v2.0.2** is an all-in-one media downloading suite combining a Windows desktop application and a Chrome/Edge browser extension.

Capture adaptive HLS/M3U8 and DASH video streams, automatically preserve all available multi-language audio tracks, and multiplex them into a single `.mkv` container with no quality loss. With batch queuing and live browser-to-desktop link forwarding, downloading streams from any website is straightforward.

---

## Key Features

### Desktop Application

- **Batch Queue**: Links sent from the extension or pasted manually queue up automatically. Click **Download All** to process the entire queue.
- **Multi-Audio MKV Muxing**: Downloads and muxes every audio track into a single container with proper language track metadata.
- **16x Parallel Segment Downloads**: Concurrent segment downloads via N_m3u8DL-RE for maximum speed.
- **Dual-Mode Engine**: Supports both adaptive playlists (`.m3u8`, `.mpd`) and direct video files (`.mp4`, `.mkv`, `.webm`, `.mp3`).
- **cURL Importer**: Paste any `cURL (bash)` or `cURL (cmd)` command from browser DevTools; headers, cookies, referers, and tokens are parsed automatically.
- **Auto-Dependency Management**: Automatically downloads `N_m3u8DL-RE` and `ffmpeg` if they are missing.
- **Live Terminal**: Real-time logging console with progress bar, completion status, and log export.
- **Safe Abort**: Stop any ongoing download cleanly at any point.

### Browser Extension (Chrome / Edge / Chromium)

- **Minimal popup**: detected player streams + **Download** (sends to the desktop queue).
- **God Mode scan**: deep player probe and F12 / DevTools unlock on protected sites.
- **Multi-format sniffer**: HLS (`.m3u8`), DASH (`.mpd`), MP4, MKV, WebM.
- **Desktop bridge**: localhost transfer on `127.0.0.1:28795`.
- **Header preservation**: Referer, Origin, User-Agent, and related request metadata when available.

---

## System Architecture

```mermaid
graph LR
    subgraph Browser ["Web Browser (Chrome / Edge)"]
        WebPage["Web Page & Media Player"]
        GodMode["God Mode Sniffer & Anti-DevTools"]
        ExtSW["Extension Service Worker"]
        Popup["Extension UI (Streams & Queue)"]
        WebPage --> GodMode
        GodMode --> ExtSW
        ExtSW --> Popup
    end

    subgraph Bridge ["Local Bridge (127.0.0.1:28795)"]
        BridgeServer["HTTP Bridge Server (/add, /batch_add)"]
    end

    subgraph DesktopApp ["OmniStream Pro Desktop v2.0.2"]
        GUI["CustomTkinter Dark GUI"]
        QueueMgr["Queue Manager (Download All)"]
        Engine["High-Speed Engine (N_m3u8DL-RE + FFmpeg)"]
        OutputMKV["Multi-Audio Lossless MKV File"]
        GUI --> QueueMgr
        QueueMgr --> Engine
        Engine --> OutputMKV
    end

    Popup -- "Send All / Send Stream" --> BridgeServer
    BridgeServer --> GUI
```

---

## Getting Started

### 1. Desktop Application

#### Option A: Windows Setup Installer (Recommended)
1. Download **`OmniStream_Pro_Setup.exe`** from [GitHub Releases](https://github.com/Xmon4u/OmniStream-Pro-v2/releases).
2. Run the installer wizard. It will automatically deploy the software, create Desktop and Start Menu shortcuts, and configure the browser extension with 1 click.

#### Option B: Standalone Portable Executable
1. Download **`OmniStream_Pro.exe`** from [GitHub Releases](https://github.com/Xmon4u/OmniStream-Pro-v2/releases).
2. Double-click to launch directly without installation.

#### Option C: Run from Source
```bash
git clone https://github.com/Xmon4u/OmniStream-Pro-v2.git
cd OmniStream-Pro-v2

pip install -r requirements.txt
cd desktop
python main_gui.py
```

Or simply double-click `Start_OmniStream_Pro.bat` in the root folder.

Verify before publishing:

```bash
cd desktop
python selftest.py
```

---

### 2. Browser Extension

1. Open Google Chrome, Edge, or Brave.
2. Go to `chrome://extensions/` (or `edge://extensions/`).
3. Enable **Developer mode** in the top-right corner.
4. Click **Load unpacked** and select the `extension` folder inside this repository.

---

## How to Download Streams

1. Open the **OmniStream Pro** desktop application.
2. In the browser, open a video page and press play.
3. Click the **OmniStream** extension icon.
4. If the list is empty, click **God Mode scan**.
5. Click **Download** on a detected stream (it appears in the desktop queue).
6. In OmniStream Pro, click **Download All** / start the queue.

OmniStream Pro downloads segments and available audio tracks, then muxes them into an `.mkv` when multi-audio is present.

---

## Building Standalone Executable (.exe)

```bash
cd desktop
python build_exe.py
```

The compiled binary will be placed at `desktop/dist/OmniStream_Pro.exe`.

---

## Project Structure

```
OmniStream_Pro_v2/
├── desktop/
│   ├── main_gui.py              # CustomTkinter desktop application
│   ├── core_engine.py           # Multi-audio download manager & FFmpeg muxer
│   ├── bridge_server.py         # Localhost browser bridge (127.0.0.1:28795)
│   ├── extension_manager.py     # Extension deploy / Chrome profile install
│   ├── window_chrome.py         # Borderless rounded window chrome
│   ├── ui_icons.py              # Line icons + app logo helpers
│   ├── setup_dependencies.py    # Auto-downloader for N_m3u8DL-RE and FFmpeg
│   ├── build_exe.py             # PyInstaller one-file builder
│   ├── selftest.py              # Offline publish checks
│   ├── bin/README.md            # Binary tools (auto-downloaded; not in git)
│   ├── app_icon.ico
│   └── app_icon.png
│
├── extension/
│   ├── manifest.json            # Chrome MV3 manifest (v2.0.2)
│   ├── background.js            # Network sniffer & bridge
│   ├── content.js               # Content script injector
│   ├── godmode.js               # Deep scan + anti-devtools
│   ├── popup.html / .css / .js  # Minimal popup UI
│   └── icons/
│
├── requirements.txt             # Python dependencies
├── Start_OmniStream_Pro.bat
├── build_release.py             # Builds exe, installer, extension zip
├── LICENSE
├── RELEASE_NOTES.md
└── README.md
```

---

## Author

**XMON4U** — [GitHub: @Xmon4u](https://github.com/Xmon4u)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
