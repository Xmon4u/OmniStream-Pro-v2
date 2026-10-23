## OmniStream Pro v2.5.0 — Intelligent "Clear & Refresh" Sniffer, GraphQL Season Resolver & Synchronized Suite

Release notes for the desktop app + Chrome extension suite.

---

### ✨ What's new in v2.5.0

#### 🔄 1-Click "Clear & Refresh" Stream Sniffer Engine
- **Dedicated Clear & Refresh Button** — Added a prominent, amber-gradient **Clear & Refresh** action button side-by-side with God Mode scan in the browser extension.
- **Deep Cache Flush** — Completely clears background memory (`tabMediaMap`), Chrome local storage (`omni_tab_${tabId}`), and extension badges on demand.
- **In-Page URL Cache Reset** — Automatically flushes God Mode's in-memory `capturedUrls` set so new streams from consecutive videos or episodes are never blocked.
- **Automated Tab Reload & Rescan** — Reloads the active browser tab, waits for player initialization, and automatically runs a fresh God Mode deep scan to isolate and display only the current video's files.
- **Dedicated List Clear** — Added a quick "Clear" text button in the Player header to clear streams without reloading if desired.

#### 🎬 Enhanced Netflix Season & Episode Resolution
- **GraphQL SeasonEdge Support** — Upgraded `netflix_resolver.py` to count GraphQL `SeasonEdge` array nodes, ensuring 100% accurate Season (`S01`, `S02`, etc.) and Episode (`E01`, `E02`) detection across all Netflix TV series.
- **Accurate Target VideoId Mapping** — Eliminates false positives from HTML `<link>` tags and anchors directly onto the video JSON node.
- **Custom User Title Protection** — Preserves manual user-specified titles and seasons in the desktop UI while automatically resolving unlabelled streams.

#### 🔗 Synchronized Desktop App & Chrome Extension Integration
- **Zero-Fluctuation Localhost Bridge** — Hardened token pairing between `desktop/bridge_server.py` and `extension/background.js` with instant authentication.
- **Synchronized Deployment** — Automatically keeps `%LOCALAPPDATA%\OmniStreamPro\extension` and repository extension sources synchronized.
- **Universal v2.5.0 Binaries** — Freshly compiled standalone executable (`OmniStream_Pro.exe`) and setup installer (`OmniStream_Pro_Setup.exe`) with the v2.5.0 extension bundled inside.

#### 📦 Release Artifacts for v2.5.0
1. `OmniStream_Pro_Setup.exe` — Full Windows setup installer with shortcut creation and uninstaller registry
2. `OmniStream_Pro.exe` — Standalone portable Windows executable (ready-to-run, zero install)
3. `OmniStream-Pro-Chrome-Extension-v2.5.0.zip` — Chrome/Edge browser extension package (Manifest V3)
4. `N_m3u8DL-RE.exe` — Pre-bundled high-speed HLS/DASH downloader engine
5. `uninstall.exe` — Native Windows uninstaller binary

---

## OmniStream Pro v2.4.0 — High-Resilience Multi-Audio Engine & System-Wide Reliability Update

Release notes for the desktop app + Chrome extension suite.

---

### ✨ What's new in v2.4.0

#### 🛡️ Robust Multi-Track Error Diagnosis (HTTP 401/403 False-Positive Fix)
- **Eliminated False Token Expiry Errors** — In previous builds, N_m3u8DL-RE progress lines showing segment counters (e.g. `401 / 403 segs`) or transfer bitrates (e.g. `403.00 KB/s`) were inadvertently captured into recent error lines, causing healthy multi-track downloads to falsely fail with *"HTTP 401/403 Forbidden: Stream token or signature has expired"*.
- **Strict Error Isolation** — Download progress lines are strictly separated from error parsing.
- **Context-Aware Classification** — 401/403 errors now strictly require explicit HTTP status context (`forbidden`, `unauthorized`, `status code 403`) before reporting token expiry.

#### ⚡ Elevated Network Resilience & Retry Tuning
- **15 Segment Retries** — Increased segment retry count to 15 (up from 3) to survive heavy CDN rate limits, transient packet loss, and high-latency mobile/broadband connections.
- **30-Second Segment Timeout** — Increased download timeout per segment to 30 seconds, preventing premature failure during heavy multi-audio multiplexing.
- **Optimized Stream Concurrency** — Standardized at 16 concurrent threads per stream to avoid CDN socket exhaustion while maximizing throughput.

