@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_wechat2rss.ps1"
set EC=%ERRORLEVEL%
if not "%EC%"=="0" (
  echo.
  echo Wechat2RSS start failed with exit code %EC%.
  echo.
  pause
)
endlocal
