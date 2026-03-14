@echo off
setlocal

REM Check if Docker is installed
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [Error] Docker is not installed or not in PATH.
    echo Please install Docker Desktop for Windows first: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

REM Create directory for RSSHub
set "INSTALL_DIR=D:\rsshub"
if not exist "%INSTALL_DIR%" (
    echo [Info] Creating directory %INSTALL_DIR%...
    mkdir "%INSTALL_DIR%"
)

REM Create docker-compose.yml for RSSHub
echo [Info] Generating docker-compose.yml...
(
echo version: '3.8'
echo services:
echo   rsshub:
echo     image: diygod/rsshub:latest
echo     container_name: rsshub
echo     restart: always
echo     ports:
echo       - "1200:1200"
echo     environment:
echo       - NODE_ENV=production
echo       - CACHE_TYPE=memory
echo       - PUPPETEER_WS_ENDPOINT=ws://browserless:3000
echo     depends_on:
echo       - browserless
echo   browserless:
echo     image: browserless/chrome:latest
echo     container_name: browserless
echo     restart: always
) > "%INSTALL_DIR%\docker-compose.yml"

REM Start the service
echo [Info] Starting RSSHub service...
cd /d "%INSTALL_DIR%"
docker-compose up -d

if %errorlevel% equ 0 (
    echo.
    echo [Success] RSSHub service started successfully!
    echo.
    echo It provides RSS feeds for thousands of websites, including Bilibili, Douyin, Weibo, etc.
    echo.
    echo Service URL: http://localhost:1200
    echo.
    echo [Usage Examples]
    echo Bilibili User: http://localhost:1200/bilibili/user/video/USER_ID
    echo Douyin User: http://localhost:1200/douyin/user/USER_ID
    echo.
) else (
    echo [Error] Failed to start RSSHub service. Please check Docker status.
)

pause
