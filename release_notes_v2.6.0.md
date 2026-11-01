# OmniStream Pro v2.6.0 — High-Performance Streaming & Direct Media Download Suite

OmniStream Pro v2.6.0 delivers a ground-up native C++20 architecture overhaul paired with an enhanced Chrome Manifest V3 browser companion. Engineered for speed, stability, and high-concurrency downloads, OmniStream Pro unifies HLS, DASH, and direct HTTP/HTTPS media stream handling into a seamless desktop experience.

---

## What's New in v2.6.0

### 1. High-Performance Native C++20 Architecture
- **Migrated from legacy Python to native C++20 (MSVC 2022 + Qt 6.6.3)**: Instant application startup, reduced memory footprint, and low-latency UI responsiveness.
- **Pure Win32 GUI Subsystem**: Eliminates auxiliary console popups and standard CRT abort/assertion dialogues.
- **Clean Thread Lifecycles**: Integrated synchronized joinable worker thread pools with atomic barrier counters (`active_workers_count_`, `active_clients_`) to ensure thread-safe application shutdowns without orphan processes or database locks.

### 2. Dual-Engine Download Pipeline with Automatic Fallback
- **Universal Stream Support**: Automatically classifies and routes media streams between the specialized HLS/DASH engine and the native WinHTTP streaming engine.
- **Native HTTP Streaming Engine**: High-throughput multi-part downloader with full `Range: bytes=X-` resumption (HTTP 206 Partial Content) for direct MP4, MKV, WebM, TS, and audio formats.
- **HLS / DASH Muxing Pipeline**: High-speed concurrent segment extraction powered by `N_m3u8DL-RE` and `FFmpeg` with MKV container packaging and multi-track audio selection.
- **Fail-Safe Automatic Fallback**: If an unsegmented CDN video URL is passed to the manifest parser, the engine catches unsupported format errors and immediately shifts to direct HTTP chunked download with zero user intervention.

### 3. Chrome / Edge Extension Integration (MV3)
- **1-Click Stream Capture**: Instant sniffer detects HLS playlists, DASH manifests, and CDN video files directly from web players.
- **Local Bridge Protocol**: High-speed authenticated loopback communication on `127.0.0.1:28795` with Bearer token protection and origin verification.
- **IDM-Grade Queue Progression**: Added support for single send, batch queueing, and live download state synchronization across the extension and desktop interface.

### 4. Database & Persistence Layer
- **SQLite3 with Write-Ahead Logging (WAL)**: Robust persistent storage for download history, queue status, and headers.
- **Comprehensive Metadata Preservation**: Complete storage and reload of Cookies, User-Agent, Referer, Origin, and custom request parameters across application restarts.

### 5. Professional UI & Window Handling
- **Windows Frameless Window Management**: Clean custom title bar with working minimize, maximize, restore, and drag behaviors.
- **Dual Visual Themes**: Cyber Slate and Midnight Black themes with smooth contrast adjustments.
- **System Tray Integration**: Background stream capture and non-blocking desktop notifications.

---

## Release Assets

| Asset Name | Description | Size |
|---|---|---|
| **`OmniStream_Pro_Setup.exe`** | Standalone Windows Installer (installs C++ app, tools, extension, uninstaller) | ~178 MB |
| **`OmniStream_Pro_v2.6.0_C++_Portable.zip`** | Full Portable Archive (OmniStreamPro.exe + Qt 6 DLLs + FFmpeg + N_m3u8DL-RE) | ~116 MB |
| **`OmniStream_Pro.exe`** | Standalone Native C++ Executable (MSVC 2022 Release) | ~740 KB |
| **`OmniStream-Pro-Chrome-Extension-v2.6.0.zip`** | Chrome / Edge / Brave Manifest V3 Extension Package | ~135 KB |
| **`uninstall.exe`** | Dedicated Uninstaller Utility (cleans registry, hosts, and shortcuts) | ~74 KB |
| **`ffmpeg.exe`** | FFmpeg 64-bit Multimedia Muxing Binary | ~161 MB |
| **`N_m3u8DL-RE.exe`** | High-Speed Stream Segment Extraction Engine | ~12.7 MB |
| **`OmniStream-Pro-v2.6.0-CPP-Source.zip`** | Complete Native C++20 Project Source Code | ~380 KB |
| **`OmniStream-Pro-v2.6.0-Python-Source.zip`** | Complete Legacy Python Reference Source Code | ~265 KB |

---

## Installation & Usage

### Method 1: Windows Installer (Recommended)
1. Download **`OmniStream_Pro_Setup.exe`**.
2. Run the installer. It will automatically deploy OmniStream Pro, register the Chrome Extension native messaging host, and configure desktop shortcuts.
3. Open OmniStream Pro and click **Setup Extension (1-Click)** to complete browser integration.

### Method 2: Portable Package
1. Download and extract **`OmniStream_Pro_v2.6.0_C++_Portable.zip`**.
2. Run **`OmniStreamPro.exe`** (or `OmniStream_Pro.exe`).
3. In Chrome or Edge, navigate to `chrome://extensions`, enable **Developer mode**, and select **Load unpacked** pointing to the `extension` folder.

---

## System Requirements
- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Browser**: Google Chrome, Microsoft Edge, Brave, or any Chromium-based browser
- **Runtime**: Microsoft Visual C++ 2015-2022 Redistributable (x64)

