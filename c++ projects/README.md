# OmniStream Pro v2.5.0 — Native C++ Core Engine

High-performance, low-level native C++ stream capturing engine and localhost bridge for **OmniStream Pro v2.5.0**.

Designed for zero external dependencies on Windows—leverages native Windows cryptographic, networking, and asynchronous socket APIs.

---

## ⚡ মূল বৈশিষ্ট্যসমূহ (Features)

1. **Zero External Dependencies (Windows Native)**
   - **WinHTTP (`winhttp.lib`)**: উচ্চগতির TLS 1.2/1.3 মাল্টি-কানেকশন এইচটিটিপি/এইচটিটিপিএস ইঞ্জিন।
   - **Winsock2 (`ws2_32.lib`)**: Chrome ও Edge ব্রাউজার এক্সটেনশনের জন্য লোকালহোস্ট ব্রিজ সার্ভার (`127.0.0.1:28795`)।
   - **Windows BCrypt (`bcrypt.lib`)**: Intel AES-NI হার্ডওয়্যার এক্সিলারেশনে সরাসরি মেমোরিতে AES-128-CBC HLS ডিক্রিপশন (OpenSSL-এর কোনো প্রয়োজন নেই)।

2. **Full A to Z মডিউল স্ট্রাকচার**
   - **`curl_parser.cpp`**: Chrome DevTools cURL ও কাঁচা URL পার্সিং, হেডার্স (`-H`), কুকিজ (`-b`), এবং ডায়নামিক Origin ও Referer নির্ণয়।
   - **`hls_parser.cpp`**: M3U8 Master ও Media প্লেলিস্ট পার্সার (ভিডিও ভ্যারিয়েন্ট, মাল্টি-অডিও ট্র্যাক, সাবটাইটেল ট্র্যাক, ইনিশিয়ালাইজেশন সেগমেন্ট)।
   - **`download_engine.cpp`**: সমান্তরাল মাল্টি-থ্রেডেড সেগমেন্ট ডাউনলোড (16–64 থ্রেড কনকারেন্সি), রিয়েল-টাইম স্পিড (MB/s), ETA এবং প্রগ্রেস ট্র্যাকিং।
   - **`muxer.cpp`**: সেগমেন্ট জোড়া লাগানো এবং FFmpeg থাকলে লসলেস কন্টেইনারে (`.mkv`/`.mp4`) স্বয়ংক্রিয় মাল্টিপ্লেক্সিং।
   - **`netflix_resolver.cpp`**: Netflix Title, IMDb ID (`tt...`), TMDB ID এক্সট্রাকশন এবং উইন্ডোজ ফাইলনেম স্যানিটাইজার।
   - **`bridge_server.cpp`**: ব্রাউজার এক্সটেনশন থেকে এক ক্লিকে ডাউনলোড রিকোয়েস্ট গ্রহণ করার জন্য নেটিভ HTTP সার্ভার।

---

## 📁 ফোল্ডার স্ট্রাকচার

```
cpp_omnistream/
├── CMakeLists.txt          # CMake কনফিগারেশন ফাইল
├── build.bat               # ১-ক্লিক অটোমেটিক বিল্ড স্ক্রিপ্ট (MSVC, GCC, Clang)
├── README.md               # এই ডকুমেন্টেশন
├── include/
│   ├── common.hpp          # সাধারণ ডেফিনেশন, ANSI কালার ও লগার
│   ├── curl_parser.hpp     # cURL ও URL পার্সার
│   ├── hls_parser.hpp      # M3U8 মাস্টার ও মিডিয়া পার্সার
│   ├── http_client.hpp     # উইন্ডোজ WinHTTP ক্লায়েন্ট
│   ├── crypto.hpp          # BCrypt হার্ডওয়্যার AES-128 ডিক্রিপটর
│   ├── download_engine.hpp # মাল্টি-থ্রেডেড ডাউনলোড ইঞ্জিন
│   ├── muxer.hpp           # স্ট্রিচিং ও FFmpeg মাল্টিপ্লেক্সার
│   ├── netflix_resolver.hpp# Netflix ID ও মেটাডাটা রিজলভার
│   └── bridge_server.hpp   # Winsock2 লোকালহোস্ট ব্রিজ সার্ভার
└── src/
    ├── main.cpp            # CLI এন্ট্রি পয়েন্ট ও সেলফ-টেস্ট স্যুট
    ├── curl_parser.cpp
    ├── hls_parser.cpp
    ├── http_client.cpp
    ├── crypto.cpp
    ├── download_engine.cpp
    ├── muxer.cpp
    ├── netflix_resolver.cpp
    └── bridge_server.cpp
```

---

## 🔨 বিল্ড করার উপায় (Build Instructions)

### পদ্ধতি ১: সহজ ১-ক্লিক স্ক্রিপ্ট
সরাসরি `build.bat`-এ ডাবল ক্লিক করুন অথবা টার্মিনালে চালান:
```cmd
build.bat
```
এটি স্বয়ংক্রিয়ভাবে আপনার মেশিনের `cl.exe` (MSVC), `g++` (MinGW) অথবা `clang++` শনাক্ত করে সর্বোচ্চ অপটিমাইজেশন (`-O3` বা `/O2`) সহ বাইনারি তৈরি করবে এবং বিল্ট-ইন সেলফ-টেস্ট চালাবে।

### পদ্ধতি ২: GCC / MinGW দিয়ে ম্যানুয়ালি
```cmd
g++ -std=c++17 -O3 -Iinclude src\*.cpp -lwinhttp -lws2_32 -lbcrypt -o OmniStream_Pro.exe
```

### পদ্ধতি ৩: MSVC (Visual Studio Command Prompt) দিয়ে ম্যানুয়ালি
```cmd
cl /EHsc /std:c++17 /O2 /Iinclude src\*.cpp winhttp.lib ws2_32.lib bcrypt.lib /Fe:OmniStream_Pro.exe
```

### পদ্ধতি ৪: CMake দিয়ে
```cmd
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

---

## 🚀 কমান্ড-লাইন ব্যবহার (CLI Usage)

### ১. সেলফ-টেস্ট চালানো:
```cmd
OmniStream_Pro.exe --test
```

### ২. সরাসরি cURL বা URL দিয়ে স্ট্রিম ডাউনলোড:
```cmd
OmniStream_Pro.exe --url "https://example.com/playlist.m3u8" --out "MyMovie" --threads 32
```

### ৩. ব্রাউজার এক্সটেনশন ব্রিজ সার্ভার হিসেবে ব্যাকগ্রাউন্ডে চালানো:
```cmd
OmniStream_Pro.exe --server
```
এটি পোর্ট `28795`-এ কানেকশন শুনবে এবং ব্রাউজারে এক্সটেনশন থেকে ডাউনলোড বাটনে চাপলেই সরাসরি ডাউনলোড শুরু হবে।
