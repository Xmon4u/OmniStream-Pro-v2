# OmniStream Pro — Browser Extension

Manifest V3 extension for Chrome, Edge, and Brave. Sniffs player streams and sends them to the OmniStream Pro desktop app.

## Features

- Real-time HLS (`.m3u8`), DASH (`.mpd`), and direct video detection
- **Copy Button** — Copy any stream URL to clipboard instantly with one click
- **God Mode scan** — deep player probe + F12 / DevTools unlock
- Minimal popup: detected player links + **Download** (sends to desktop) + **Copy**
- Localhost bridge to desktop app on `127.0.0.1:28795`
- Header / cURL capture for authenticated streams

## Install (Load unpacked)

1. Open `chrome://extensions/` (or `edge://extensions/`).
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Select this `extension` folder.
5. Pin OmniStream in the toolbar.

## Use with the desktop app

1. Start **OmniStream Pro** (desktop).
2. Play a video on any site.
3. Open the extension popup.
4. Click **God Mode scan** if the list is empty.
5. Click **Download** to send a stream to the desktop queue, or **Copy** to copy its URL.
6. In the desktop app, use **Download All** / the queue to save multi-audio MKV when available.

## Version

See `manifest.json` (`2.1.0`).

## Author

**XMON4U** — [github.com/Xmon4u](https://github.com/Xmon4u)
