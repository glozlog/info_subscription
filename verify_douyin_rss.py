import requests
import feedparser
import time

import sys

def verify_douyin_rss(uid=None):
    if uid is None:
        if len(sys.argv) > 1:
            uid = sys.argv[1]
        else:
            uid = "MS4wLjABAAAAyvVEqOEIqpt9h1IU0fpvJzvVEPsABP6fN0jqNQy2ePI"

    base_url = "http://localhost:1200"
    rss_url = f"{base_url}/douyin/user/{uid}"
    
    print(f"Testing RSSHub connectivity for Douyin user: {uid}")
    print(f"URL: {rss_url}")
    
    try:
        # 1. Check raw response
        response = requests.get(rss_url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("Connection successful!")
            # 2. Parse feed
            feed = feedparser.parse(response.content)
            print(f"Feed Title: {feed.feed.title}")
            print(f"Entries found: {len(feed.entries)}")
            
            if len(feed.entries) > 0:
                print("Latest Entry:")
                print(f"- Title: {feed.entries[0].title}")
                print(f"- Date: {feed.entries[0].published}")
                print(f"- Link: {feed.entries[0].link}")
            else:
                print("Warning: Feed is empty.")
        else:
            print(f"Error: {response.text[:200]}")
            
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Please ensure RSSHub is running on localhost:1200")

if __name__ == "__main__":
    verify_douyin_rss()
