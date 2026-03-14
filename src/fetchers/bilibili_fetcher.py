import requests
import json
from datetime import datetime
from typing import List, Dict, Any
from .base import BaseFetcher
import re
import feedparser

class BilibiliFetcher(BaseFetcher):
    """
    Fetcher for Bilibili user updates.
    
    Strategies:
    1. RSSHub (Preferred): Uses local RSSHub instance if available.
    2. Direct API (Fallback): Uses Bilibili public API (often rate-limited/WBI protected).
    """
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/"
        }
        self.rsshub_base = "http://localhost:1200"

    def validate_url(self, url: str) -> bool:
        return "space.bilibili.com" in url or "bilibili.com/video" in url

    def fetch(self, url: str) -> List[Dict[str, Any]]:
        # Extract UID
        uid = self._extract_uid(url)
        if not uid:
            print(f"Could not extract UID from {url}")
            return []

        # Strategy 1: Try RSSHub
        rss_url = f"{self.rsshub_base}/bilibili/user/video/{uid}"
        try:
            print(f"Attempting fetch via RSSHub: {rss_url}")
            feed = feedparser.parse(rss_url)
            if not feed.bozo and len(feed.entries) > 0:
                results = []
                for entry in feed.entries[:5]:
                    results.append({
                        "title": entry.title,
                        "url": entry.link,
                        "content": entry.description,
                        "publish_date": entry.published,
                        "author": feed.feed.title,
                        "platform": "bilibili"
                    })
                return results
        except Exception as e:
            print(f"RSSHub fetch failed: {e}")

        # Strategy 2: Direct API (Fallback)
        print("RSSHub failed or empty, falling back to Direct API...")
        return self._fetch_direct(uid)

    def _extract_uid(self, url: str) -> str:
        match = re.search(r'space\.bilibili\.com/(\d+)', url)
        return match.group(1) if match else None

    def _fetch_direct(self, uid: str) -> List[Dict[str, Any]]:
        # Existing API logic
        api_url = "https://api.bilibili.com/x/space/wbi/arc/search"
        params = {
            "mid": uid,
            "ps": 5,
            "tid": 0,
            "pn": 1,
            "keyword": "",
            "order": "pubdate"
        }
        
        try:
            response = requests.get(api_url, params=params, headers=self.headers, timeout=10)
            data = response.json()
            
            if data['code'] != 0:
                print(f"Bilibili API error: {data.get('message')}")
                return []
                
            vlist = data['data']['list']['vlist']
            results = []
            
            for v in vlist:
                results.append({
                    "title": v['title'],
                    "url": f"https://www.bilibili.com/video/{v['bvid']}",
                    "content": v['description'],
                    "publish_date": datetime.fromtimestamp(v['created']).strftime('%Y-%m-%d %H:%M:%S'),
                    "author": v['author'],
                    "platform": "bilibili"
                })
            return results
        except Exception as e:
            print(f"Direct API fetch error: {e}")
            return []
