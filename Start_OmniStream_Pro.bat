@echo off
title OmniStream Pro v2.6.0 - Universal Stream Downloader
cd /d "%~dp0"

if exist "C++\OmniStream_Pro.exe" (
    cd C++
    start "" "OmniStream_Pro.exe"
    exit /b
)

if exist "C++\vs_project\Release\OmniStream_Pro.exe" (
    cd C++\vs_project\Release
    start "" "OmniStream_Pro.exe"
    exit /b
)

echo [ERROR] OmniStream_Pro.exe not found in C++ directory!
echo Please run C++\build.bat to compile the native engine.
pause

