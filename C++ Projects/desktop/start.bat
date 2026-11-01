@echo off
setlocal
cd /d "%~dp0"
if not exist "build\OmniStreamPro.exe" (
    echo [Notice] Binary not built yet. Running build.bat first...
    call build.bat
)
start "" "%~dp0build\OmniStreamPro.exe"
exit
