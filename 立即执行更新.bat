@echo off
setlocal
cd /d "%~dp0"
call "%~dp0.venv\Scripts\activate.bat" >nul 2>nul
python -u main.py --run-3days
echo.
pause
endlocal
