@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\register_console_task.ps1"
set EC=%ERRORLEVEL%
if not "%EC%"=="0" (
  echo.
  echo Install console task failed with exit code %EC%.
  echo.
  pause
)
endlocal
