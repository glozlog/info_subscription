import feedparser
from .base import BaseFetcher
from typing import List, Dict, Any
import time
import re

class RssFetcher(BaseFetcher):
    """
    Fetcher for generic RSS feeds.
    """
    
    def validate_url(self, url: str) -> bool:
        """
        Check if the URL looks like an RSS feed (xml, rss, atom) or if user explicitly specifies it.
        """
        return url.endswith('.xml') or url.endswith('.rss') or url.endswith('.atom') or 'feed' in url

    def _extract_video_url(self, content: str) -> str:
        """Extract video URL from content HTML (specific for Douyin/RSSHub)."""
        if not content:
            return ""
        # Try to find the "视频直链" href pattern from RSSHub
        match = re.search(r'href="(https://www\.douyin\.com/aweme/v1/play/\?[^"]+)"[^>]*>视频直链', content)
        if match:
            return match.group(1).replace("&amp;", "&")
        return ""

    def fetch(self, url: str, source_name: str = None) -> List[Dict[str, Any]]:
        """
        Fetch content from an RSS feed.
        """
        try:
            feed = feedparser.parse(url)
            results = []
            
            # Check for parsing errors
            if feed.bozo:
                print(f"Warning: Potential error parsing RSS feed {url}: {feed.bozo_exception}")
            
            # Logic for history backfill
            # If we want to fetch last 3 months, we should check dates.
            # Usually RSS feeds are paginated or limited by the server.
            # However, for now let's ensure we consume ALL entries present in the feed.
            # And increase local limit to 20 just in case the feed is rich.
            limit = 20 

            for entry in feed.entries[:limit]: 
                title = entry.get('title', 'No Title')
                link = entry.get('link', '')
                
                # Extract content (prefer full content)
                content = ""
                if 'content' in entry:
                    content = entry.content[0].value
                elif 'summary_detail' in entry:
                    content = entry.summary_detail.value
                elif 'description' in entry:
                    content = entry.description
                else:
                    content = title
                    
                # Extract subtitle (prefer summary/description)
                subtitle = ""
                if 'summary' in entry:
                    subtitle = entry.summary
                elif 'description' in entry:
                    subtitle = entry.description
                
                # If subtitle is identical to content (common in some feeds), clear it to avoid duplication in UI
                # But sometimes content IS just the description.
                # Let's keep it, but maybe truncate or clean it up in UI.
                
                # Publish date
                published = entry.get('published', '')
                if not published:
                    published = entry.get('updated', time.strftime('%Y-%m-%d'))
                
                # Check if it's within last 3 months?
                # For simplicity, we just return all recent items and let Archiver decide what to keep.
                # But Archiver currently overwrites daily report.
                # Ideally, we should check against a persistent database.
                # Since we are using file-based storage, fetching 50 items is fine.
                    
                author = entry.get('author', feed.feed.get('title', 'RSS Source'))
                
                platform = "rss"
                if "douyin" in url or "douyin" in link:
                    platform = "douyin"
                
                # Extract video URL if available (for Douyin)
                video_url = self._extract_video_url(content)
                
                results.append({
                    "title": title,
                    "url": link,
                    "content": content, # This might contain HTML, summarizer needs to handle it
                    "subtitle": subtitle, # Original feed summary/description
                    "publish_date": published,
                    "author": author,
                    "platform": platform,
                    "video_url": video_url
                })
                
            return results
            
        except Exception as e:
            print(f"Error fetching RSS {url}: {e}")
            return []
