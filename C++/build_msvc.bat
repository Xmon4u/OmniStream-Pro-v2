@echo off
setlocal enabledelayedexpansion
title OmniStream Pro - Visual Studio 2022 MSVC Builder
cd /d "%~dp0"

echo ============================================================
echo   OmniStream Pro - Visual Studio 2022 (MSVC) Build Script
echo ============================================================
echo.

set "VS_VCVARS="
if exist "D:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_VCVARS=D:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_VCVARS=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
)

if not defined VS_VCVARS (
    echo [ERROR] Visual Studio 2022 vcvars64.bat not found!
    echo Checked D:\Program Files\Microsoft Visual Studio\2022\Community
    pause
    exit /b 1
)

echo [1/3] Initializing Visual Studio 2022 x64 Environment...
call "%VS_VCVARS%" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to initialize Visual Studio environment.
    pause
    exit /b 1
)
echo [OK] MSVC Environment Loaded.
cl /? | findstr /i "Optimizing"

echo.
echo [2/3] Compiling Windows Application Icon and Manifest Resources...
rc /fo resource.res resource.rc
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Resource compilation failed.
    pause
    exit /b 1
)
echo [OK] resource.res generated.

echo.
echo [3/3] Compiling C++ Native Engine with MSVC (/std:c++17 /O2)...
cl /EHsc /std:c++17 /O2 /utf-8 /DUNICODE /D_UNICODE /Iinclude src\*.cpp resource.res winhttp.lib ws2_32.lib bcrypt.lib dwmapi.lib comctl32.lib gdi32.lib ole32.lib user32.lib shell32.lib uxtheme.lib msimg32.lib /Fe:OmniStream_Pro.exe
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Compilation failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] OmniStream_Pro.exe built successfully with Visual Studio 2022!
echo Output: %~dp0OmniStream_Pro.exe
echo ============================================================
echo.
echo Running Automated Self-Tests (--test)...
OmniStream_Pro.exe --test
echo.
echo All tests completed.
