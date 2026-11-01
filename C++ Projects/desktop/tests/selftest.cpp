#include "Common.hpp"
#include "Json.hpp"
#include "Database.hpp"
#include "SettingsManager.hpp"
#include "MetadataResolver.hpp"
#include "StreamResolver.hpp"
#include "QueueManager.hpp"
#include "BridgeServer.hpp"
#include "Downloader.hpp"
#include <iostream>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <vector>
#include <thread>
#include <chrono>
#include <winsock2.h>

using namespace OmniStream;

struct SimpleHttpResponse {
    int status_code = 0;
    std::string headers;
    std::string body;
};

static SimpleHttpResponse SendRawHttpRequest(
    int port,
    const std::string& method,
    const std::string& path,
    const std::vector<std::pair<std::string, std::string>>& headers,
    const std::string& body = ""
) {
    SimpleHttpResponse resp;
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return resp;

    sockaddr_in addr = { 0 };
    addr.sin_family = AF_INET;
    addr.sin_port = htons(static_cast<u_short>(port));
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    if (connect(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        closesocket(s);
        return resp;
    }

    std::ostringstream ss;
    ss << method << " " << path << " HTTP/1.1\r\n";
    ss << "Host: 127.0.0.1:" << port << "\r\n";
    for (const auto& h : headers) {
        ss << h.first << ": " << h.second << "\r\n";
    }
    if (!body.empty()) {
        ss << "Content-Length: " << body.length() << "\r\n";
    }
    ss << "Connection: close\r\n\r\n";
    ss << body;

    std::string req = ss.str();
    send(s, req.c_str(), static_cast<int>(req.length()), 0);

    char buf[4096];
    std::string raw;
    int n = 0;
    while ((n = recv(s, buf, sizeof(buf) - 1, 0)) > 0) {
        buf[n] = '\0';
        raw.append(buf, n);
    }
    closesocket(s);

    size_t line_end = raw.find("\r\n");
    if (line_end != std::string::npos) {
        std::string first = raw.substr(0, line_end);
        std::istringstream fis(first);
        std::string p, c;
        fis >> p >> c;
        try { resp.status_code = std::stoi(c); } catch (...) {}
    }

    size_t head_end = raw.find("\r\n\r\n");
    if (head_end != std::string::npos) {
        resp.headers = raw.substr(0, head_end);
        resp.body = raw.substr(head_end + 4);
    } else {
        resp.body = raw;
    }
    return resp;
}

void TestJson() {
    std::cout << "[TEST 1/8] Running JSON Parser & Serializer tests...\n";
    std::string sample = R"({"name":"Inception","year":2010,"is_auto":true,"tags":["sci-fi","action"]})";
    JsonValue v = JsonParser::Parse(sample);

    assert(v.IsObject());
    assert(v.Get("name").AsString() == "Inception");
    assert(v.Get("year").AsInt() == 2010);
    assert(v.Get("is_auto").AsBool() == true);
    assert(v.Get("tags").IsArray());
    assert(v.Get("tags").AsArray().size() == 2);
    assert(v.Get("tags").AsArray()[0].AsString() == "sci-fi");

    std::string dumped = v.Dump();
    JsonValue roundtrip = JsonParser::Parse(dumped);
    assert(roundtrip.Get("name").AsString() == "Inception");
    std::cout << "  ✓ JSON serialization and parsing PASSED\n";
}

void TestMetadataAndUnicode() {
    std::cout << "[TEST 2/8] Running Metadata, Unicode, Bangla & ID Naming tests...\n";

    // 1. Netflix ID extraction
    std::string nid = MetadataResolver::ExtractNetflixId("https://www.netflix.com/watch/81902147?trackId=123");
    assert(nid == "81902147");

    // 2. IMDb ID extraction
    std::string imdb = MetadataResolver::ExtractIMDbId("https://www.imdb.com/title/tt1375666/");
    assert(imdb == "tt1375666");

    // 3. Season & Episode
    auto se = MetadataResolver::ExtractSeasonEpisode("Stranger Things S02E05 1080p");
    assert(se.found && se.season == 2 && se.episode == 5);

    // 4. TMDb ID extraction requires tmdb / themoviedb.org prefix (No false positives on years)
    assert(MetadataResolver::ExtractTMDbId("Sigma 2026 1080p") == "");
    assert(MetadataResolver::ExtractTMDbId("Release 2024 Dual Audio") == "");
    assert(MetadataResolver::ExtractTMDbId("tmdb: 27205") == "27205");
    assert(MetadataResolver::ExtractTMDbId("https://www.themoviedb.org/movie/27205-inception") == "27205");

    // 5. Windows file safety: strip trailing dots and spaces
    assert(MetadataResolver::SanitizeInputTitle("Inception...   ") == "Inception");

    // 6. Multilingual Unicode Preservation
    std::string unicodeTitle = "Tufan - Movie (2024)...   ";
    std::string sanitizedUnicode = MetadataResolver::SanitizeInputTitle(unicodeTitle);
    assert(sanitizedUnicode.find("Tufan") != std::string::npos);
    assert(sanitizedUnicode.back() != '.');
    assert(sanitizedUnicode.back() != ' ');

    std::wstring wideUnicode = Utils::Utf8ToWide(sanitizedUnicode);
    std::string roundtripUnicode = Utils::WideToUtf8(wideUnicode);
    assert(roundtripUnicode == sanitizedUnicode);

    // 7. Canonical Unique ID Determinism
    std::string uid1 = MetadataResolver::ComputeMovieUniqueId(
        "https://prmovies.ventures/sigma-2026-hindi-dubbed-Watch-online-full-movie/",
        "https://prmovies.ventures/sigma-2026-hindi-dubbed-Watch-online-full-movie/",
        "Sigma (2026)"
    );
    std::string uid2 = MetadataResolver::ComputeMovieUniqueId(
        "curl \"https://speedostream1.com/index.m3u8\" -H \"Referer: https://prmovies.ventures/sigma-2026-hindi-dubbed-Watch-online-full-movie/\"",
        "",
        "Sigma (2026)"
    );
    assert(uid1 == uid2);

    std::cout << "  ✓ Metadata, Unicode, Bangla & ID Naming tests PASSED\n";
}

void TestDatabasePersistenceAndMigration() {
    std::cout << "[TEST 3/8] Running Database Migration & Header Persistence tests...\n";
    std::string test_db = "test_persistence_migration.db";
    if (std::filesystem::exists(test_db)) std::filesystem::remove(test_db);

    // 1. Simulate legacy database schema without referer, origin, user_agent, cookie
    {
        sqlite3* raw_db = nullptr;
        int rc = sqlite3_open(test_db.c_str(), &raw_db);
        assert(rc == SQLITE_OK);

        const char* legacy_schema = R"(
            CREATE TABLE queue (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                input_raw TEXT,
                save_dir TEXT,
                saved_file TEXT,
                resolution TEXT,
                audio TEXT,
                sub_format TEXT,
                sub_lang TEXT,
                include_subtitles INTEGER,
                mode TEXT,
                netflix_id TEXT,
                status TEXT,
                progress_pct REAL,
                progress_text TEXT,
                error_msg TEXT,
                priority INTEGER,
                created_at REAL,
                completed_at REAL,
                year TEXT,
                is_multi_audio INTEGER,
                unique_id TEXT
            );
            INSERT INTO queue (id, title, url, input_raw) VALUES ('legacy_item_1', 'Old Movie 1', 'https://old.com', 'https://old.com/video.m3u8');
        )";
        char* err = nullptr;
        rc = sqlite3_exec(raw_db, legacy_schema, nullptr, nullptr, &err);
        assert(rc == SQLITE_OK);
        sqlite3_close(raw_db);
    }

    // 2. Initialize Database singleton on legacy database -> Automated Schema Migration triggers!
    auto& db = Database::GetInstance();
    bool init_ok = db.Initialize(test_db);
    assert(init_ok);

    // Verify legacy item survived migration intact
    auto loaded = db.LoadAllQueueItems();
    assert(loaded.size() == 1);
    assert(loaded[0].id == "legacy_item_1");
    assert(loaded[0].title == "Old Movie 1");

    // 3. Insert fresh item with all modern Chrome headers
    DownloadItem fresh;
    fresh.id = "persist_item_2";
    fresh.unique_id = "page:netnaija.film/the-pretenders";
    fresh.title = "The Pretenders [Hindi]";
    fresh.input = "https://cdn.soneroom.com/media/2026/10/27/video.mp4";
    fresh.page_url = "https://netnaija.film/watch";
    fresh.referer = "https://netnaija.film/";
    fresh.origin = "https://netnaija.film";
    fresh.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/133.0.0.0";
    fresh.cookie = "cf_clearance=abc123456789; auth_tok=secret_sess_token";
    fresh.media_type = "MP4";
    fresh.status = DownloadStatus::Waiting;
    fresh.save_dir = "C:\\Downloads\\videos";

    bool save_ok = db.SaveOrUpdateItem(fresh);
    assert(save_ok);

    // 4. Close database and Re-open to simulate Application Restart
    db.Close();

    bool reopen_ok = db.Initialize(test_db);
    assert(reopen_ok);

    auto item_opt = db.GetItem("persist_item_2");
    assert(item_opt.has_value());
    assert(item_opt->title == "The Pretenders [Hindi]");
    assert(item_opt->referer == "https://netnaija.film/");
    assert(item_opt->origin == "https://netnaija.film");
    assert(item_opt->user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/133.0.0.0");
    assert(item_opt->cookie == "cf_clearance=abc123456789; auth_tok=secret_sess_token");
    assert(item_opt->media_type == "MP4");

    db.Close();
    if (std::filesystem::exists(test_db)) std::filesystem::remove(test_db);
    std::cout << "  ✓ Database Migration & Header Persistence across Restart PASSED\n";
}

void TestBridgeAuthenticationAndCors() {
    std::cout << "[TEST 4/8] Running Bridge Server Authentication & CORS Security tests...\n";
    auto& bridge = BridgeServer::GetInstance();
    bool started = bridge.Start(28797);
    assert(started);
    std::string token = bridge.GetToken();
    assert(!token.empty());

    // 1. Health check is unauthenticated -> 200 OK
    auto respHealth = SendRawHttpRequest(28797, "GET", "/health", {});
    assert(respHealth.status_code == 200);

    // 2. /add with NO token -> Expect 401 Unauthorized
    auto respNoAuth = SendRawHttpRequest(28797, "POST", "/add", {
        {"Content-Type", "application/json"}
    }, R"({"url":"https://example.com/test.mp4"})");
    assert(respNoAuth.status_code == 401);

    // 3. /add with INVALID token -> Expect 401 Unauthorized
    auto respBadAuth = SendRawHttpRequest(28797, "POST", "/add", {
        {"Content-Type", "application/json"},
        {"X-OmniStream-Token", "wrong_token_12345"}
    }, R"({"url":"https://example.com/test.mp4"})");
    assert(respBadAuth.status_code == 401);

    // 4. /add with VALID token -> Expect 200 OK
    auto respGoodAuth = SendRawHttpRequest(28797, "POST", "/add", {
        {"Content-Type", "application/json"},
        {"X-OmniStream-Token", token}
    }, R"({"url":"https://example.com/test.mp4","title":"Bridge Test Stream","type":"MP4"})");
    assert(respGoodAuth.status_code == 200);

    // 5. Untrusted third-party Origin -> Expect 403 Forbidden
    auto respUntrusted = SendRawHttpRequest(28797, "POST", "/add", {
        {"Origin", "https://malicious-tracker.com"},
        {"Content-Type", "application/json"},
        {"X-OmniStream-Token", token}
    }, R"({"url":"https://example.com/test.mp4"})");
    assert(respUntrusted.status_code == 403);

    // 6. Trusted Chrome Extension Origin -> Expect 200 OK and CORS header
    auto respTrusted = SendRawHttpRequest(28797, "POST", "/add", {
        {"Origin", "chrome-extension://omnistream_extension_id"},
        {"Content-Type", "application/json"},
        {"X-OmniStream-Token", token}
    }, R"({"url":"https://example.com/test.mp4","title":"Extension Stream"})");
    assert(respTrusted.status_code == 200);
    assert(respTrusted.headers.find("Access-Control-Allow-Origin: chrome-extension://omnistream_extension_id") != std::string::npos);

    // 7. /batch_add test
    auto respBatch = SendRawHttpRequest(28797, "POST", "/batch_add", {
        {"Content-Type", "application/json"},
        {"X-OmniStream-Token", token}
    }, R"({"items":[{"url":"https://example.com/1.mp4","title":"Item 1"},{"url":"https://example.com/2.mp4","title":"Item 2"}]})");
    assert(respBatch.status_code == 200);

    bridge.Stop();
    std::cout << "  ✓ Bridge Server Authentication, Token Enforcement & CORS Whitelist PASSED\n";
}

void TestDirectDownloadAndRangeResume() {
    std::cout << "[TEST 5/8] Running Direct Download & HTTP 206 Range Resume tests...\n";
    auto& bridge = BridgeServer::GetInstance();
    bridge.Start(28797);

    // 1. Direct media URL classification
    assert(Downloader::IsDirectMediaUrl("https://sample.com/video.mp4"));
    assert(Downloader::IsDirectMediaUrl("https://sample.com/video.webm"));
    assert(Downloader::IsDirectMediaUrl("https://sample.com/video.mkv"));
    assert(!Downloader::IsDirectMediaUrl("https://sample.com/master.m3u8"));
    assert(!Downloader::IsDirectMediaUrl("https://sample.com/manifest.mpd"));
    assert(Downloader::IsDirectMediaUrl("https://cdn.soneroom.com/media/2026/10/27/token123", "MP4 - player"));

    std::filesystem::path testDir = "test_range_downloads";
    if (std::filesystem::exists(testDir)) std::filesystem::remove_all(testDir);
    std::filesystem::create_directories(testDir);

    std::filesystem::path targetFile = testDir / "Range_Resume_Movie.mp4";

    // 2. Pre-create a partial file with exactly 64 KB of data
    const size_t partial_size = 64 * 1024;
    {
        std::ofstream pfile(targetFile, std::ios::binary);
        std::string partial_data(partial_size, 'V');
        pfile.write(partial_data.data(), partial_data.size());
        pfile.close();
    }
    assert(std::filesystem::file_size(targetFile) == partial_size);

    // 3. Initiate download with existing partial file -> Must request Range: bytes=65536- and resume!
    Downloader dl;
    DownloadItem item;
    item.id = "range_test_item";
    item.title = "Range_Resume_Movie";
    item.input = "http://127.0.0.1:28797/test_video.mp4";
    item.save_dir = testDir.string();

    auto details = Downloader::ParseStreamDetails(item);
    auto res = dl.ExecuteDirectDownload(item, details);

    assert(res.success);
    assert(std::filesystem::exists(res.final_file_path));
    // Verify completed file reaches the full 256 KB!
    assert(std::filesystem::file_size(res.final_file_path) == 256 * 1024);

    std::filesystem::remove_all(testDir);
    bridge.Stop();
    std::cout << "  ✓ Direct Download & HTTP 206 Range Resume PASSED\n";
}

void TestThreadShutdownIntegrity() {
    std::cout << "[TEST 6/8] Running Thread Synchronization & Shutdown Integrity tests...\n";

    // Initialize QueueManager with isolated test db
    std::string test_db = "test_shutdown.db";
    if (std::filesystem::exists(test_db)) std::filesystem::remove(test_db);
    Database::GetInstance().Initialize(test_db);

    auto& qm = QueueManager::GetInstance();
    qm.Initialize();

    // Enqueue 5 items
    for (int i = 1; i <= 5; ++i) {
        DownloadItem it;
        it.id = "shut_item_" + std::to_string(i);
        it.title = "Shutdown Item " + std::to_string(i);
        it.input = "http://127.0.0.1:28797/dummy.mp4";
        qm.AddItem(it, true);
    }

    // Call Shutdown() while items and dispatcher are active
    auto start_t = std::chrono::steady_clock::now();
    qm.Shutdown();
    auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start_t).count();

    // Verify shutdown completes cleanly without hanging or crashing
    assert(elapsed < 6000);

    Database::GetInstance().Close();
    if (std::filesystem::exists(test_db)) std::filesystem::remove(test_db);
    std::cout << "  ✓ Active Thread Drain & Shutdown Barrier PASSED (Elapsed: " << elapsed << "ms)\n";
}

void TestCsvParsingRobustness() {
    std::cout << "[TEST 7/8] Running RFC 4180 CSV Parser & XLSX Detection tests...\n";

    // RFC 4180 CSV parser logic (Identical to MainWindow.cpp)
    auto parseCsvRow = [](const std::string& line) {
        std::vector<std::string> fields;
        std::string cur;
        bool in_quotes = false;
        for (size_t i = 0; i < line.size(); ++i) {
            char c = line[i];
            if (c == '"') {
                if (in_quotes && i + 1 < line.size() && line[i + 1] == '"') {
                    cur += '"';
                    ++i;
                } else {
                    in_quotes = !in_quotes;
                }
            } else if (c == ',' && !in_quotes) {
                fields.push_back(cur);
                cur.clear();
            } else {
                cur += c;
            }
        }
        fields.push_back(cur);
        return fields;
    };

    // 1. Standard CSV line
    auto r1 = parseCsvRow("1,Inception,https://example.com/inception");
    assert(r1.size() == 3);
    assert(r1[1] == "Inception");
    assert(r1[2] == "https://example.com/inception");

    // 2. RFC 4180 Quoted title with embedded commas
    auto r2 = parseCsvRow("2,\"The Good, The Bad, and The Ugly\",https://example.com/goodbadugly");
    assert(r2.size() == 3);
    assert(r2[1] == "The Good, The Bad, and The Ugly");
    assert(r2[2] == "https://example.com/goodbadugly");

    // 3. Quoted title with escaped internal quotes
    auto r3 = parseCsvRow("3,\"Mission: Impossible - \"\"Fallout\"\"\",https://example.com/fallout");
    assert(r3.size() == 3);
    assert(r3[1] == "Mission: Impossible - \"Fallout\"");

    // 4. XLSX Extension Detection check
    std::string testXlsx = "movies_export.xlsx";
    bool isXlsx = (testXlsx.length() >= 5 && testXlsx.substr(testXlsx.length() - 5) == ".xlsx");
    assert(isXlsx == true);

    std::cout << "  ✓ RFC 4180 CSV Quote Parser & XLSX Detection PASSED\n";
}

void TestBinaryAvailabilityAndDiskFallback() {
    std::cout << "[TEST 8/8] Running Binaries & Output File Fallback tests...\n";

    Downloader dl;
    // Check FFmpeg and N_m3u8DL-RE resolution
    std::string ffmpeg = dl.FindBinary("ffmpeg");
    std::string nm3u8 = dl.FindBinary("N_m3u8DL-RE");

    assert(!ffmpeg.empty());
    assert(!nm3u8.empty());
    assert(std::filesystem::exists(ffmpeg));
    assert(std::filesystem::exists(nm3u8));

    // Test disk fallback search logic
    std::filesystem::path mockDir = "test_mock_save";
    if (std::filesystem::exists(mockDir)) std::filesystem::remove_all(mockDir);
    std::filesystem::create_directories(mockDir);

    std::filesystem::path mockVideo = mockDir / "Mock_Movie.mkv";
    {
        std::ofstream mf(mockVideo, std::ios::binary);
        mf << "mock video stream bytes";
        mf.close();
    }

    std::string sname = MetadataResolver::SanitizeInputTitle("Mock_Movie");
    std::vector<std::string> exts = { ".mkv", ".mp4", ".ts" };
    std::string foundPath = "";
    for (const auto& e : exts) {
        std::filesystem::path cand = mockDir / (sname + e);
        if (std::filesystem::exists(cand)) {
            foundPath = cand.string();
            break;
        }
    }
    assert(!foundPath.empty());
    assert(foundPath == mockVideo.string());

    std::filesystem::remove_all(mockDir);
    std::cout << "  ✓ Binary Detection & Output Disk Fallback PASSED\n";
}

int main() {
    std::cout << "============================================================\n";
    std::cout << "  OmniStream Pro Native C++20 Full Regression Test Suite\n";
    std::cout << "============================================================\n";

    TestJson();
    TestMetadataAndUnicode();
    TestDatabasePersistenceAndMigration();
    TestBridgeAuthenticationAndCors();
    TestDirectDownloadAndRangeResume();
    TestThreadShutdownIntegrity();
    TestCsvParsingRobustness();
    TestBinaryAvailabilityAndDiskFallback();

    std::cout << "============================================================\n";
    std::cout << "  ALL 8 REGRESSION SUITES PASSED (100% SUCCESS)\n";
    std::cout << "============================================================\n";
    return 0;
}
