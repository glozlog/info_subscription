import sys
import json
import os
import subprocess
from typing import List, Dict
from playwright.sync_api import sync_playwright, Error as PlaywrightError

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
             "MicroMessenger/8.0.35(0x18002335) NetType/WIFI Language/zh_CN")

def fetch_single(url: str) -> dict:
    """抓取单篇文章"""
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
        return {"url": url, "title": title, "content": txt, "success": True}

def fetch_batch(urls: List[str]) -> List[dict]:
    """
    批量抓取多篇文章 - 复用浏览器实例提高效率
    
    Args:
        urls: 文章URL列表
        
    Returns:
        抓取结果列表，每个结果包含 url, title, content, success, error
    """
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        try:
            for url in urls:
                try:
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
                    
                    context.close()
                    
                    results.append({
                        "url": url,
                        "title": title,
                        "content": txt,
                        "success": True
                    })
                    
                except Exception as e:
                    results.append({
                        "url": url,
                        "title": "",
                        "content": "",
                        "success": False,
                        "error": str(e)
                    })
        finally:
            browser.close()
    
    return results

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
        
        # 检查是否为批量模式
        urls = data.get("urls")
        single_url = data.get("url")
        
        if not urls and not single_url:
            print("Missing url or urls", file=sys.stderr)
            sys.exit(1)
        
        # 批量模式
        if urls and isinstance(urls, list):
            try:
                results = fetch_batch(urls)
            except PlaywrightError:
                ok = ensure_browser_installed()
                if not ok:
                    print("Playwright browsers not installed", file=sys.stderr)
                    sys.exit(1)
                results = fetch_batch(urls)
            
            output = {
                "mode": "batch",
                "total": len(urls),
                "success_count": sum(1 for r in results if r.get("success")),
                "failed_count": sum(1 for r in results if not r.get("success")),
                "results": results
            }
        
        # 单篇模式（兼容旧接口）
        else:
            try:
                result = fetch_single(single_url)
            except PlaywrightError:
                ok = ensure_browser_installed()
                if not ok:
                    print("Playwright browsers not installed", file=sys.stderr)
                    sys.exit(1)
                result = fetch_single(single_url)
            
            output = {
                "mode": "single",
                "result": result
            }
        
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        
        print(json.dumps(output, ensure_ascii=False))
        
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
