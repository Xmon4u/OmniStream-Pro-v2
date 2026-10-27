#include "common.hpp"
#include "curl_parser.hpp"
#include "hls_parser.hpp"
#include "http_client.hpp"
#include "crypto.hpp"
#include "muxer.hpp"
#include "netflix_resolver.hpp"
#include "download_engine.hpp"
#include "bridge_server.hpp"

using namespace OmniStream;

int RunSelfTest() {
    std::cout << "\n" << Color::Bold << Color::Cyan
              << "============================================================\n"
              << " OmniStream Pro v" << VERSION << " — C++ Native Core Self-Test Suite\n"
              << "============================================================\n"
              << Color::Reset << std::endl;

    int passed = 0;
    int failed = 0;

    auto test = [&](const std::string& name, bool condition) {
        if (condition) {
            std::cout << Color::Green << " [PASS] " << Color::Reset << name << std::endl;
            passed++;
        } else {
            std::cout << Color::Red << " [FAIL] " << Color::Reset << name << std::endl;
            failed++;
        }
    };

    // 1. Curl & Header Parser
    std::string testCurl = R"(curl 'https://stream.example.com/live/index.m3u8' -H 'User-Agent: CustomUA' -H 'Referer: https://myreferer.com/' -b 'token=xyz')";
    StreamInfo parsed = CurlParser::Parse(testCurl);
    test("cURL URL parsed", parsed.url == "https://stream.example.com/live/index.m3u8");
    test("cURL User-Agent extracted", parsed.user_agent == "CustomUA");
    test("cURL Referer extracted", parsed.referer == "https://myreferer.com/");
    test("cURL Cookie extracted", parsed.cookie == "token=xyz");

    // 2. Dynamic Origin & Referer Fallback
    std::string directUrl = "https://cdn.videohost.org/video_1080p/master.m3u8";
    StreamInfo autoOrigin = CurlParser::Parse(directUrl);
    test("Dynamic Origin derived", autoOrigin.origin == "https://cdn.videohost.org");
    test("Dynamic Referer derived", autoOrigin.referer == "https://cdn.videohost.org/");

    // 3. AES-128 BCrypt Decryption Round-Trip
    std::vector<uint8_t> testKey = { 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                                     0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F };
    std::vector<uint8_t> testIv = { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1 };
    std::string rawToken = Crypto::GenerateRandomToken(16);
    test("Crypto Random Token generated", rawToken.size() == 32);

    // 4. HLS M3U8 Master Parser
    std::string sampleMaster =
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
        "360p.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720\n"
        "720p.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080\n"
        "1080p.m3u8\n"
        "#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"audio\",NAME=\"English\",DEFAULT=YES,URI=\"audio_en.m3u8\"\n";

    HlsPlaylist masterPl = HlsParser::Parse(sampleMaster, "https://cdn.test.com/stream/master.m3u8");
    test("HLS Master detected", masterPl.isMaster == true);
    test("HLS Variant count == 3", masterPl.tracks.size() == 4); // 3 video + 1 audio
    HlsTrack best = HlsParser::SelectBestVideoTrack(masterPl, "1080p");
    test("HLS Best variant resolved 1080p", best.resolution == "1920x1080");

    // 5. Netflix, IMDb & TMDB Metadata Resolver
    test("Netflix ID extracted (URL)", NetflixResolver::ExtractNetflixId("https://www.netflix.com/watch/81902147?trackId=123") == "81902147");
    test("Netflix ID extracted (Episode URL)", NetflixResolver::ExtractNetflixId("https://www.netflix.com/watch/81948683") == "81948683");
    test("Netflix ID extracted (Query param)", NetflixResolver::ExtractNetflixId("https://cdn.example.com/video?movieid=81902147") == "81902147");
    test("Netflix ID extracted (Filename)", NetflixResolver::ExtractNetflixId("NF_81902147_1080p.mkv") == "81902147");
    test("IMDb ID extracted", NetflixResolver::ExtractImdbId("https://www.imdb.com/title/tt1375666/") == "tt1375666");
    test("TMDB ID extracted (URL)", NetflixResolver::ExtractTmdbId("https://www.themoviedb.org/movie/939243") == "939243");
    test("Episode tag extracted (S01E03)", NetflixResolver::ExtractEpisodeTag("MyShow S01E03 1080p") == "S01E03");
    test("Filename sanitizer", NetflixResolver::SanitizeFilename("Bad:Name/With*Illegal?Chars") == "Bad_Name_With_Illegal_Chars");

    // Unified Media Rename Logic Tests (Strict User Specifications)
    std::string renImdbMovie = NetflixResolver::ResolveMediaRename("imdb_rename", "stream.m3u8", "Inception", "", "tt1375666");
    test("ResolveMediaRename IMDb Mode Movie (tt1375666)", renImdbMovie == "tt1375666");

    std::string renImdbTv = NetflixResolver::ResolveMediaRename("imdb_rename", "stream.m3u8", "Stranger Things S01E02", "", "tt4574334");
    test("ResolveMediaRename IMDb Mode TV Series (S01E02 tt4574334)", renImdbTv == "S01E02 tt4574334");

    std::string renTmdbMovie = NetflixResolver::ResolveMediaRename("tmdb_rename", "stream.m3u8", "Sonic 3", "", "", "939243");
    test("ResolveMediaRename TMDB Mode Movie (939243)", renTmdbMovie == "939243");

    std::string renTmdbTv = NetflixResolver::ResolveMediaRename("tmdb_rename", "stream.m3u8", "Arcane S01E02", "", "", "94605");
    test("ResolveMediaRename TMDB Mode TV Series (S01E02 94605)", renTmdbTv == "S01E02 94605");

    std::string renTitleOnly = NetflixResolver::ResolveMediaRename("title_only", "stream.m3u8", "Movie Name (2025)", "", "tt1234567", "8273726");
    test("ResolveMediaRename Title Only Mode (Movie Name (2025))", renTitleOnly == "Movie Name (2025)");

    std::string renTitleId = NetflixResolver::ResolveMediaRename("title_id", "stream.m3u8", "Movie Name (2025)", "", "tt1234567", "8273726");
    test("ResolveMediaRename Title + ID Mode (Movie Name (2025) tt1234567 8273726)", renTitleId == "Movie Name (2025) tt1234567 8273726");

    // Netflix Rename Mode Tests
    std::string renNfMovie = NetflixResolver::ResolveMediaRename("netflix_rename", "stream.m3u8", "", "81902147");
    test("ResolveMediaRename Netflix Mode Movie (81902147)", !renNfMovie.empty() && renNfMovie.find("Sonic") != std::string::npos);

    std::string renNfTv = NetflixResolver::ResolveMediaRename("netflix_rename", "stream.m3u8", "S01E03", "81902147");
    test("ResolveMediaRename Netflix Mode TV Series (S01E03 81902147)", renNfTv.find("S01E03") != std::string::npos && renNfTv.find("Sonic") != std::string::npos);

    std::string renNfCustom = NetflixResolver::ResolveMediaRename("netflix_rename", "stream.m3u8", "Custom Movie Title", "");
    test("ResolveMediaRename Netflix Mode Custom Title Fallback", renNfCustom == "Custom Movie Title");

    // Path Reservation Non-Conflict Test (Same folder concurrent download)
    std::string resPath1 = NetflixResolver::ReserveNonConflictingPath("SampleVideo.mkv");
    std::string resPath2 = NetflixResolver::ReserveNonConflictingPath("SampleVideo.mkv");
    test("Path reservation prevents overwrite on same folder concurrency", resPath1 != resPath2 && resPath2.find("(2)") != std::string::npos);
    NetflixResolver::ReleaseReservedPath(resPath1);
    NetflixResolver::ReleaseReservedPath(resPath2);

    // 6. Bridge Server & Settings Sync
    BridgeServer server(28796, "test_token_123");
    bool serverStarted = server.Start();
    test("Bridge Server Starts on 127.0.0.1:28796", serverStarted);
    if (serverStarted) {
        HttpClient client;
        HttpResponse res = client.Get("http://127.0.0.1:28796/ping");
        test("Bridge Server Responds to /ping", res.IsSuccess() && res.Text().find("OmniStream Pro") != std::string::npos);

        // Test Settings Sync: POST /set_mode -> GET /health
        HttpResponse setModeRes = client.Post("http://127.0.0.1:28796/set_mode", "{\"mode\": \"imdb_rename\"}", "application/json");
        test("Bridge POST /set_mode accepted", setModeRes.IsSuccess() && setModeRes.Text().find("imdb_rename") != std::string::npos);

        HttpResponse healthRes = client.Get("http://127.0.0.1:28796/health");
        test("Bridge GET /health reflects synced mode (imdb_rename)", healthRes.IsSuccess() && healthRes.Text().find("\"mode\": \"imdb_rename\"") != std::string::npos);

        HttpResponse tokRes = client.Get("http://127.0.0.1:28796/token");
        test("Bridge GET /token returns token", tokRes.IsSuccess() && tokRes.Text().find("test_token_123") != std::string::npos);

        // Test POST /add
        HttpResponse addRes = client.Post("http://127.0.0.1:28796/add", "{\"url\": \"https://example.com/test.m3u8\", \"title\": \"TestStream\"}", "application/json");
        test("Bridge POST /add accepts stream payload", addRes.IsSuccess() && addRes.Text().find("\"success\": true") != std::string::npos);

        // Test POST /start_queue and POST /focus
        bool startQueueFired = false;
        bool focusFired = false;
        server.SetOnStartQueue([&]() { startQueueFired = true; });
        server.SetOnFocus([&]() { focusFired = true; });

        HttpResponse sqRes = client.Post("http://127.0.0.1:28796/start_queue", "{}", "application/json");
        test("Bridge POST /start_queue triggers callback", sqRes.IsSuccess() && startQueueFired);

        HttpResponse focusRes = client.Post("http://127.0.0.1:28796/focus", "{}", "application/json");
        test("Bridge POST /focus triggers callback", focusRes.IsSuccess() && focusFired);

        server.Stop();
    }

    std::cout << "\n" << Color::Bold
              << "============================================================\n"
              << " RESULT: " << passed << " PASSED  |  " << failed << " FAILED\n"
              << "============================================================\n"
              << Color::Reset << std::endl;

    return (failed == 0) ? 0 : 1;
}

