@echo off
title InfoSubscription Scheduler
cd /d "%~dp0"

:loop
echo [%date% %time%] Starting InfoSubscription Scheduler...
call .venv\Scripts\activate.bat
python main.py

echo.
echo [%date% %time%] Scheduler stopped/crashed. Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto loop
