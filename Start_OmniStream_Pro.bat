@echo off
title OmniStream Pro v2.0 - Universal Stream Downloader
cd /d "%~dp0desktop"

if exist "..\desktop\dist\OmniStream_Pro.exe" (
    start "" "..\desktop\dist\OmniStream_Pro.exe"
    exit /b
)

if exist "dist\OmniStream_Pro.exe" (
    start "" "dist\OmniStream_Pro.exe"
    exit /b
)

python main_gui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Error] Failed to launch OmniStream Pro.
    echo Please make sure Python 3.10+ and customtkinter are installed.
    echo Run: pip install customtkinter
    pause
)
