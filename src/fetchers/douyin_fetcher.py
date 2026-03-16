
from playwright.sync_api import sync_playwright
from .base import BaseFetcher
from typing import List, Dict, Any
import time
import re
import datetime
import yaml
import os

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

    def fetch(self, url: str, limit: int = 20, days_limit: int = 0, source_name: str = None) -> List[Dict[str, Any]]:
        """
        Fetch latest videos from a Douyin user profile.
        
        Args:
            url: Douyin user profile URL
            limit: Maximum number of items to fetch (default 20)
            days_limit: If > 0, only fetch items within last N days (default 0)
            source_name: Optional source name for logging
        """
        print(f"Fetching {url} via Playwright (Source: {source_name}, limit={limit}, days_limit={days_limit})...")
        return self._fetch_playwright(url, source_name, limit, days_limit)

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

    def _extract_user_nickname(self, page) -> str:
        """
        Extract user nickname from the profile page.
        """
        try:
            # 1. Try h1 (Primary)
            h1 = page.query_selector("h1")
            if h1:
                text = h1.inner_text().strip()
                if text: return text
            
            # 2. Try user-info container (Backup)
            # Text often looks like: "Nickname | Follow | ..."
            info = page.query_selector("div[data-e2e='user-info']")
            if info:
                raw = info.inner_text()
                # Usually the first line or part is the nickname
                lines = [l.strip() for l in raw.split('\n') if l.strip()]
                if lines:
                    # Check if first line is valid
                    candidate = lines[0]
                    if len(candidate) < 30 and "关注" not in candidate:
                        return candidate

            # 3. Try .nickname class (sometimes used)
            nick = page.query_selector(".nickname")
            if nick:
                text = nick.inner_text().strip()
                if text: return text
                
            # 4. Try title attribute of avatar
            avatar = page.query_selector(".avatar-component img")
            if avatar:
                alt = avatar.get_attribute("alt")
                if alt: return alt
                
        except:
            pass
        return ""

    def _fetch_playwright(self, url, source_name=None, limit: int = 20, days_limit: int = 0):
        """
        Fetch data using Playwright with PERSISTENT CONTEXT.
        This allows reusing cookies/session to mimic a real user and potentially bypass login walls.
        
        Args:
            url: Douyin user profile URL
            source_name: Optional source name for logging
            limit: Maximum number of items to fetch
            days_limit: If > 0, only fetch items within last N days
        """
        results = []
        # Use absolute path relative to project root for browser data
        user_data_dir = os.path.abspath("browser_data/douyin")
        
        # Ensure directory exists
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
            
        try:
            with sync_playwright() as p:
                # Use launch_persistent_context instead of launch + new_context
                # We use headless=True by default, but user can change it for debugging/login
                # Note: 'chrome' channel is often better for anti-detect, but requires Chrome installed.
                # If not, use standard chromium.
                
                print(f"Launching persistent browser context from: {user_data_dir}")
                
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=True, # Set to False if you want to watch or login manually
                    channel="chrome", # Try to use real Chrome if available
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    # Args to mimic real browser and avoid detection
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-infobars"
                    ]
                )
                
                page = context.pages[0] if context.pages else context.new_page()
                
                print(f"Navigating to {url}...")
                
                # Robust navigation with retry
                for attempt in range(2):
                    try:
                        if attempt > 0: page.reload()
                        else: page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        
                        try:
                            # Wait a bit longer for "pinned" content which loads lazily
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except:
                            pass 
                            
                        # Check for login modal or slider?
                        # If we see a login modal, we might want to close it.
                        close_btn = page.query_selector('.dy-account-close')
                        if close_btn:
                            print("Closing login modal...")
                            close_btn.click()
                            
                        if page.query_selector('div[data-e2e="user-post-list"]'):
                            break
                    except Exception as e:
                        print(f"Navigation attempt {attempt+1} failed: {e}")

                # Extract Nickname if source_name is generic
                extracted_nickname = ""
                if not source_name or "抖音用户" in source_name or "Douyin User" in source_name:
                    extracted_nickname = self._extract_user_nickname(page)
                    if extracted_nickname:
                        print(f"Extracted nickname: {extracted_nickname}")

                # Scroll to load content with date-aware termination
                # If days_limit is set, stop scrolling when we see old content
                cutoff_date = None
                if days_limit > 0:
                    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_limit)
                    print(f"Date filter: only fetching items after {cutoff_date.date()}")
                
                max_scroll_attempts = 10 if days_limit > 0 else 5
                consecutive_old_items = 0
                
                for scroll_round in range(max_scroll_attempts):
                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1.5)
                    
                    # Check if we should stop scrolling (date-based)
                    if days_limit > 0 and scroll_round >= 2:  # Check after initial scrolls
                        # Quick check: get last visible item's date
                        temp_list = page.query_selector('div[data-e2e="user-post-list"]')
                        if temp_list:
                            temp_items = temp_list.query_selector_all('li') or temp_list.query_selector_all(':scope > div')
                            if len(temp_items) > 0:
                                # Check last few items
                                recent_items_checked = 0
                                old_items_in_check = 0
                                
                                for temp_item in temp_items[-3:]:  # Check last 3 items
                                    temp_link = temp_item.query_selector('a[href*="/video/"], a[href*="/note/"]')
                                    if temp_link:
                                        temp_href = temp_link.get_attribute("href") or ""
                                        temp_vid_match = re.search(r'(?:video|note|article)/(\d+)|modal_id=(\d+)', temp_href)
                                        temp_vid = temp_vid_match.group(1) or temp_vid_match.group(2) if temp_vid_match else ""
                                        if temp_vid:
                                            temp_date_str = self._extract_date_from_id(temp_vid)
                                            if temp_date_str:
                                                try:
                                                    temp_date = datetime.datetime.strptime(temp_date_str, "%Y-%m-%d")
                                                    if temp_date < cutoff_date:
                                                        old_items_in_check += 1
                                                except:
                                                    pass
                                
                                # If all checked items are old, we can stop scrolling
                                if old_items_in_check >= 2:
                                    print(f"  Stopping scroll at round {scroll_round + 1}: found old content")
                                    break
                
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
                        if len(fetched_items) >= limit: break
                        
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
                        
                        # Check for "Pinned" (置顶) status
                        is_pinned = False
                        if "置顶" in item.inner_text():
                            is_pinned = True
                            # Pinned videos might be old, so ID extraction is correct,
                            # BUT user wants "instant info".
                            # If it's pinned, we still extract the real date.
                        
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

                        # Date-based filtering during extraction (for early termination)
                        if days_limit > 0 and publish_date:
                            try:
                                # Try parsing with time first, then fallback to date-only
                                try:
                                    item_date = datetime.datetime.strptime(publish_date, "%Y-%m-%d %H:%M:%S")
                                except ValueError:
                                    item_date = datetime.datetime.strptime(publish_date, "%Y-%m-%d")
                                if item_date < cutoff_date:
                                    # This item is too old, skip it
                                    # But continue to check next items (don't break, as items might not be sorted)
                                    continue
                            except:
                                pass

                        # Author Name Logic
                        final_author = source_name
                        if not final_author or "抖音用户" in final_author or "Douyin User" in final_author:
                             if extracted_nickname:
                                 final_author = extracted_nickname
                             else:
                                 final_author = "Douyin User"
                        
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
                            "id": vid,
                            "is_pinned": is_pinned
                        })
                
                results = fetched_items
                context.close() # Saves cookies to user_data_dir
                
        except Exception as e:
            print(f"Error fetching Douyin user {url}: {e}")
            if "Target closed" in str(e) or "browser" in str(e):
                 print("Hint: If browser closed unexpectedly, check if Chrome is installed or remove 'channel' arg.")
        
        # 应用日期过滤
        if days_limit > 0:
            results = self._filter_by_date(results, days_limit)
            
        return results
