cmake_minimum_required(VERSION 3.16)
project(OmniStreamProCpp VERSION 2.6.0 LANGUAGES CXX RC)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

# Qt 6 path on D:\Qt
list(APPEND CMAKE_PREFIX_PATH "D:/Qt/6.6.3/msvc2019_64")
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)

include_directories(include ui)

set(SOURCES
    src/bridge_server.cpp
    src/crypto.cpp
    src/curl_parser.cpp
    src/download_engine.cpp
    src/hls_parser.cpp
    src/http_client.cpp
    src/main.cpp
    src/muxer.cpp
    src/netflix_resolver.cpp
    ui/MainWindow.cpp
)

set(HEADERS
    ui/MainWindow.h
)

set(RESOURCES
    resources.qrc
    resource.rc
)

add_executable(omnistream_pro ${SOURCES} ${HEADERS} ${RESOURCES})

target_link_libraries(omnistream_pro PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    winhttp
    ws2_32
    bcrypt
    dwmapi
    comctl32
    gdi32
    ole32
    user32
    shell32
    uxtheme
    msimg32
)

set_target_properties(omnistream_pro PROPERTIES
    OUTPUT_NAME "OmniStream_Pro"
    CXX_EXTENSIONS OFF
)
