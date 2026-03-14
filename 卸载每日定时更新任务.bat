@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\unregister_daily_update_task.ps1"
echo.
pause
endlocal
