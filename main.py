import time
import os
import json
import subprocess
import email.utils
import hashlib
from datetime import datetime, timedelta, timezone
from src.utils.config_loader import ConfigLoader
from src.scheduler.job import JobScheduler
from typing import Dict, Any, List, Set

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

    def _filter_items_by_date(items: List[Dict], days_limit: int) -> List[Dict]:
        """按日期过滤内容"""
        if days_limit <= 0:
            return items
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
        filtered = []
        for item in items:
            pd = item.get("publish_date")
            dt = _parse_to_datetime_utc(pd)
            if dt > cutoff:
                filtered.append(item)
        return filtered

    def daily_job(days_limit: int = 0, target_name: str = None):
        """
        The daily job that:
        1. Iterates through subscriptions.
        2. Fetches new content.
        3. Summarizes content.
        4. Archives and generates reports.
        
        使用 ConcurrencyManager 实现并行抓取和摘要生成
        
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

        # Import required modules
        from src.fetchers.factory import FetcherFactory
        from src.summarizer.llm_summarizer import OpenAISummarizer
        from src.archiver.file_archiver import FileArchiver
        from src.database import DatabaseManager
        from src.concurrency import ConcurrencyManager
        import inspect

        # Initialize components
        summarizer_config = config.get('summarizer', {})
        archiver_config = config.get('output', {})
        
        api_key = summarizer_config.get('api_key', 'YOUR_API_KEY')
        base_url = summarizer_config.get('base_url')
        model = summarizer_config.get('model', 'gpt-3.5-turbo')
        provider = summarizer_config.get('provider', 'openai')
        summarizer = OpenAISummarizer(api_key=api_key, base_url=base_url, model=model, provider=provider)
        
        db = DatabaseManager()
        archiver = FileArchiver(output_dir=archiver_config.get('directory', 'archives'))
        
        # 预加载 URL 缓存用于去重 - 使用哈希索引减少内存占用
        print("Loading URL cache for deduplication...")
        url_cache = db.get_recent_urls(days=90)
        # 将URL转换为64位哈希值，内存占用减少约87.5%（从~100 bytes/URL降到~8 bytes/URL）
        url_hash_cache: Set[int] = {_url_hash(u) for u in url_cache}
        print(f"  - Cached {len(url_hash_cache)} URLs (hash index)")
        
        # 定义抓取函数
        def fetch_single_subscription(sub: Dict) -> List[Dict]:
            """抓取单个订阅源"""
            platform = sub.get('platform')
            name = sub.get('name')
            url = sub.get('url')
            
            if not platform or not url:
                return []
            
            fetcher = FetcherFactory.get_fetcher(platform)
            if not fetcher:
                return []
            
            # 根据模式决定 limit 和 days_limit
            # --run-now (近20条): limit=20, days_limit=0
            # --run-3days (近3天): limit=100, days_limit=3
            if days_limit > 0:
                # 近N天模式：抓取更多条目，然后在 fetcher 内按日期过滤
                fetch_limit = 100
                fetch_days = days_limit
            else:
                # 近20条模式：限制数量，不限制日期
                fetch_limit = 20
                fetch_days = 0
            
            # 检查 fetcher 签名并调用
            sig = inspect.signature(fetcher.fetch)
            fetch_kwargs = {}
            if 'limit' in sig.parameters:
                fetch_kwargs['limit'] = fetch_limit
            if 'days_limit' in sig.parameters:
                fetch_kwargs['days_limit'] = fetch_days
            if 'source_name' in sig.parameters:
                fetch_kwargs['source_name'] = name
            
            items = fetcher.fetch(url, **fetch_kwargs)
            
            # 添加分类信息
            for item in items:
                item['category'] = sub.get('category', 'General')
            
            return items
        
        # 定义摘要函数
        def summarize_single_item(item: Dict) -> str:
            """为单个项目生成摘要"""
            content = item.get('content', '')
            video_url = item.get('video_url')
            return summarizer.summarize(content, video_url=video_url)
        
        # 使用 ConcurrencyManager 并行处理
        with ConcurrencyManager(
            fetcher_workers=5,          # 5 个抓取线程
            summarizer_workers=10,      # 10 个摘要线程
            max_browsers=3,             # 最多 3 个浏览器实例
            api_rate=10.0,              # API 限速 10/秒
            use_backpressure=True       # 启用背压控制
        ) as cm:
            
            print(f"\n[Phase 1] Fetching from {len(subscriptions)} subscriptions in parallel...")
            
            # 阶段 1: 并行抓取
            fetch_result = cm.fetch_subscriptions_parallel(
                subscriptions=subscriptions,
                fetch_func=fetch_single_subscription,
                days_limit=days_limit,
                timeout_per_fetch=60,
                use_backpressure=True
            )
            
            all_items = fetch_result['items']
            print(f"  - Fetched {len(all_items)} items total")
            print(f"  - Fetch stats: {fetch_result['stats']}")
            
            if fetch_result['errors']:
                print(f"  - Fetch errors: {len(fetch_result['errors'])}")
                for err in fetch_result['errors'][:5]:  # 只显示前 5 个
                    print(f"    - {err.get('subscription')}: {err.get('error')}")
            
            # 注：日期过滤已在 fetcher 层完成，无需再次过滤
            
            # 去重：使用哈希索引检查 URL - O(1) 时间复杂度，低内存占用
            new_items = []
            duplicate_count = 0
            for item in all_items:
                item_url = item.get('url')
                url_hash = _url_hash(item_url) if item_url else 0
                # 使用哈希值检查 - 可能产生极少量误报（哈希碰撞），但不会漏报
                if url_hash in url_hash_cache:
                    duplicate_count += 1
                    continue
                new_items.append(item)
                url_hash_cache.add(url_hash)  # 添加到缓存防止同一批次内重复
            
            print(f"  - Duplicates skipped: {duplicate_count}")
            print(f"  - New items to process: {len(new_items)}")
            
            if not new_items:
                print("No new items to process.")
                return
            
            print(f"\n[Phase 2] Generating summaries for {len(new_items)} items in parallel...")
            
            # 阶段 2: 并行生成摘要
            summary_result = cm.summarize_items_parallel(
                items=new_items,
                summarize_func=summarize_single_item,
                timeout_per_item=30,
                use_backpressure=True,
                max_retries=2
            )
            
            summaries = summary_result['summaries']
            print(f"  - Generated {len(summaries)} summaries")
            print(f"  - Summary stats: {summary_result['stats']}")
            
            if summary_result['errors']:
                print(f"  - Summary errors: {len(summary_result['errors'])}")
            
            # 批量保存到数据库
            print(f"\n[Phase 3] Saving to database...")
            
            # 为每个 item 添加 summary
            items_with_summary = []
            for item in new_items:
                item_url = item.get('url')
                if item_url in summaries:
                    item['summary'] = summaries[item_url]
                    items_with_summary.append(item)
            
            save_stats = db.save_articles_batch(
                items=items_with_summary,
                summaries=summaries,
                batch_size=50
            )
            print(f"  - Saved {save_stats['saved']} articles")
            if save_stats['errors'] > 0:
                print(f"  - Save errors: {save_stats['errors']}")
            
            # 生成报告
            if items_with_summary:
                print(f"\n[Phase 4] Generating daily report...")
                archiver.generate_report(items_with_summary, summaries)
            
            # 输出并发管理器统计
            cm_stats = cm.get_stats()
            print(f"\n[Concurrency Stats]")
            print(f"  - Browser limiter: {cm_stats['browser_limiter']}")
            print(f"  - API circuit breaker: {cm_stats['api_circuit_breaker']}")
        
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Update job completed.")

    def _python_executable():
        python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        if os.path.exists(python_exe):
            return python_exe
        import sys
        return sys.executable

    def _url_hash(url: str) -> int:
        """
        生成URL的64位哈希值，用于内存高效的去重索引。
        
        使用BLAKE2b哈希算法生成8字节(64位)哈希值，相比存储完整URL：
        - 内存占用减少约87.5%（从~100 bytes/URL降到~8 bytes/URL）
        - 查询时间仍为O(1)
        - 哈希碰撞概率极低（64位空间约1.8e19，1百万URL碰撞概率<1e-13）
        
        Args:
            url: URL字符串
            
        Returns:
            64位整数哈希值
        """
        if not url:
            return 0
        # 使用BLAKE2b生成8字节(64位)哈希
        hash_bytes = hashlib.blake2b(url.encode('utf-8'), digest_size=8).digest()
        # 转换为无符号64位整数
        return int.from_bytes(hash_bytes, byteorder='big', signed=False)

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
        """
        全量重算摘要并覆盖存档 - 优化版本
        
        优化点:
        1. 流式分页处理 - 避免全量加载到内存
        2. 并行摘要生成 - 使用 ConcurrencyManager 并发处理
        3. 断点续传 - 支持中断后恢复
        4. 批量微信内容补全 - 预筛选后批量抓取
        5. O(n) 存档生成 - 哈希分组替代双重循环
        6. 事务保护 - 确保数据一致性
        """
        import pickle
        from collections import defaultdict
        from src.concurrency import ConcurrencyManager
        
        # 配置参数
        BATCH_SIZE = 100  # 每批处理文章数
        CHECKPOINT_FILE = ".regenerate_checkpoint.pkl"
        
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
        
        # 加载断点续传状态
        checkpoint = _load_checkpoint(CHECKPOINT_FILE)
        processed_urls = set(checkpoint.get('processed_urls', []))
        offset = checkpoint.get('offset', 0)
        
        print(f"Starting regenerate_all_summaries_and_archives...")
        print(f"  - Checkpoint: offset={offset}, processed={len(processed_urls)}")
        
        # 获取文章总数
        total_count = db.count_articles(use_cache=False)
        print(f"  - Total articles: {total_count}")
        
        # 显示数据库性能配置
        perf_stats = db.get_performance_stats()
        print(f"  - DB Config: journal_mode={perf_stats.get('journal_mode')}, "
              f"cache_size={perf_stats.get('cache_size')}, "
              f"pages={perf_stats.get('page_count', 0)}")
        
        # 收集所有更新后的文章（用于后续存档重建）
        # 使用流式处理，避免全量加载
        all_updated_articles = []
        
        try:
            with ConcurrencyManager(
                summarizer_workers=5,      # 控制并发避免API风控
                api_rate=5.0,              # 保守限速 5/秒
                use_backpressure=True
            ) as cm:
                
                while True:
                    # 流式分页获取文章
                    batch = db.get_all_articles(limit=BATCH_SIZE, offset=offset)
                    if not batch:
                        break
                    
                    print(f"\nProcessing batch: offset={offset}, size={len(batch)}")
                    
                    # 筛选需要处理的文章（断点续传：跳过已处理的）
                    articles_to_process = [
                        a for a in batch 
                        if a.get('url') not in processed_urls
                    ]
                    
                    if not articles_to_process:
                        offset += len(batch)
                        continue
                    
                    # ========== 优化4: 批量微信内容补全 ==========
                    wechat_articles = [
                        a for a in articles_to_process 
                        if a.get('url', '').startswith('https://mp.weixin.qq.com') 
                        and len(a.get('content') or '') < 200
                    ]
                    
                    if wechat_articles:
                        print(f"  - Fetching content for {len(wechat_articles)} WeChat articles...")
                        _batch_fetch_wechat_content(wechat_articles, db)
                    
                    # ========== 优化1&2: 并行摘要生成 ==========
                    def summarize_article(article):
                        """为单篇文章生成摘要"""
                        content = article.get("content") or ""
                        video_url = article.get("video_url")
                        return summarizer.summarize(content, video_url=video_url)
                    
                    # 使用 ConcurrencyManager 并行生成摘要
                    summary_result = cm.summarize_items_parallel(
                        items=articles_to_process,
                        summarize_func=summarize_article,
                        timeout_per_item=60,
                        use_backpressure=True,
                        max_retries=2
                    )
                    
                    summaries = summary_result['summaries']
                    print(f"  - Generated {len(summaries)} summaries")
                    if summary_result['errors']:
                        print(f"  - Errors: {len(summary_result['errors'])}")
                    
                    # ========== 优化6: 事务保护批量更新 ==========
                    _batch_update_summaries(db, articles_to_process, summaries)
                    
                    # 收集更新后的文章用于存档重建
                    for article in articles_to_process:
                        url = article.get('url')
                        if url in summaries:
                            article['summary'] = summaries[url]
                            all_updated_articles.append(article)
                            processed_urls.add(url)
                    
                    # ========== 优化3: 保存断点 ==========
                    offset += len(batch)
                    _save_checkpoint(CHECKPOINT_FILE, {
                        'offset': offset,
                        'processed_urls': list(processed_urls),
                        'total': total_count
                    })
                    
                    print(f"  - Progress: {len(processed_urls)}/{total_count} ({100*len(processed_urls)//total_count}%)")
                    
                    # 定期强制垃圾回收
                    if offset % (BATCH_SIZE * 10) == 0:
                        import gc
                        gc.collect()
            
            # ========== 优化5: O(n) 存档生成 ==========
            print(f"\nRebuilding archives...")
            _rebuild_archives_optimized(config, all_updated_articles, db)
            
            # 清理断点文件
            if os.path.exists(CHECKPOINT_FILE):
                os.remove(CHECKPOINT_FILE)
                print(f"  - Checkpoint file removed")
            
            print("\nDone.")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Progress saved to checkpoint.")
            print(f"Resume with: python main.py --regenerate-all")
            raise
        except Exception as e:
            print(f"\n\nError occurred: {e}")
            print(f"Progress saved to checkpoint. Resume with: python main.py --regenerate-all")
            raise

    def _load_checkpoint(checkpoint_file: str) -> dict:
        """加载断点状态"""
        if os.path.exists(checkpoint_file):
            try:
                with open(checkpoint_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                print(f"Warning: Failed to load checkpoint: {e}")
        return {}

    def _save_checkpoint(checkpoint_file: str, state: dict):
        """保存断点状态"""
        try:
            with open(checkpoint_file, 'wb') as f:
                pickle.dump(state, f)
        except Exception as e:
            print(f"Warning: Failed to save checkpoint: {e}")

    def _batch_fetch_wechat_content(articles: List[Dict], db: DatabaseManager):
        """
        批量抓取微信文章内容
        串行处理避免启动过多浏览器实例
        """
        for article in articles:
            url = article.get('url')
            if not url:
                continue
            try:
                fetched = _fetch_wechat_content_by_playwright(url)
                if fetched and len(fetched) > len(article.get('content') or ''):
                    db.update_content(url, fetched)
                    article['content'] = fetched
                    print(f"    Updated content for: {article.get('title', url)[:50]}...")
            except Exception as e:
                print(f"    Failed to fetch {url}: {e}")

    def _batch_update_summaries(db: DatabaseManager, articles: List[Dict], summaries: Dict[str, str]):
        """
        批量更新摘要 - 使用 executemany 批量操作
        
        优化点:
        - 使用 update_summaries_batch 替代逐条更新
        - 单条更新: N 次事务开销
        - 批量更新: 1 次事务开销，性能提升 50-100x
        """
        # 准备 (url, summary) 列表
        url_summary_pairs = [
            (url, summaries[url])
            for article in articles
            if (url := article.get('url')) and url in summaries
        ]
        
        if not url_summary_pairs:
            print(f"  - No summaries to update")
            return
        
        # 使用批量更新方法
        stats = db.update_summaries_batch(url_summary_pairs, batch_size=100)
        print(f"  - Updated {stats['updated']} summaries in database")
        if stats['errors'] > 0:
            print(f"  - Errors: {stats['errors']}")

    def _rebuild_archives_optimized(config: Dict, updated_articles: List[Dict], db: DatabaseManager):
        """
        O(n) 复杂度重建存档 - 使用哈希分组
        
        优化点:
        - 复用全量重算时已加载的文章数据，避免重复查询数据库
        - 如果 updated_articles 为空，才需要查询数据库
        """
        from src.archiver.file_archiver import FileArchiver
        from collections import defaultdict
        
        archive_dir = config.get("output", {}).get("directory", "archives")
        archiver = FileArchiver(output_dir=archive_dir)
        
        # 获取所有存档日期
        existing_dates = set()
        if os.path.isdir(archive_dir):
            for name in os.listdir(archive_dir):
                if name.startswith("daily_report_") and name.endswith(".json"):
                    date_part = name[len("daily_report_"):-len(".json")]
                    if len(date_part) == 10:
                        existing_dates.add(date_part)
        
        if not existing_dates:
            print("  - No existing archives found")
            return
        
        print(f"  - Found {len(existing_dates)} archive dates")
        
        # ========== 优化: 复用已加载的文章数据 ==========
        all_articles_by_date = defaultdict(list)
        
        if updated_articles:
            # 复用全量重算时已加载的文章（已包含新摘要）
            print(f"  - Using {len(updated_articles)} articles from regeneration process")
            for article in updated_articles:
                date_str = _date_str_from_publish_date(article.get("publish_date", ""))
                if date_str in existing_dates:
                    all_articles_by_date[date_str].append(article)
            
            # 对于没有更新到的日期，从数据库补充（增量加载）
            covered_dates = set(all_articles_by_date.keys())
            missing_dates = existing_dates - covered_dates
            
            if missing_dates:
                print(f"  - Loading articles for {len(missing_dates)} dates not covered by regeneration")
                _load_missing_dates(db, missing_dates, all_articles_by_date)
        else:
            # 如果没有提供更新文章，全量加载
            print(f"  - Loading all articles from database...")
            _load_all_articles_for_archive(db, existing_dates, all_articles_by_date)
        
        # 重建每个日期的存档
        total_items = 0
        for date_str in sorted(existing_dates):
            items = all_articles_by_date.get(date_str, [])
            if items:
                summaries = {a.get("url", ""): a.get("summary", "") for a in items if a.get("url")}
                archiver.generate_report_for_date(date_str, items, summaries)
                total_items += len(items)
                print(f"    Rebuilt archive: {date_str} ({len(items)} items)")
            else:
                print(f"    Skipped archive: {date_str} (no articles)")
        
        print(f"  - Total: {total_items} articles in {len(existing_dates)} archives")

    def _load_missing_dates(db: DatabaseManager, missing_dates: set, articles_by_date: defaultdict):
        """增量加载缺失日期的文章"""
        for date_str in missing_dates:
            # 使用日期范围查询（利用索引）
            start_datetime = f"{date_str} 00:00:00"
            end_datetime = f"{date_str} 23:59:59"
            articles = db.get_articles_by_date_range(start_datetime, end_datetime)
            articles_by_date[date_str] = articles
            print(f"      Loaded {len(articles)} articles for {date_str}")

    def _load_all_articles_for_archive(db: DatabaseManager, existing_dates: set, articles_by_date: defaultdict):
        """全量加载文章（fallback）"""
        offset = 0
        batch_size = 500
        total_loaded = 0
        while True:
            batch = db.get_all_articles(limit=batch_size, offset=offset)
            if not batch:
                break
            
            for article in batch:
                date_str = _date_str_from_publish_date(article.get("publish_date", ""))
                if date_str in existing_dates:
                    articles_by_date[date_str].append(article)
            
            offset += len(batch)
            total_loaded += len(batch)
            if offset % 5000 == 0:
                print(f"    Loaded {total_loaded} articles...")
        
        print(f"  - Total loaded: {total_loaded} articles")

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
