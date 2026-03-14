
import os
import time
from playwright.sync_api import sync_playwright

def debug_nickname():
    # Target URLs that failed
    urls = [
        "https://www.douyin.com/user/MS4wLjABAAAA25xxS-4HJ5PYicMjFpvzlYR_oe37SK-ryMNQZs-ilpdFNy7iaGBWl3cyQIsPirtB",
        "https://www.douyin.com/user/MS4wLjABAAAAoXm3UTY6L_aOBfJxd0Y8B9ojQS4rUUWwDK-iEre3opQ"
    ]
    
    user_data_dir = os.path.abspath("browser_data/douyin")
    
    with sync_playwright() as p:
        print(f"Launching browser from {user_data_dir}...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            channel="chrome",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.pages[0] if context.pages else context.new_page()
        
        for url in urls:
            print(f"\nDebugging {url}...")
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(5) # Wait for render
            
            # 1. Try common selectors
            h1 = page.query_selector("h1")
            nick = page.query_selector(".nickname")
            avatar = page.query_selector(".avatar-component img")
            
            print(f"  h1 text: {h1.inner_text() if h1 else 'Not found'}")
            print(f"  .nickname text: {nick.inner_text() if nick else 'Not found'}")
            print(f"  avatar alt: {avatar.get_attribute('alt') if avatar else 'Not found'}")
            
            # 2. Dump relevant HTML for analysis
            # Usually user info is in a header container
            header = page.query_selector("div[data-e2e='user-info']")
            if header:
                print("  Found user-info container.")
                # print(header.inner_html()) # Too verbose, maybe just text
                print(f"  User Info Text: {header.inner_text().replace('\n', ' | ')}")
            else:
                print("  User-info container NOT found. Dumping first 2000 chars of body...")
                # print(page.content()[:2000])

        context.close()

if __name__ == "__main__":
    debug_nickname()
