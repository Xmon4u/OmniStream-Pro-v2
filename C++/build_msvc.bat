@echo off
setlocal enabledelayedexpansion
title OmniStream Pro - Visual Studio 2022 MSVC Builder
cd /d "%~dp0"

echo ============================================================
echo   OmniStream Pro - Visual Studio 2022 (MSVC) Build Script
echo ============================================================
echo.

set "CMAKE_BIN="
where cmake >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "CMAKE_BIN=cmake"
) else if exist "D:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" (
    set "CMAKE_BIN=D:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" (
    set "CMAKE_BIN=%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe" (
    set "CMAKE_BIN=%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
)

if not defined CMAKE_BIN (
    echo [ERROR] CMake not found in PATH or Visual Studio 2022!
    pause
    exit /b 1
)

echo [1/3] Configuring CMake project...
if not exist "vs_project" mkdir "vs_project"
"%CMAKE_BIN%" -B vs_project -S . -DCMAKE_PREFIX_PATH="D:/Qt/6.6.3/msvc2019_64"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] CMake configuration failed!
    pause
    exit /b 1
)

echo.
echo [2/3] Building Release configuration with MSVC...
"%CMAKE_BIN%" --build vs_project --config Release
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Compilation failed!
    pause
    exit /b 1
)

if exist "vs_project\Release\OmniStream_Pro.exe" (
    copy /Y "vs_project\Release\OmniStream_Pro.exe" "OmniStream_Pro.exe" >nul
)

echo.
echo ============================================================
echo [SUCCESS] OmniStream_Pro.exe built successfully!
echo Output: %~dp0OmniStream_Pro.exe
echo ============================================================
echo.
echo [3/3] Running Automated Self-Tests (--test)...
.\OmniStream_Pro.exe --test
echo.
echo All tests completed.
pause

