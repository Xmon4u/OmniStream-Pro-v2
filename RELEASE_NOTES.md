# OmniStream Pro Release Notes

## Version 2.6.0

Release notes for the desktop application and Chromium extension suite.

### What's New in v2.6.0

#### Media Title Resolver (Netflix, IMDb, TMDB)
- **Dedicated Media Modes**: Added support for selecting between **Netflix Mode**, **IMDb Mode**, and **TMDB Mode** alongside Normal and Subtitle Merge modes.
- **IMDb ID Detection & Online Resolution**: Automatically extracts IMDb IDs (`tt...`) from URLs, request headers, cURL commands, or filenames. Queries Wikidata and metadata endpoints to format filenames into standardized conventions (e.g. `Inception (2010) S02E04.mkv`).
- **TMDB Integration**: Resolves TMDB movie and TV show IDs with localized title and episode formatting.
- **Netflix Parser**: Extracts clean show and season information from Netflix media identifiers.

#### Native C++ Core Engine
- **Windows-Native Network Core**: Added CMake-based C++ engine utilizing native WinHTTP and Winsock for lightweight localhost bridge communication.
- **Zero External DLLs**: Fully linked against standard Windows system runtime libraries (`winhttp.lib`, `ws2_32.lib`, `crypt32.lib`).

#### Download Engine Improvements
- **Per-Item Cancellation**: Cancel individual downloads without blocking or aborting other queued items.
- **Live Progress & Speed Calculation**: Precise real-time MB/s or KB/s speed tracking, percentage completion, and ETA.
- **Inline Title Renaming**: Click the edit button on any item card in the queue to rename the target file on disk before or after download completion.
- **Automatic Post-Mux Cleanup**: Temporary chunk and segment files (`.ts`, `.m4a`, `.aac`) are safely removed after final MKV assembly.

#### Desktop UI & System Integration
- **Modernized Dark Palette**: Refined contrast, consistent font hierarchy, and improved layout spacing.
- **Windows Integration**: Proper Control Panel ("Programs and Features") registration and uninstaller support via Inno Setup.
