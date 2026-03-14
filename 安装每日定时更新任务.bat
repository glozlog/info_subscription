@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\register_daily_update_task.ps1"
set EC=%ERRORLEVEL%
if not "%EC%"=="0" (
  echo.
  echo Install task failed with exit code %EC%.
  echo.
  pause
)
endlocal
