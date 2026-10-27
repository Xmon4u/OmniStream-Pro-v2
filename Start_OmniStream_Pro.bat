@echo off
title OmniStream Pro v2.6.0 - Universal Stream Downloader
cd /d "%~dp0"

if exist "C++\vs_project\Release\OmniStream_Pro.exe" (
    start "" "C++\vs_project\Release\OmniStream_Pro.exe"
    exit /b
)

if exist "c++ projects\vs_project\Release\OmniStream_Pro.exe" (
    start "" "c++ projects\vs_project\Release\OmniStream_Pro.exe"
    exit /b
)

if exist "release_output\OmniStream_Pro.exe" (
    start "" "release_output\OmniStream_Pro.exe"
    exit /b
)

if exist "Release Test\OmniStream_Pro.exe" (
    start "" "Release Test\OmniStream_Pro.exe"
    exit /b
)

if exist "desktop\main_gui.py" (
    cd desktop
    python main_gui.py
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [Error] Failed to launch OmniStream Pro.
        echo Please make sure Python 3.10+ and customtkinter are installed.
        echo Run: pip install customtkinter
        pause
    )
    exit /b
)
