@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\wechat2rss_status.ps1"
echo.
pause
endlocal