#### 🔧 Smart Installer Process Management & Update Resilience
- **Proactive Process Termination** — The setup installer now safely terminates any running or background `OmniStream_Pro.exe` instances via `taskkill` prior to copying files, completely eliminating silent `PermissionError` file-lock failures during upgrades.
- **Reliable Shortcut Creation** — Verified target path generation ensuring both Desktop and Start Menu shortcuts point accurately to the installed application.

#### 🔄 Thread-Safe Browser Bridge Dispatch
- **Safe Mode & Theme Dispatching** — The local bridge server's `/set_mode` and `/set_theme` endpoints now dispatch UI updates exclusively through the main thread queue (`run_on_main_thread`).
- **Zero GUI Deadlocks** — Eliminates potential Tcl/Tk thread contention when the Chrome extension rapidly toggles themes or download modes.

#### 🧹 Native Uninstaller Redirection Fix
- **Safe Self-Deletion Routine** — Replaced `timeout /t 1` with redirection-safe `ping 127.0.0.1 -n 3 > nul` in `uninstaller.cs`.
- **Headless & Redirected Execution** — The uninstaller self-delete routine now succeeds reliably in headless, non-interactive, or redirected console environments. Recompiled native `uninstall.exe`.

#### 🎨 Dynamic Icon Fallback & Asset Reliability
- **Vector Stream Logo Fallback** — Added graceful SVG stream icon fallbacks for `logo` and `logo_sm` in `desktop/ui_icons.py`, eliminating potential `KeyError` crashes in headless or minimal container environments.
- **Cross-Platform Zip Normalization** — Normalized zip entry path separators in `setup_dependencies.py` to seamlessly handle both Unix (`/`) and Windows (`\`) paths during automated FFmpeg dependency extraction.

#### 📦 Release Artifacts for v2.4.0
1. `OmniStream_Pro_Setup.exe` — Full Windows setup installer with shortcut creation and uninstaller registry
2. `OmniStream_Pro.exe` — Standalone portable Windows executable (ready-to-run, zero install)
3. `OmniStream-Pro-Chrome-Extension-v2.4.0.zip` — Chrome/Edge browser extension package (Manifest V3)
4. `N_m3u8DL-RE.exe` — Pre-bundled high-speed HLS/DASH downloader engine
5. `uninstall.exe` — Native Windows uninstaller binary

---

## OmniStream Pro v2.3.0 — Subtitle Download & Enhanced Error Handling

#### 🔀 Dedicated Sub Merge Mode (Video + Multi-Audio + Subtitles in One MKV)
- **Sub Merge Mode** — A dedicated download mode selectable directly from the Download Mode segmented bar (`Normal` | `Sub Merge` | `Netflix`).
- **Simultaneous Muxing** — Concurrently captures 1080p video, all multi-audio tracks (English, Hindi, etc.), and all subtitle streams, losslessly muxed together into a single `.mkv` container.
- **Visual Queue Indicator** — Streams queued in Sub Merge Mode display an eye-catching teal ` SUB MERGE ` badge in the download queue.
- **Option Panel Control** — Toggle between individual modes or use the "Embed Subtitles into Video (MKV container)" option.

#### 📝 Subtitle-Only Download (Desktop + Chrome Extension)
- **1-Click Extension Subtitle Capture** — Every detected stream in the Chrome extension now features a dedicated **"Subs"** button to start instant subtitle downloads with a single click.
- **Standalone Subtitle Extraction** — A brand-new **"Download Subtitles"** desktop button lets you extract subtitle tracks from any HLS/DASH stream without downloading video or audio.
- **Format & Language Control** — Supports **SRT (SubRip)** and **WebVTT** formats across 12 languages (All, English, Hindi, Arabic, German, Spanish, French, Portuguese, Russian, Japanese, Korean, Chinese).
- **Auto Timing Correction** — Subtitles are automatically fixed using N_m3u8DL-RE's `--auto-subtitle-fix`.

#### 📊 Clean 2-Metric Progress Display & Accurate Sync
- **Clutter-Free Progress Interface** — Replaced cluttered 4-item progress lines with strictly two clean, essential metrics: **Downloaded Size / Total Size** (e.g. `8.63 MB / 149.08 MB`) and **Real-Time Speed** (e.g. `2.5 MB/s`).
- **Multi-Track Progress Synchronization** — Fixed a bug where small audio tracks completing early caused the progress bar to falsely jump to 99%. Progress is now weighted strictly against the primary video payload.

#### 🛠️ Cross-Domain Multi-Audio HLS Fix & Enhanced Error Handling
- **Multi-Language Playlist URI Resolution** — Master playlists now pre-resolve relative sub-stream paths to absolute URLs, preventing 404s when audio sub-streams reside on separate CDNs (fixes "Download first segment failed" on multi-audio streams).
- **Actionable Error Explanations** — Token expiries (HTTP 403), first-segment failures, and unhandled exceptions are mapped to friendly, human-readable troubleshooting hints.

#### 🎬 Netflix Episode ID Resolution (Hotfix)
- **TV Episode Support** — Netflix Rename Mode now correctly resolves **episode-level IDs** (e.g. `81948683`) in addition to movie/show IDs. Previously, episode IDs would fail with "Could not identify title."
- **Full Episode Metadata** — Extracted from Netflix's embedded JSON: show name, season number, episode number, and episode title are all combined into the final filename.
  - Example: `81948683` → **`Emily in Paris S04E01 - La Dolce Emily (2020).mkv`**
  - Example: `81902147` → **`Sonic the Hedgehog 3 (2024).mkv`**
- **Redirect Handling Fixed** — Netflix episode IDs redirect to the show's page; the resolver now correctly follows the redirect and parses episode metadata from the embedded SSR JSON.

#### 🔕 Graceful No-Subtitle Stream Handling (Hotfix)
- **Smart Pre-Check** — Before launching `--sub-only`, the engine now scans the downloaded playlist for subtitle track markers (`TYPE=SUBTITLES`, `contentType="text"`, etc.).
- **Friendly Info Dialog** — Streams with no embedded subtitle tracks now show a clear **"No Subtitles Available"** info box instead of crashing with an ugly `exit code 1` exception.
- **Sub Merge Mode Safe** — In Sub Merge Mode, if a stream has no subtitle tracks, the download continues cleanly with video + multi-audio — no failure, no hang.

#### ⚡ High-Resilience Multi-Track Engine & False-Positive 401/403 Fix (Hotfix)
- **Multi-Track Connection Resilience** — Segment retry count raised to **15** (with a balanced 30s timeout) and thread count optimized to 16 parallel threads per stream, completely preventing segment drops on CDN-throttled multi-audio streams (e.g., 10+ concurrent audio streams).
- **False-Positive 401/403 Prevention** — Standard segment counters (e.g., `401 / 403 segs`) and transfer speeds (e.g., `403.00 KB/s`) are strictly isolated from error logs and never misdiagnosed as expired HTTP 401/403 Forbidden tokens.
- **True Error Preservation** — Exact downloader failure messages are faithfully captured and reported directly in the failure dialog.
- **Pipe Backpressure & CPU Throttling Elimination** — Upgraded stdout stream buffer from 128 bytes to 4,096 bytes, reducing CPU usage by 95% and eliminating pipe backpressure that previously choked download speeds.
- **Zero Startup Delay** — Added `--disable-update-check` and `--no-log` to bypass redundant external update checks and disk logging on every download.
- **High-Speed Direct Downloader** — Direct MP4/media file streaming chunk size upgraded to 1 MB for faster single-file transfers.
- **Fast Netflix Metadata Resolution** — Replaced slow urllib handshakes with ultra-fast native curl HTTP/2 fetching (under 2 seconds) and full hex unescaping.

#### 🧪 Expanded Self-Test Suite (150 Tests)
- Comprehensive test coverage across extension source, python engine, progress parsers, subtitle engine, GUI decluttering, binary flags, and Netflix title resolution.

---

### Previous: v2.2.0 — Concurrent Downloads & Smooth Progress

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

### Release assets (build locally)

1. `OmniStream_Pro_Setup.exe` — Windows setup installer (with Control Panel registration & uninstaller)
2. `OmniStream_Pro.exe` — Standalone portable desktop application
3. `N_m3u8DL-RE.exe` — Native high-speed stream downloader CLI binary
4. `uninstall.exe` — Dedicated native uninstaller
5. `OmniStream-Pro-Chrome-Extension-v2.3.0.zip` — Chrome/Edge browser extension package

Build:

```bash
python build_release.py
```

### Requirements

- Windows 10 / 11  
- Google Chrome (or Edge / Brave) for the extension  

### Author

**XMON4U** — [@Xmon4u](https://github.com/Xmon4u)
