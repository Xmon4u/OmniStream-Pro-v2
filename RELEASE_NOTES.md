## OmniStream Pro v2.0.2 — Universal Stream Downloader & Extension Suite

Release notes for the desktop app + Chrome extension suite.

### What's new

- **Rounded borderless desktop window** with custom caption buttons (Windows).
- **App logo + line icons** in the desktop UI (no emoji icons).
- **Chrome extension install** into the profile you are using, without killing every open profile.
- **Minimal extension popup**: God Mode scan, player list, **Download** to desktop.
- **Live download timeline**: percent done / left, ETA, speed, and progress-bar animation.
- **Cleaner desktop UI**: removed duplicate Chrome/queue buttons; **Clear Logs** kept on the Terminal tab.
- Stronger stream capture (`webRequest.onBeforeRequest` + God Mode deep scan).
- Playlist filter fixed so normal `.m3u8` / `.mpd` links are shown (not only multi-audio masters).
- Fixed Windows Setup EXE PKG packaging (no nested PyInstaller archives).

### Release assets (build locally)

1. `OmniStream_Pro.exe` — portable desktop app  
2. `OmniStream_Pro_Setup.exe` — Windows installer (optional)  
3. `OmniStream-Pro-Chrome-Extension-v2.0.2.zip` — Load unpacked after unzip, or use the `extension/` folder in the repo  

Build:

```bash
python build_release.py
```

### Requirements

- Windows 10 / 11  
- Google Chrome (or Edge / Brave) for the extension  
- Node.js on PATH helps Chrome extension auto-install on branded Chrome  

### Author

**XMON4U** — [@Xmon4u](https://github.com/Xmon4u)
