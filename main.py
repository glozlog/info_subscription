import time
import os
import json
import subprocess
import email.utils
from datetime import datetime, timedelta, timezone
from src.utils.config_loader import ConfigLoader
from src.scheduler.job import JobScheduler
from typing import Dict, Any

def main():
    """
    Main entry point for the information subscription application.
    """
    
    # 1. Load configuration
    print("Loading configuration...")
    config_loader = ConfigLoader()
    try:
        config = config_loader.load()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # 2. Define the main job function (to be run daily)
    def _parse_to_datetime_utc(publish_date: str) -> datetime:
        if not publish_date:
            return datetime.min.replace(tzinfo=timezone.utc)
        s = str(publish_date).strip()
        try:
            # Try ISO format
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT"]:
                try:
                    # Handle GMT/UTC somewhat loosely
                    if s.endswith(" GMT"):
                            dt = datetime.strptime(s, "%a, %d %b %Y %H:%M:%S GMT")
                            return dt.replace(tzinfo=timezone.utc)
                    dt = datetime.strptime(s[:19], fmt)
                    # Assume local if no TZ, but for simplicity treat as UTC or Beijing
                    # Ideally we should handle TZ properly.
                    # For now let's just return offset-aware
                    return dt.replace(tzinfo=timezone.utc)
                except:
                    continue
        except:
            pass
        return datetime.min.replace(tzinfo=timezone.utc)

    def daily_job(days_limit: int = 0, target_name: str = None):
        """
        The daily job that:
        1. Iterates through subscriptions.
        2. Fetches new content.
        3. Summarizes content.
        4. Archives and generates reports.
        
        :param days_limit: If > 0, only fetch articles published within the last N days.
        :param target_name: If provided, only fetch the subscription with this name.
        """
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting update job (days_limit={days_limit}, target={target_name})...")
        
        subscriptions = config.get('subscriptions', [])
        if not subscriptions:
            print("No subscriptions found in config.")
            return

        # Filter subscriptions if target_name is provided
        if target_name:
            original_count = len(subscriptions)
            subscriptions = [s for s in subscriptions if s.get('name') == target_name]
            print(f"Filtered subscriptions: {len(subscriptions)}/{original_count} matched '{target_name}'")
            if not subscriptions:
                print(f"No subscription found with name: {target_name}")
                return

        # Factory pattern implementation (conceptual)
        from src.fetchers.factory import FetcherFactory
        from src.summarizer.llm_summarizer import OpenAISummarizer
        from src.archiver.file_archiver import FileArchiver
        
        # Initialize Summarizer and Archiver
        summarizer_config = config.get('summarizer', {})
        archiver_config = config.get('output', {})
        
        # Default to OpenAI, but should handle different providers
        api_key = summarizer_config.get('api_key', 'YOUR_API_KEY')
        base_url = summarizer_config.get('base_url')
        model = summarizer_config.get('model', 'gpt-3.5-turbo')
        provider = summarizer_config.get('provider', 'openai')
        summarizer = OpenAISummarizer(api_key=api_key, base_url=base_url, model=model, provider=provider)
        
        # Initialize Database
        from src.database import DatabaseManager
        db = DatabaseManager()
        
        archiver = FileArchiver(output_dir=archiver_config.get('directory', 'archives'))
        
        all_fetched_items = []
        all_summaries = {}

        for sub in subscriptions:
            platform = sub.get('platform')
            name = sub.get('name')
            url = sub.get('url')
            
            if not platform or not url:
                print(f"Skipping invalid subscription: {sub}")
                continue
                
            print(f"Fetching from {name} ({platform})...")
            
            try:
                fetcher = FetcherFactory.get_fetcher(platform)
                if not fetcher:
                    print(f"No fetcher found for {platform}")
                    continue
                
                # Pass source_name to fetcher if supported (e.g. DouyinFetcher)
                import inspect
                sig = inspect.signature(fetcher.fetch)
                if 'source_name' in sig.parameters:
                    items = fetcher.fetch(url, source_name=name)
                else:
                    # Fallback for fetchers that don't support source_name arg
                    items = fetcher.fetch(url)
                    
                print(f"  - Fetched {len(items)} items")
                
                # Filter items (e.g., only today's) - optional logic here
                # If days_limit is set, filter by publish_date
                if days_limit > 0:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
                    filtered_items = []
                    for item in items:
                        pd = item.get("publish_date")
                        dt = _parse_to_datetime_utc(pd)
                        # Only keep if dt is valid and newer than cutoff
                        # If date parsing fails (min date), we might skip or keep. Let's skip to be safe.
                        if dt > cutoff:
                            filtered_items.append(item)
                    
                    print(f"  - Filtered to {len(filtered_items)} items (within {days_limit} days)")
                    items = filtered_items
                
                # OPTIMIZATION: Check if we already have a summary for this URL in today's archive
                # to avoid re-generating it.
                # However, Archiver logic currently overwrites the daily file.
                # So we need to load existing data first if we want to be smart.
                # But user asked to "re-generate once" now.
                # So we will proceed with generation.
                
                for item in items:
                    item_url = item.get('url')
                    content = item.get('content')
                    video_url = item.get('video_url') # Extract video_url
                    
                    # Check if summary already exists in DB
                    existing_article = db.get_article(item_url)
                    summary = ""
                    if existing_article and existing_article.get('summary'):
                        # Skip processing if we already have it in DB
                        # This aligns with "Run Now" logic: only process NEW items
                        # We do NOT add it to all_fetched_items unless we want to rebuild today's report with OLD items too.
                        # But user request says: "Only process new articles".
                        # If we skip adding to all_fetched_items, they won't appear in today's report if they were fetched before.
                        # However, usually daily report should contain TODAY's items.
                        # If it's an old item already in DB, maybe we shouldn't report it again as "New".
                        # Let's decide: Only add to report if it was actually summarized NOW or if it's considered "today's news".
                        
                        # Current Logic:
                        # 1. If exists in DB, skip summary generation.
                        # 2. DO NOT add to all_fetched_items (so it won't be in the new report segment).
                        print(f"  - [Skip] Already in DB: {item.get('title')}")
                        continue
                    
                    if not summary:
                        print(f"  - Summarizing: {item.get('title')}")
                        summary = summarizer.summarize(content, video_url=video_url)
                    
                    # Save to DB (Full Archive)
                    # For Run Now, we save new item.
                    # For Full Regen, we overwrite.
                    item['summary'] = summary
                    db.save_article(item, summary)
                    
                    all_summaries[item_url] = summary
                    
                    # Tag the item with category from config
                    item['category'] = sub.get('category', 'General')
                    all_fetched_items.append(item)
                    
            except Exception as e:
                print(f"Error processing subscription {name}: {e}")
                
        # Generate daily report ONLY if we have new items
        if all_fetched_items:
            print("Generating daily report for NEW items...")
            archiver.generate_report(all_fetched_items, all_summaries)
        else:
            print("No new items fetched.")
            
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Update job completed.")

    def _python_executable():
        python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        if os.path.exists(python_exe):
            return python_exe
        import sys
        return sys.executable

    def _fetch_wechat_content_by_playwright(article_url: str) -> str:
        try:
            python_exe = _python_executable()
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(
                [python_exe, "fetch_wechat_playwright.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=creationflags,
            )
            stdout, stderr = process.communicate(input=json.dumps({"url": article_url}, ensure_ascii=False))
            if process.returncode != 0:
                return ""
            data = json.loads(stdout.strip()) if stdout else {}
            content = data.get("content", "")
            return content if isinstance(content, str) else ""
        except Exception:
            return ""

    def _date_str_from_publish_date(publish_date: str) -> str:
        if not publish_date:
            return ""
        s = str(publish_date).strip()
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return s[:10]
        try:
            dt = email.utils.parsedate_to_datetime(s)
            if dt:
                bj = dt.astimezone(timezone(timedelta(hours=8)))
                return bj.date().isoformat()
        except Exception:
            pass
        return ""

    def regenerate_all_summaries_and_archives():
        config_loader = ConfigLoader()
        config = config_loader.load()

        summarizer_config = config.get('summarizer', {})
        api_key = summarizer_config.get('api_key', 'YOUR_API_KEY')
        base_url = summarizer_config.get('base_url')
        model = summarizer_config.get('model', 'gpt-3.5-turbo')
        provider = summarizer_config.get('provider', 'openai')

        from src.summarizer.llm_summarizer import OpenAISummarizer
        summarizer = OpenAISummarizer(api_key=api_key, base_url=base_url, model=model, provider=provider)

        from src.database import DatabaseManager
        db = DatabaseManager()

        articles = db.get_all_articles(limit=50000)
        updated_articles = []

        total = len(articles)
        for i, article in enumerate(articles, start=1):
            url = article.get("url", "")
            content = article.get("content") or ""
            video_url = article.get("video_url") or None

            if url and "mp.weixin.qq.com" in url and len(content) < 200:
                fetched = _fetch_wechat_content_by_playwright(url)
                if fetched and len(fetched) > len(content):
                    content = fetched
                    db.update_content(url, content)
                    article["content"] = content

            summary = summarizer.summarize(content, video_url=video_url)
            db.update_summary(url, summary)
            article["summary"] = summary

            updated_articles.append(article)
            if i % 20 == 0 or i == total:
                print(f"Regenerated {i}/{total}")

        archive_dir = config.get("output", {}).get("directory", "archives")
        existing_dates = set()
        if os.path.isdir(archive_dir):
            for name in os.listdir(archive_dir):
                if name.startswith("daily_report_") and name.endswith(".json"):
                    date_part = name[len("daily_report_"):-len(".json")]
                    if len(date_part) == 10:
                        existing_dates.add(date_part)

        if existing_dates:
            from src.archiver.file_archiver import FileArchiver
            archiver = FileArchiver(output_dir=archive_dir)
            for date_str in sorted(existing_dates):
                items = [a for a in updated_articles if _date_str_from_publish_date(a.get("publish_date", "")) == date_str]
                summaries = {a.get("url", ""): a.get("summary", "") for a in items if a.get("url")}
                archiver.generate_report_for_date(date_str, items, summaries)
                print(f"Rebuilt archive: {date_str}")

        print("Done.")

    # 3. Check for command line arguments (Run Once mode)
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "--run-now":
            # Optional: check if a target name is provided as second arg
            target = sys.argv[2] if len(sys.argv) > 2 else None
            daily_job(target_name=target)
            return
        if sys.argv[1] == "--run-days":
            try:
                days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            except Exception:
                days = 3
            target = sys.argv[3] if len(sys.argv) > 3 else None
            daily_job(days_limit=days, target_name=target)
            return
        if sys.argv[1] == "--run-3days":
            target = sys.argv[2] if len(sys.argv) > 2 else None
            daily_job(days_limit=3, target_name=target)
            return
        if sys.argv[1] == "--regenerate-all":
            regenerate_all_summaries_and_archives()
            return

    # 4. Initialize scheduler
    scheduler = JobScheduler(config)
    
    # 5. Schedule the job
    # Check for multiple times in config
    scheduler_config = config.get('scheduler', {})
    times = scheduler_config.get('times', [])
    
    if not times:
        # Fallback to single time or default
        times = [scheduler_config.get('time', '08:00')]
        
    for time_str in times:
        print(f"Scheduling daily update at {time_str} (days_limit=3)")
        # Use a lambda to pass arguments
        # Note: We must bind days_limit=3 to ensure it's used
        scheduler.add_daily_job(lambda: daily_job(days_limit=3), time_str=time_str)
    
    # 6. Start the scheduler (blocking)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nScheduler stopped by user.")

if __name__ == "__main__":
    main()
