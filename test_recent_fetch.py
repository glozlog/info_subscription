
import os
import sys
import yaml
import datetime
from src.fetchers.douyin_fetcher import DouyinFetcher

def test_recent_fetch():
    print("--- Testing Recent Fetch (3 Days) ---")
    
    # 1. Load config to get sessionid (already loaded by Fetcher)
    fetcher = DouyinFetcher()
    
    # 2. Define targets
    targets = [
        # Product Jun: "3月1日" -> Should be parsed as 2026-03-01
        {
            "url": "https://www.douyin.com/user/MS4wLjABAAAAVmG_pTXp3pvTEwF7Cm3te2-s_RDjXsCMf3n4sgs-63u-0xRsmvBdm6gj3rjNKaR-?previous_page=app_code_link",
            "expect_title_part": "3月1日",
            "expect_date": "2026-03-01"
        },
        # MeiTou: "史上最大IPO" -> Should be parsed as "2小时前" -> Today (2026-03-03)
        {
            "url": "https://www.douyin.com/user/MS4wLjABAAAAyvVEqOEIqpt9h1IU0fpvJzvVEPsABP6fN0jqNQy2ePI",
            "expect_title_part": "史上最大IPO",
            "expect_date": datetime.datetime.now().strftime("%Y-%m-%d")
        },
        # XingBuXing: "买完就赚" -> Should be parsed as "3天前" -> 2026-02-28
        {
            "url": "https://www.douyin.com/user/MS4wLjABAAAA9lwxwRIw3UpuTXj0_C3upyYDg74QysOH8w3yVdNCWv83EnQHyqEGMgtMdqSY2o4Q",
            "expect_title_part": "买完就赚",
            "expect_date": (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        }
    ]
    
    # 3. Run fetch for each
    for target in targets:
        print(f"\nChecking: {target['url']}")
        try:
            results = fetcher.fetch(target['url'])
            print(f"Fetched {len(results)} items.")
            
            found = False
            for item in results:
                title = item.get('title', '')
                date = item.get('publish_date', '')
                
                if target['expect_title_part'] in title:
                    print(f"  [FOUND] Title: {title[:30]}... | Date: {date}")
                    found = True
                    
                    # Check Date
                    if date == target['expect_date']:
                         print(f"  [PASS] Date matches expected: {date}")
                    else:
                         print(f"  [WARN] Date mismatch! Expected {target['expect_date']}, got {date}")
                    
                    # Check if it would be filtered by "recent 3 days"
                    item_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                    today = datetime.date.today()
                    delta = (today - item_date).days
                    if delta <= 3:
                        print(f"  [PASS] Item is within 3 days (delta={delta})")
                    else:
                        print(f"  [FAIL] Item is OLDER than 3 days (delta={delta})")
                    break
            
            if not found:
                print(f"  [FAIL] Target '{target['expect_title_part']}' NOT found in fetch results.")
                
        except Exception as e:
            print(f"Error fetching: {e}")

if __name__ == "__main__":
    test_recent_fetch()
