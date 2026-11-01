@echo off
setlocal
cd /d "%~dp0"
if not exist "build\omnistream_selftest.exe" (
    echo [Notice] Executable not found. Running build.bat first...
    call build.bat
)
echo.
echo ============================================================
echo   Executing OmniStream Pro C++ Automated Self-Tests
echo ============================================================
build\omnistream_selftest.exe
pause

