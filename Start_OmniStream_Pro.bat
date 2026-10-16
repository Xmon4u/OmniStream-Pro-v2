@echo off
title OmniStream Pro v2.0 - Universal Stream Downloader
cd /d "%~dp0"

if exist "release_output\OmniStream_Pro.exe" (
    start "" "release_output\OmniStream_Pro.exe"
    exit /b
)

if exist "desktop\dist\OmniStream_Pro.exe" (
    start "" "desktop\dist\OmniStream_Pro.exe"
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
