from src.fetchers.douyin_fetcher import DouyinFetcher
import json

url = "https://www.douyin.com/user/MS4wLjABAAAAVmG_pTXp3pvTEwF7Cm3te2-s_RDjXsCMf3n4sgs-63u-0xRsmvBdm6gj3rjNKaR-?previous_page=app_code_link"

def run():
    fetcher = DouyinFetcher()
    
    print("--- Testing _fetch_playwright direct call ---")
    try:
        results = fetcher._fetch_playwright(url)
        print(f"Found {len(results)} videos via Playwright:")
        for r in results:
            print(f"  [{r['publish_date']}] {r['title']} (URL: {r['url']})")
            
        # Check for March 1st
        found = any("03-01" in r['publish_date'] for r in results)
        if found:
            print("SUCCESS: Found 2026-03-01 video!")
        else:
            print("FAILURE: Did NOT find 2026-03-01 video.")
            
    except Exception as e:
        print(f"Playwright error: {e}")

if __name__ == "__main__":
    run()
