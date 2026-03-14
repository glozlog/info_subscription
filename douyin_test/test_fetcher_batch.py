
import os
import re
import datetime
import time
from playwright.sync_api import sync_playwright

# Configuration
TEST_URLS = [
    {
        "url": "https://www.douyin.com/user/MS4wLjABAAAAB3Qx5iT-XPUp54-wBHTac06qDEKdyWUmKhcIwTIyS5Q25jt7CBoRK-OS-N1ha4Yk",
        "name": "User 1 (学院派Academia?)"
    },
    {
        "url": "https://www.douyin.com/user/MS4wLjABAAAA25xxS-4HJ5PYicMjFpvzlYR_oe37SK-ryMNQZs-ilpdFNy7iaGBWl3cyQIsPirtB",
        "name": "User 2"
    },
    {
        "url": "https://www.douyin.com/user/MS4wLjABAAAAoXm3UTY6L_aOBfJxd0Y8B9ojQS4rUUWwDK-iEre3opQ",
        "name": "User 3"
    }
]

def extract_date_from_id(vid: str) -> str:
    """Extract publish date from Douyin Aweme ID (Snowflake ID)."""
    if not vid or not vid.isdigit():
        return ""
    try:
        vid_int = int(vid)
        timestamp = vid_int >> 32
        dt_object = datetime.datetime.fromtimestamp(timestamp)
        now = datetime.datetime.now()
        if 2016 < dt_object.year <= now.year + 1:
            return dt_object.strftime("%Y-%m-%d")
    except:
        pass
    return ""

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'#\S+', '', text)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        l = line.strip()
        if not l: continue
        if re.match(r'^[\d\.w万k\+]+$', l): continue
        if l in ["置顶", "广告", "刚刚", "昨天"]: continue
        if re.match(r'^\d+-\d+$', l): continue
        cleaned.append(l)
    return "\n".join(cleaned)

def test_fetch_batch():
    user_data_dir = os.path.abspath("douyin_test/browser_data")
    if not os.path.exists(user_data_dir):
        print(f"Warning: Browser data dir {user_data_dir} does not exist. You might need to run manual_login.py first.")
        os.makedirs(user_data_dir)
    
    print(f"Starting BATCH fetch test... (Using persistent context: {user_data_dir})")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            channel="chrome",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        for user in TEST_URLS:
            url = user["url"]
            name = user["name"]
            
            print(f"\nProcessing {name}...")
            print(f"URL: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass

                # Scroll
                for i in range(3):
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1)
                    
                # Find items
                main_list = page.query_selector('div[data-e2e="user-post-list"]')
                if not main_list:
                    print("  Error: Could not find user-post-list container.")
                    continue
                    
                list_items = main_list.query_selector_all('li')
                if not list_items:
                    list_items = main_list.query_selector_all(':scope > div')
                    
                print(f"  Found {len(list_items)} items. Top 5:")
                
                count = 0
                for item in list_items:
                    if count >= 5: break
                    
                    # Extract basic info
                    link = item.query_selector('a[href*="/video/"], a[href*="/note/"]')
                    if not link: continue
                    
                    href = link.get_attribute("href")
                    # Get ID
                    vid_match = re.search(r'(?:video|note|article)/(\d+)|modal_id=(\d+)', href)
                    vid = vid_match.group(1) or vid_match.group(2) if vid_match else ""
                    
                    # Get Text/Title
                    raw_text = link.inner_text()
                    cleaned_text = clean_text(raw_text)
                    title = cleaned_text.split('\n')[0] if cleaned_text else "No Title"
                    
                    # Get Date
                    date = "Unknown"
                    if vid:
                        date = extract_date_from_id(vid)
                        
                    is_pinned = "置顶" in raw_text
                    
                    print(f"    [{count+1}] {date} | {'[PINNED]' if is_pinned else ''} {title[:30]}...")
                    count += 1
                    
            except Exception as e:
                print(f"  Error fetching {name}: {e}")
                
            time.sleep(2) # Cooldown between users

        context.close()
        print("\nBatch test complete.")

if __name__ == "__main__":
    test_fetch_batch()
