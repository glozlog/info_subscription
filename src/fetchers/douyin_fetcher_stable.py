
from playwright.sync_api import sync_playwright
from .base import BaseFetcher
from typing import List, Dict, Any
import time
import re
import datetime
import yaml

class DouyinFetcher(BaseFetcher):
    """
    Fetcher for Douyin user updates.
    Strategies: Playwright only (RSSHub deprecated for this module).
    """
    
    def __init__(self):
        # SessionID logic removed as requested/deprecated
        pass

    def validate_url(self, url: str) -> bool:
        return "douyin.com" in url

    def fetch(self, url: str, source_name: str = None) -> List[Dict[str, Any]]:
        """
        Fetch latest videos from a Douyin user profile.
        """
        print(f"Fetching {url} via Playwright (Source: {source_name})...")
        return self._fetch_playwright(url, source_name)

    def _extract_date_from_id(self, vid: str) -> str:
        """
        Extract publish date from Douyin Aweme ID (Snowflake ID).
        High 32 bits of the ID represent the timestamp (seconds since epoch).
        Returns datetime in format: YYYY-MM-DD HH:MM:SS
        """
        if not vid or not vid.isdigit():
            return ""
            
        try:
            vid_int = int(vid)
            timestamp = vid_int >> 32
            
            # Sanity check: > 2016 (Douyin launch) and < Future + buffer
            dt_object = datetime.datetime.fromtimestamp(timestamp)
            now = datetime.datetime.now()
            
            if 2016 < dt_object.year <= now.year + 1:
                return dt_object.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        return ""

    def _clean_text(self, text: str) -> str:
        """Remove stats, hashtags, and common artifacts from Douyin text."""
        if not text:
            return ""
            
        # Remove hashtags (e.g. #AI #Douyin)
        text = re.sub(r'#\S+', '', text)
            
        # Remove stats patterns (e.g. 1.2w, 100, Share, Like)
        # Often these are at the start or end, or separate lines.
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Skip short numeric/stat lines
            if re.match(r'^[\d\.w万k\+]+$', line): continue # "1.2w"
            if line in ["置顶", "广告", "刚刚", "昨天"]: continue
            if re.match(r'^\d+-\d+$', line): continue # "03-01"
            
            cleaned_lines.append(line)
            
        return "\n".join(cleaned_lines)

    def _fetch_playwright(self, url, source_name=None):
        """
        Fetch data using Playwright (headless browser).
        """
        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                
                # Add dummy cookie to help with structure (sometimes needed)
                context.add_cookies([
                     {'name': 'ttwid', 'value': '1%7Cdummy', 'domain': '.douyin.com', 'path': '/'},
                ])
                
                page = context.new_page()
                print(f"Navigating to {url}...")
                
                # Robust navigation with retry
                for attempt in range(2):
                    try:
                        if attempt > 0: page.reload()
                        else: page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except:
                            pass # Network idle might timeout, continue
                            
                        if page.query_selector('div[data-e2e="user-post-list"]'):
                            break
                    except Exception as e:
                        print(f"Navigation attempt {attempt+1} failed: {e}")

                # Scroll to load content
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 500)")
                    time.sleep(1)
                
                # Extract items
                main_list = page.query_selector('div[data-e2e="user-post-list"]')
                fetched_items = []
                
                if main_list:
                    # Try 'li' first, then direct 'div' children
                    list_items = main_list.query_selector_all('li')
                    if not list_items:
                        list_items = main_list.query_selector_all(':scope > div')
                    
                    print(f"Found {len(list_items)} potential items.")
                    
                    for item in list_items:
                        if len(fetched_items) >= 20: break
                        
                        # Find link
                        link = item.query_selector('a[href*="/video/"], a[href*="/note/"], a[href*="/article/"], a[href*="modal_id="]')
                        
                        # Fallback: Check if item itself is the link
                        if not link:
                            tag_name = item.evaluate("el => el.tagName.toLowerCase()")
                            if tag_name == 'a':
                                href = item.get_attribute('href')
                                if href and ('/video/' in href or '/note/' in href):
                                    link = item
                        
                        if not link: continue
                        
                        href = link.get_attribute("href")
                        if not href: continue
                        
                        # Normalize URL
                        if href.startswith('//'): full_url = f"https:{href}"
                        elif href.startswith('/'): full_url = f"https://www.douyin.com{href}"
                        else: full_url = href
                        
                        # ID Extraction
                        vid_match = re.search(r'(?:video|note|article)/(\d+)|modal_id=(\d+)', full_url)
                        vid = vid_match.group(1) or vid_match.group(2) if vid_match else ""
                        
                        # Title Extraction
                        img = link.query_selector('img')
                        title = img.get_attribute('alt') if img else ""
                        
                        # Text Content fallback for title
                        if not title:
                            # Clean text extraction
                            raw_text = link.inner_text()
                            title = self._clean_text(raw_text)
                            # If still multiple lines, pick longest
                            if '\n' in title:
                                lines = [l.strip() for l in title.split('\n') if l.strip()]
                                if lines:
                                    title = max(lines, key=len)
                        
                        is_article = "/article/" in full_url
                        if not title:
                            title = "Douyin Article" if is_article else "Douyin Video"
                            
                        # Date Extraction Strategy
                        publish_date = ""
                        
                        # Strategy 1: ID-based (Most Reliable for non-pinned recent items)
                        if vid:
                            publish_date = self._extract_date_from_id(vid)
                        
                        # Strategy 2: Text-based (Fallback or if ID fails)
                        if not publish_date:
                            card_text = item.inner_text()
                            now = datetime.datetime.now()
                            # Specific Date format: (3月1日)
                            date_match = re.search(r'[(\uff08](\d{1,2})[月\.\-](\d{1,2})[日\) \uff09]', title)
                            if date_match:
                                month, day = int(date_match.group(1)), int(date_match.group(2))
                                year = now.year
                                if datetime.datetime(year, month, day) > now + datetime.timedelta(days=1):
                                    year -= 1
                                # Use noon (12:00:00) as default time for date-only sources
                                publish_date = f"{year}-{month:02d}-{day:02d} 12:00:00"
                            
                            # Relative Time
                            elif "昨天" in card_text:
                                yesterday = now - datetime.timedelta(days=1)
                                publish_date = yesterday.strftime("%Y-%m-%d 12:00:00")
                            elif "刚刚" in card_text or "小时前" in card_text or "分钟前" in card_text:
                                publish_date = now.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                rel_match = re.search(r'(\d+)天前', card_text)
                                if rel_match:
                                    days_ago = int(rel_match.group(1))
                                    past_date = now - datetime.timedelta(days=days_ago)
                                    publish_date = past_date.strftime("%Y-%m-%d 12:00:00")

                        # Final Default
                        if not publish_date:
                            publish_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        # Author Name
                        # If source_name is provided (from config), USE IT.
                        # Otherwise try to extract.
                        final_author = source_name if source_name else "Douyin User"
                        
                        # Clean title for content
                        clean_content = self._clean_text(title)
                        
                        # Process Title: Take only the first meaningful line
                        final_title = clean_content.split('\n')[0] if clean_content else "Douyin Video"
                        # Fallback if first line is too short but there are more lines
                        if len(final_title) < 5 and '\n' in clean_content:
                             lines = [l.strip() for l in clean_content.split('\n') if len(l.strip()) > 5]
                             if lines:
                                 final_title = lines[0]
                        
                        fetched_items.append({
                            "title": final_title,
                            "url": full_url,
                            "content": clean_content,
                            "publish_date": publish_date, 
                            "author": final_author, 
                            "platform": "douyin",
                            "video_url": "",
                            "is_article": is_article,
                            "id": vid
                        })
                
                results = fetched_items
                browser.close()
                
        except Exception as e:
            print(f"Error fetching Douyin user {url}: {e}")
            
        return results
