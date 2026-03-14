
import os
import re
import datetime
import time
from playwright.sync_api import sync_playwright

# Configuration
TARGET_URL = "https://www.douyin.com/user/MS4wLjABAAAAVmG_pTXp3pvTEwF7Cm3te2-s_RDjXsCMf3n4sgs-63u-0xRsmvBdm6gj3rjNKaR-"
TARGET_VIDEO_KEYWORD = "荣耀发布全球首个机器人手机"
TARGET_DATE = "2026-03-06" # Based on user's "3月6号" and env year 2026

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
    # Remove hashtags
    text = re.sub(r'#\S+', '', text)
    # Remove stats and common artifacts
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

def test_fetch():
    user_data_dir = os.path.abspath("douyin_test/browser_data")
    if not os.path.exists(user_data_dir):
        print(f"Warning: Browser data dir {user_data_dir} does not exist. You might need to run manual_login.py first.")
        os.makedirs(user_data_dir)
    
    print(f"Starting fetch test... (Using persistent context: {user_data_dir})")
    
    found_target = False
    
    with sync_playwright() as p:
        # Launch with persistent context
        # Try headless=True first, if fails maybe switch to False for debugging
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            channel="chrome",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print(f"Navigating to {TARGET_URL}...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass

        # Scroll
        print("Scrolling to load content...")
        for i in range(5):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)
            
        # Find items
        main_list = page.query_selector('div[data-e2e="user-post-list"]')
        if not main_list:
            print("Error: Could not find user-post-list container.")
            context.close()
            return
            
        list_items = main_list.query_selector_all('li')
        if not list_items:
            list_items = main_list.query_selector_all(':scope > div')
            
        print(f"Found {len(list_items)} items. Checking for target...")
        
        for idx, item in enumerate(list_items):
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
            
            # Check match
            is_match = False
            if TARGET_VIDEO_KEYWORD in title or TARGET_VIDEO_KEYWORD in raw_text:
                is_match = True
                found_target = True
                print("\n" + "="*50)
                print(f"FOUND TARGET VIDEO!")
                print(f"Title: {title}")
                print(f"Date extracted from ID: {date}")
                print(f"Is Pinned: {is_pinned}")
                print(f"Raw Text Preview: {raw_text[:50]}...")
                print("="*50 + "\n")
            
            # Print recent items for debugging
            if idx < 5 or is_match:
                 print(f"[{idx+1}] {date} | {'[PINNED]' if is_pinned else ''} {title[:40]}...")

        context.close()
        
    if found_target:
        print(f"\nSUCCESS: Target video found! Date: {date} (Expected: {TARGET_DATE})")
        if date == TARGET_DATE:
            print("Date matches perfectly.")
        else:
            print("Date mismatch! Please verify.")
    else:
        print(f"\nFAILURE: Target video '{TARGET_VIDEO_KEYWORD}' NOT found in first ~20 items.")
        print("Possible reasons: Login required (pinned videos hidden), or video is older/newer than expected.")

if __name__ == "__main__":
    test_fetch()