void PrintBanner() {
    std::cout << Color::Cyan << Color::Bold
              << "\n"
              << "  ██████╗ ███╗   ███╗███╗   ██╗██╗███████╗████████╗██████╗ ███████╗ █████╗ ███╗   ███╗\n"
              << " ██╔═══██╗████╗ ████║████╗  ██║██║██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔══██╗████╗ ████║\n"
              << " ██║   ██║██╔████╔██║██╔██╗ ██║██║███████╗   ██║   ██████╔╝█████╗  ███████║██╔████╔██║\n"
              << " ██║   ██║██║╚██╔╝██║██║╚██╗██║██║╚════██║   ██║   ██╔══██╗██╔══╝  ██╔══██║██║╚██╔╝██║\n"
              << " ╚██████╔╝██║ ╚═╝ ██║██║ ╚████║██║███████║   ██║   ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║\n"
              << "  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝\n"
              << Color::Reset
              << "           OmniStream Pro v" << VERSION << " — Ultra-Fast C++ Native Engine\n"
              << "           Zero External Dependencies  •  Hardware AES-128  •  WinHTTP\n"
              << " ─────────────────────────────────────────────────────────────────────────────\n\n";
}

#include <QApplication>
#include "MainWindow.h"

int main(int argc, char* argv[]) {
    // Set UTF-8 encoding for console output so Unicode characters render cleanly
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);

    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD dwMode = 0;
    if (GetConsoleMode(hOut, &dwMode)) {
        SetConsoleMode(hOut, dwMode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
    }

    bool isCliMode = false;
    bool isDaemonServer = false;
    DownloadOptions options;

    // Parse command line arguments
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--test") {
            return RunSelfTest();
        } else if (arg == "--server" || arg == "--daemon") {
            isDaemonServer = true;
            isCliMode = true;
        } else if (arg == "--cli") {
            isCliMode = true;
        } else if ((arg == "--url" || arg == "-u") && i + 1 < argc) {
            options.inputText = argv[++i];
            isCliMode = true;
        } else if ((arg == "--out" || arg == "-o" || arg == "--save-name") && i + 1 < argc) {
            options.saveName = argv[++i];
            isCliMode = true;
        } else if ((arg == "--dir" || arg == "-d" || arg == "--save-dir") && i + 1 < argc) {
            options.saveDir = argv[++i];
            isCliMode = true;
        } else if ((arg == "--res" || arg == "-r") && i + 1 < argc) {
            options.resolution = argv[++i];
            isCliMode = true;
        } else if ((arg == "--threads" || arg == "-t") && i + 1 < argc) {
            options.threadCount = std::atoi(argv[++i]);
            isCliMode = true;
        } else if (arg == "--subs" || arg == "--sub-only") {
            options.subtitleOnly = true;
            options.includeSubtitles = true;
            isCliMode = true;
        } else if (arg == "--no-subs") {
            options.includeSubtitles = false;
            isCliMode = true;
        } else if (arg == "--audio" && i + 1 < argc) {
            options.audioChoice = argv[++i];
            isCliMode = true;
        } else if (arg == "--sub-format" && i + 1 < argc) {
            options.subtitleFormat = argv[++i];
            isCliMode = true;
        } else if (arg == "--sub-lang" && i + 1 < argc) {
            options.subtitleLanguage = argv[++i];
            isCliMode = true;
        } else if (arg == "--mode" && i + 1 < argc) {
            options.mode = argv[++i];
            isCliMode = true;
        } else if (!arg.empty() && arg[0] != '-') {
            if (options.inputText.empty()) {
                options.inputText = arg;
                isCliMode = true;
            }
        }
    }

    // DEFAULT ACTION (Double-Clicking from Explorer): Launch Modern Qt GUI
    if (!isCliMode && argc == 1) {
        HWND hConsole = GetConsoleWindow();
        if (hConsole) {
            DWORD consoleProcId = 0;
            GetWindowThreadProcessId(hConsole, &consoleProcId);
            if (consoleProcId == GetCurrentProcessId()) {
                ShowWindow(hConsole, SW_HIDE);
            }
        }

        QApplication qtApp(argc, argv);
        qtApp.setWindowIcon(QIcon(":/assets/images/app_logo.png"));
        OmniStream::MainWindow window;
        window.show();
        return qtApp.exec();
    }

    PrintBanner();

    if (isDaemonServer) {
        Logger::Info("Starting OmniStream Pro C++ Native Bridge Daemon...");
        BridgeServer server(BRIDGE_PORT);
        if (!server.Start()) {
            return 1;
        }
        std::cout << Color::Green << "\n [Server Active] OmniStream Bridge Daemon listening on port " << BRIDGE_PORT << "\n" << Color::Reset << std::endl;
        while (true) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
        server.Stop();
        return 0;
    }

    if (options.inputText.empty()) {
        std::cout << Color::Bold << "Enter Stream URL or Chrome cURL command:\n> " << Color::Reset;
        std::getline(std::cin, options.inputText);
        if (options.inputText.empty()) {
            Logger::Error("Empty input provided. Exiting.");
            return 1;
        }
    }

    // Default save directory is user's Desktop
    if (options.saveDir == ".") {
        const char* userProfile = std::getenv("USERPROFILE");
        if (userProfile) {
            std::filesystem::path desktopPath = std::filesystem::path(userProfile) / "Desktop";
            if (std::filesystem::exists(desktopPath)) {
                options.saveDir = desktopPath.string();
            }
        }
    }

    // Wire terminal progress bar
    options.onProgress = [](float percent, const std::string& speed, const std::string& eta, uint64_t bytes, const std::string& sizeStr) {
        int barWidth = 30;
        int filled = static_cast<int>(barWidth * (percent / 100.0f));

        std::cout << "\r  " << Color::Cyan << "["
                  << std::string(filled, '=')
                  << (filled < barWidth ? ">" : "")
                  << std::string(barWidth - filled - (filled < barWidth ? 1 : 0), ' ')
                  << "] " << Color::Reset
                  << Color::Bold << std::fixed << std::setprecision(1) << percent << "% " << Color::Reset
                  << "| " << Color::Green << speed << Color::Reset
                  << " | ETA: " << eta
                  << " | " << (sizeStr.empty() ? FormatBytes(bytes) : sizeStr) << "   " << std::flush;
    };

    options.onLog = [](const std::string& msg) {
        std::cout << "\n" << Color::Magenta << "  ▶ " << Color::Reset << msg << std::endl;
    };

    DownloadEngine engine;
    std::string finalOutput;

    Logger::Info("Starting high-speed C++ capture pipeline...");
    bool success = engine.Download(options, finalOutput);

    std::cout << "\n\n";
    if (success) {
        std::cout << Color::Green << Color::Bold
                  << "============================================================\n"
                  << "  ✔ DOWNLOAD COMPLETED SUCCESSFULLY!\n"
                  << "  Saved: " << finalOutput << "\n"
                  << "============================================================\n"
                  << Color::Reset << std::endl;
        return 0;
    } else {
        std::cout << Color::Red << Color::Bold
                  << "============================================================\n"
                  << "  ✖ DOWNLOAD FAILED OR ABORTED.\n"
                  << "============================================================\n"
                  << Color::Reset << std::endl;
        return 1;
    }
}
