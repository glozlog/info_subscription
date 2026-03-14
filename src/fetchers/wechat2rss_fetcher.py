from typing import List, Dict, Any
from .base import BaseFetcher
import feedparser
import os
import time


class Wechat2RssFetcher(BaseFetcher):
    def validate_url(self, url: str) -> bool:
        if not isinstance(url, str):
            return False
        s = url.strip()
        if not s:
            return False
        if s.startswith("wechat2rss:"):
            s = s.split(":", 1)[1].strip()
        if s.isdigit():
            return True
        return ("/feed/" in s) and (s.endswith(".xml") or s.endswith(".rss") or s.endswith(".atom") or s.endswith(".json"))

    def _resolve_feed_url(self, spec: str) -> str:
        s = (spec or "").strip()
        if s.startswith("wechat2rss:"):
            s = s.split(":", 1)[1].strip()
        if s.isdigit():
            base_url = os.environ.get("WECHAT2RSS_BASE_URL", "http://localhost:8080").rstrip("/")
            return f"{base_url}/feed/{s}.xml"
        return s

    def fetch(self, url: str) -> List[Dict[str, Any]]:
        if not self.validate_url(url):
            return []

        feed_url = self._resolve_feed_url(url)
        feed = feedparser.parse(feed_url)
        results: List[Dict[str, Any]] = []

        if getattr(feed, "bozo", False):
            print(f"Warning: Potential error parsing Wechat2RSS feed {feed_url}: {getattr(feed, 'bozo_exception', None)}")

        limit = 20
        for entry in getattr(feed, "entries", [])[:limit]:
            title = entry.get("title", "No Title")
            link = entry.get("link", "")

            content = ""
            if "content" in entry and entry.content:
                content = entry.content[0].value
            elif "summary_detail" in entry and entry.summary_detail:
                content = entry.summary_detail.value
            elif "description" in entry:
                content = entry.description
            else:
                content = title

            subtitle = ""
            if "summary" in entry:
                subtitle = entry.summary
            elif "description" in entry:
                subtitle = entry.description

            published = entry.get("published", "")
            if not published:
                published = entry.get("updated", time.strftime("%Y-%m-%d"))

            author = entry.get("author", "") or getattr(getattr(feed, "feed", {}), "title", "") or "WeChat"
            if author:
                a = str(author).strip()
                t = str(title).strip()
                if t and a and not (t.startswith(f"{a}：") or t.startswith(f"{a}:")):
                    title = f"{a}：{t}"

            results.append(
                {
                    "title": title,
                    "url": link,
                    "content": content,
                    "subtitle": subtitle,
                    "publish_date": published,
                    "author": author,
                    "platform": "wechat",
                    "video_url": "",
                }
            )

        return results
