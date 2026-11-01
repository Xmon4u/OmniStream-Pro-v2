cmake_minimum_required(VERSION 3.20)
project(OmniStreamPro LANGUAGES CXX RC)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Choose build type" FORCE)
endif()

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

list(APPEND CMAKE_PREFIX_PATH "D:/Qt/6.6.3/msvc2019_64")
find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)

if(MSVC)
    add_compile_options(/W4 /EHsc /utf-8)
    add_compile_definitions(WIN32_LEAN_AND_MEAN NOMINMAX _WINSOCK_DEPRECATED_NO_WARNINGS)
endif()

include_directories(include ui)

set(COMMON_SOURCES
    src/Database.cpp
    src/SettingsManager.cpp
    src/MetadataResolver.cpp
    src/Downloader.cpp
    src/StreamResolver.cpp
    src/QueueManager.cpp
    src/BridgeServer.cpp
    src/NativeMessaging.cpp
    src/ExtensionInstaller.cpp
)

set(UI_SOURCES
    ui/MainWindow.cpp
    ui/SettingsDialog.cpp
)

set(UI_HEADERS
    ui/MainWindow.h
    ui/SettingsDialog.h
)

set(RESOURCES
    resources.qrc
    resource.rc
)

set(PLATFORM_LIBS
    winsqlite3
    ws2_32
    winhttp
    shlwapi
    dwmapi
    uxtheme
    comctl32
    gdi32
    user32
    shell32
    ole32
    msimg32
)

# 1. Main GUI Application Executable (Pure Windows GUI, No Console Window)
add_executable(OmniStreamPro WIN32
    src/main.cpp
    ${COMMON_SOURCES}
    ${UI_SOURCES}
    ${UI_HEADERS}
    ${RESOURCES}
)
target_link_libraries(OmniStreamPro PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Widgets
    ${PLATFORM_LIBS}
)
if(MSVC)
    target_link_options(OmniStreamPro PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)
endif()

# 2. Automated Self-Test Runner Executable
add_executable(omnistream_selftest
    tests/selftest.cpp
    ${COMMON_SOURCES}
)
target_link_libraries(omnistream_selftest PRIVATE ${PLATFORM_LIBS})
