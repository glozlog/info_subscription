import time
import os
import json
import subprocess
import email.utils
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from src.utils.config_loader import ConfigLoader
from src.scheduler.job import JobScheduler
from typing import Dict, Any, List, Tuple

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
        
        # --- Phase 1: Fetch from all subscriptions (serial, fetchers may have side effects) ---
        items_to_summarize: List[Tuple[Dict[str, Any], str]] = []  # (item, category)
        skipped = 0

        for sub in subscriptions:
            platform = sub.get('platform')
            name = sub.get('name')
            url = sub.get('url')
            category = sub.get('category', 'General')

            if not platform or not url:
                print(f"Skipping invalid subscription: {sub}")
                continue

            print(f"Fetching from {name} ({platform})...")

            try:
                fetcher = FetcherFactory.get_fetcher(platform)
                if not fetcher:
                    print(f"No fetcher found for {platform}")
                    continue

                import inspect
                sig = inspect.signature(fetcher.fetch)
                if 'source_name' in sig.parameters:
                    items = fetcher.fetch(url, source_name=name)
                else:
                    items = fetcher.fetch(url)

                print(f"  - Fetched {len(items)} items")

                if days_limit > 0:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
                    items = [item for item in items if _parse_to_datetime_utc(item.get("publish_date")) > cutoff]
                    print(f"  - Filtered to {len(items)} items (within {days_limit} days)")

                # Batch-check which URLs already exist in DB
                item_urls = [item.get('url') for item in items if item.get('url')]
                existing_map = db.get_existing_urls(item_urls)

                for item in items:
                    item_url = item.get('url')
                    if item_url in existing_map and existing_map[item_url]:
                        skipped += 1
                        continue
                    items_to_summarize.append((item, category))

            except Exception as e:
                print(f"Error fetching subscription {name}: {e}")

        if skipped:
            print(f"Skipped {skipped} articles already in DB.")

        if not items_to_summarize:
            print("No new items to process.")
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Update job completed.")
            return

        # --- Phase 2: Parallel summarization ---
        print(f"Summarizing {len(items_to_summarize)} new articles (max 4 concurrent)...")
        t_start = time.time()

        all_fetched_items = []
        all_summaries = {}

        def _summarize_item(item: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
            content = item.get('content')
            video_url = item.get('video_url')
            summary = summarizer.summarize(content, video_url=video_url)
            return item, summary

        max_workers = min(4, len(items_to_summarize))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_category = {}
            for item, category in items_to_summarize:
                future = executor.submit(_summarize_item, item)
                future_to_category[future] = category

            for i, future in enumerate(as_completed(future_to_category), 1):
                category = future_to_category[future]
                try:
                    item, summary = future.result()
                    item['summary'] = summary
                    item['category'] = category
                    all_summaries[item.get('url')] = summary
                    all_fetched_items.append(item)
                    print(f"  [{i}/{len(items_to_summarize)}] {item.get('title', '')[:50]}")
                except Exception as e:
                    print(f"  [{i}/{len(items_to_summarize)}] Summarization failed: {e}")

        elapsed = time.time() - t_start
        print(f"Summarization done in {elapsed:.1f}s ({len(all_fetched_items)} articles)")

        # --- Phase 3: Batch save + report ---
        if all_fetched_items:
            saved = db.save_articles_batch(all_fetched_items)
            print(f"Saved {saved} new articles to DB.")
            print("Generating daily report...")
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
        total = len(articles)
        print(f"Regenerating summaries for {total} articles...")

        # Phase 1: Pre-fetch WeChat content serially (subprocess-based, not parallelizable)
        refetched = 0
        for article in articles:
            url = article.get("url", "")
            content = article.get("content") or ""
            if url and "mp.weixin.qq.com" in url and len(content) < 200:
                fetched = _fetch_wechat_content_by_playwright(url)
                if fetched and len(fetched) > len(content):
                    db.update_content(url, fetched)
                    article["content"] = fetched
                    refetched += 1
        if refetched:
            print(f"Re-fetched content for {refetched} WeChat articles.")

        # Phase 2: Parallel summarization
        t_start = time.time()
        completed = 0

        def _summarize_article(article: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
            content = article.get("content") or ""
            video_url = article.get("video_url") or None
            summary = summarizer.summarize(content, video_url=video_url)
            return article, summary

        max_workers = min(4, total)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_summarize_article, a): a for a in articles}
            for future in as_completed(futures):
                try:
                    article, summary = future.result()
                    article["summary"] = summary
                    db.update_summary(article.get("url", ""), summary)
                except Exception as e:
                    print(f"Error summarizing {futures[future].get('url', '?')}: {e}")
                completed += 1
                if completed % 20 == 0 or completed == total:
                    print(f"Regenerated {completed}/{total}")

        elapsed = time.time() - t_start
        print(f"Summarization done in {elapsed:.1f}s")

        # Phase 3: Rebuild archives
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
                items = [a for a in articles if _date_str_from_publish_date(a.get("publish_date", "")) == date_str]
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
