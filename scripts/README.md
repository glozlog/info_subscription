# Scripts

## run_webapp.ps1

Runs the Streamlit Web UI on port 8501 from the project root and tries to use the local `.venv`.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_webapp.ps1
```

## Double-Click Launcher

Double-click [启动控制台.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%90%AF%E5%8A%A8%E6%8E%A7%E5%88%B6%E5%8F%B0.bat) to start the Web UI and open the default browser.

## Console Auto-Start (recommended)

- Double-click [安装控制台常驻任务.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%AE%89%E8%A3%85%E6%8E%A7%E5%88%B6%E5%8F%B0%E5%B8%B8%E9%A9%BB%E4%BB%BB%E5%8A%A1.bat) to run the console automatically at logon (hidden background).
- Double-click [卸载控制台常驻任务.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%8D%B8%E8%BD%BD%E6%8E%A7%E5%88%B6%E5%8F%B0%E5%B8%B8%E9%A9%BB%E4%BB%BB%E5%8A%A1.bat) to remove it.

## Wechat2RSS (WeChat)

- Create `wechat2rss/.env` (the launcher creates it automatically if missing), then fill `LIC_EMAIL`, `LIC_CODE`, `RSS_HOST`.
- Double-click [启动Wechat2RSS.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%90%AF%E5%8A%A8Wechat2RSS.bat) to start it (Docker Desktop must be running).
- Open: `http://localhost:8080`
- Troubleshooting: double-click [查看Wechat2RSS状态.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E6%9F%A5%E7%9C%8BWechat2RSS%E7%8A%B6%E6%80%81.bat)

## Keep Running After Closing Trae (Windows)

### Option A: Task Scheduler (recommended)

1. Open Task Scheduler.
2. Create Task…
3. Triggers: At log on (or At startup).
4. Actions: Start a program
   - Program/script: `powershell`
   - Add arguments: `-ExecutionPolicy Bypass -File "D:\TRAE\信息订阅\scripts\run_webapp.ps1"`
   - Start in: `D:\TRAE\信息订阅`
5. Settings: enable “Restart the task if it fails”.

### Option B: Run manually in a separate PowerShell window

```powershell
powershell -ExecutionPolicy Bypass -File D:\TRAE\信息订阅\scripts\run_webapp.ps1
```

## Daily Update (07:00)

- Double-click [安装每日定时更新任务.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%AE%89%E8%A3%85%E6%AF%8F%E6%97%A5%E5%AE%9A%E6%97%B6%E6%9B%B4%E6%96%B0%E4%BB%BB%E5%8A%A1.bat) to register a Windows Task Scheduler task (runs `main.py --run-3days` at 07:00).
- Double-click [卸载每日定时更新任务.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E5%8D%B8%E8%BD%BD%E6%AF%8F%E6%97%A5%E5%AE%9A%E6%97%B6%E6%9B%B4%E6%96%B0%E4%BB%BB%E5%8A%A1.bat) to remove the task.
- Double-click [立即执行更新.bat](file:///D:/TRAE/%E4%BF%A1%E6%81%AF%E8%AE%A2%E9%98%85/%E7%AB%8B%E5%8D%B3%E6%89%A7%E8%A1%8C%E6%9B%B4%E6%96%B0.bat) to run an update immediately.
