from playwright.sync_api import sync_playwright
import time
import re
import hashlib

# List of URLs to check
check_urls = [
    # 0. 产品君 (3月1日缺失)
    "https://www.douyin.com/user/MS4wLjABAAAAVmG_pTXp3pvTEwF7Cm3te2-s_RDjXsCMf3n4sgs-63u-0xRsmvBdm6gj3rjNKaR-?previous_page=app_code_link",
    # 1. 美投讲美股 (2小时前文章)
    "https://www.douyin.com/user/MS4wLjABAAAAyvVEqOEIqpt9h1IU0fpvJzvVEPsABP6fN0jqNQy2ePI",
    # 2. 量化投资邢不行啊 (3天前文章)
    "https://www.douyin.com/user/MS4wLjABAAAA9lwxwRIw3UpuTXj0_C3upyYDg74QysOH8w3yVdNCWv83EnQHyqEGMgtMdqSY2o4Q"
]

def run_checks():
    with sync_playwright() as p:
        # Switch to chromium for better devtools protocol support (network interception)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        context.add_cookies([
             {'name': 'ttwid', 'value': '1%7Cdummy', 'domain': '.douyin.com', 'path': '/'},
             {'name': 'sessionid', 'value': '53bda0af3c47cfb31f2a0f5b8b3a8778', 'domain': '.douyin.com', 'path': '/'},
        ])
        
        page = context.new_page()

        for url in check_urls:
            print(f"\n==========================================")
            print(f"Checking URL: {url}")
            print(f"==========================================")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print(f"Page Title: {page.title()}")
                
                # Wait for list
                try:
                    page.wait_for_selector('div[data-e2e="user-post-list"]', timeout=15000)
                    print("List container found.")
                except:
                    print("List container NOT found (timeout).")
                
                # Scroll multiple times to ensure top content is loaded/rendered
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 500)")
                    time.sleep(1)
                
                # Target texts
                targets = ["3月1日", "买完就赚", "史上最大IPO"]
                
                content = page.content()
                
                for t in targets:
                    if t in content:
                        print(f"\n[FOUND TARGET] '{t}' in rendered body text!")
                        
                        try:
                            # Find the element handle
                            # Using simpler xpath to find text node
                            element = page.query_selector(f"//*[contains(text(), '{t}')]")
                            
                            if element:
                                print(f"  elementTag: {element.evaluate('el => el.tagName')}")
                                
                                # Check parents for Link or LI
                                parent = element
                                found_link = False
                                found_li = False
                                link_href = None
                                
                                for i in range(10):
                                    parent = parent.query_selector("..")
                                    if not parent: break
                                    
                                    tag = parent.evaluate("el => el.tagName.toLowerCase()")
                                    # print(f"    Ancestor {i}: <{tag}> class={parent.get_attribute('class')}")
                                    
                                    if tag == 'a':
                                        found_link = True
                                        link_href = parent.get_attribute('href')
                                        print(f"    [SUCCESS] Found <A>: {link_href}")
                                        break
                                        
                                    if tag == 'li':
                                        found_li = True
                                        # Check if LI has a link child
                                        link_child = parent.query_selector("a")
                                        if link_child:
                                             link_href = link_child.get_attribute('href')
                                             print(f"      <LI> contains <A>: {link_href}")
                                             found_link = True
                                        else:
                                             print("      <LI> does NOT contain <A> tag.")
                                        
                                        # Dump LI HTML
                                        print(f"      LI HTML (trunc): {parent.evaluate('el => el.outerHTML')[:300]}...")
                                        break
                                
                                if not found_link:
                                    print("    [FAILURE] No Link found for this target.")
                                else:
                                    print(f"    [VERIFIED] Link found: {link_href}")

                            else:
                                print("  Could not select element handle.")
                                
                        except Exception as e:
                            print(f"  Error inspecting: {e}")
                    else:
                        pass # Not in this page

            except Exception as e:
                print(f"Error checking {url}: {e}")
                
        browser.close()

if __name__ == "__main__":
    run_checks()
