@echo off
title OmniStream Pro v2.6.0 - Universal Stream Downloader
cd /d "%~dp0"

if exist "OmniStream_Pro.exe" (
    start "" "OmniStream_Pro.exe"
    exit /b
)

if exist "release_output\OmniStream_Pro.exe" (
    start "" "release_output\OmniStream_Pro.exe"
    exit /b
)

if exist "C++ Projects\desktop\build\Release\OmniStreamPro.exe" (
    start "" "C++ Projects\desktop\build\Release\OmniStreamPro.exe"
    exit /b
)

if exist "desktop\main_gui.py" (
    cd desktop
    python main_gui.py
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo [Error] Failed to launch OmniStream Pro.
        pause
    )
    exit /b
)

echo [Error] OmniStream Pro executable not found.
pause
