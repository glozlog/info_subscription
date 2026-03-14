@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_webapp_and_open.ps1"
set EC=%ERRORLEVEL%
if not "%EC%"=="0" (
  echo.
  echo Console start failed with exit code %EC%.
  echo.
  pause
)
endlocal
