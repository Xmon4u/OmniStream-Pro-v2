@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo   Building OmniStream Pro Native C++20 Desktop Application
echo ============================================================

call "D:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 (
    echo [Error] Failed to initialize MSVC x64 build environment.
    exit /b 1
)

set "PATH=D:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;D:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;%PATH%"

cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo [Error] CMake configuration failed.
    exit /b 1
)

cmake --build build --config Release
if errorlevel 1 (
    echo [Error] Build compilation failed.
    exit /b 1
)

echo.
echo Deploying Qt6 Release runtime libraries...
if not exist "build\bin" mkdir "build\bin"
copy /y "bin\ffmpeg.exe" "build\bin\" >nul 2>&1
copy /y "bin\N_m3u8DL-RE.exe" "build\bin\" >nul 2>&1

"D:\Qt\6.6.3\msvc2019_64\bin\windeployqt.exe" --release --no-translations --compiler-runtime build\OmniStreamPro.exe >nul 2>&1

echo.
echo ============================================================
echo   BUILD SUCCESSFUL!
echo   Binaries generated at: %~dp0build\
echo ============================================================

