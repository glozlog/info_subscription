import sys
import json
import os
import subprocess
from playwright.sync_api import sync_playwright, Error as PlaywrightError

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
             "MicroMessenger/8.0.35(0x18002335) NetType/WIFI Language/zh_CN")

def fetch(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=MOBILE_UA,
            locale="zh-CN",
            viewport={"width": 375, "height": 812},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#js_content", timeout=20000)
        txt = ""
        try:
            txt = page.inner_text("#js_content").strip()
        except:
            txt = page.text_content("#js_content") or ""
            txt = txt.strip()
        title = ""
        try:
            title = page.inner_text("#activity-name").strip()
        except:
            title = ""
        browser.close()
        return {"title": title, "content": txt}

def ensure_browser_installed():
    exe = os.path.join(os.getcwd(), ".venv", "Scripts", "playwright.exe")
    cmd = [exe if os.path.exists(exe) else "playwright", "install", "chromium"]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        return True
    except Exception:
        return False

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw else {}
        url = data.get("url")
        if not url:
            print("Missing url", file=sys.stderr)
            sys.exit(1)
        try:
            res = fetch(url)
        except PlaywrightError:
            ok = ensure_browser_installed()
            if not ok:
                print("Playwright browsers not installed", file=sys.stderr)
                sys.exit(1)
            res = fetch(url)
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
