@echo off
setlocal enabledelayedexpansion
title OmniStream Pro v2.6.0 - C++ Native Engine Builder
cd /d "%~dp0"

echo ============================================================
echo   OmniStream Pro v2.6.0 — C++ Native Engine 1-Click Builder
echo ============================================================
echo.
:: Check D:\Dev\w64devkit\bin
if exist "D:\Dev\w64devkit\bin\g++.exe" (
    set "PATH=D:\Dev\w64devkit\bin;!PATH!"
)

:: 1. Check for g++
where g++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Found GCC / MinGW compiler:
    g++ --version | findstr /i "g++"
    echo.
    echo Compiling Windows icon and version resource...
    windres resource.rc -O coff -o resource.res
    echo Compiling with g++ (High-Performance -O3) + Embedded Icon + Native GUI...
    g++ -std=c++17 -O3 -Iinclude src\*.cpp resource.res -lwinhttp -lws2_32 -lbcrypt -ldwmapi -lcomctl32 -lgdi32 -lole32 -o OmniStream_Pro.exe
    if %ERRORLEVEL% EQU 0 (
        goto :SUCCESS
    ) else (
        echo [ERROR] g++ compilation failed.
        pause
        exit /b 1
    )
)

:: 2. Check for clang++
where clang++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Found Clang compiler:
    clang++ --version | findstr /i "clang"
    echo.
    echo Compiling Windows icon and version resource...
    windres resource.rc -O coff -o resource.res
    echo Compiling with clang++ (High-Performance -O3) + Embedded Icon + Native GUI...
    clang++ -std=c++17 -O3 -Iinclude src\*.cpp resource.res -lwinhttp -lws2_32 -lbcrypt -ldwmapi -lcomctl32 -lgdi32 -lole32 -o OmniStream_Pro.exe
    if %ERRORLEVEL% EQU 0 (
        goto :SUCCESS
    ) else (
        echo [ERROR] clang++ compilation failed.
        pause
        exit /b 1
    )
)

:: 3. Check for MSVC cl.exe
where cl >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Found Microsoft Visual C++ compiler:
    cl /? | findstr /i "Optimizing"
    echo.
    echo Compiling Windows icon and version resource...
    rc /fo resource.res resource.rc
    echo Compiling with cl.exe (High-Performance /O2) + Embedded Icon + Native GUI...
    cl /EHsc /std:c++17 /O2 /utf-8 /Iinclude src\*.cpp resource.res winhttp.lib ws2_32.lib bcrypt.lib dwmapi.lib comctl32.lib gdi32.lib ole32.lib user32.lib shell32.lib uxtheme.lib msimg32.lib /Fe:OmniStream_Pro.exe
    if %ERRORLEVEL% EQU 0 (
        goto :SUCCESS
    ) else (
        echo [ERROR] cl.exe compilation failed.
        pause
        exit /b 1
    )
)

:: 4. If Visual Studio is installed on system, try loading vcvarsall.bat
set "VS_PATH="
if exist "D:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_PATH=D:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_PATH=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_PATH=%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
) else if exist "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" (
    set "VS_PATH=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
)

if defined VS_PATH (
    echo [INFO] Found Visual Studio 2022. Initializing MSVC environment...
    call "%VS_PATH%"
    echo Compiling Windows icon and version resource...
    rc /fo resource.res resource.rc
    echo Compiling with cl.exe (High-Performance /O2) + Embedded Icon + Native GUI...
    cl /EHsc /std:c++17 /O2 /utf-8 /Iinclude src\*.cpp resource.res winhttp.lib ws2_32.lib bcrypt.lib dwmapi.lib comctl32.lib gdi32.lib ole32.lib user32.lib shell32.lib uxtheme.lib msimg32.lib /Fe:OmniStream_Pro.exe
    if %ERRORLEVEL% EQU 0 (
        goto :SUCCESS
    )
)

:: 5. No compiler detected
echo [!] No C++ compiler (g++, clang++, or MSVC cl.exe) found in system PATH.
echo.
echo You can easily install a C++ compiler using either:
echo   1. winget install LLVM.LLVM
echo   2. Or install Visual Studio Community (Desktop development with C++)
echo   3. Or install MinGW-w64
echo.
pause
exit /b 1

:SUCCESS
echo.
echo ============================================================
echo   BUILD SUCCESSFUL: OmniStream_Pro.exe is ready!
echo ============================================================
echo.
echo Running Built-In Native Self-Test:
.\OmniStream_Pro.exe --test
echo.
pause
