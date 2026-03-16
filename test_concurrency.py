"""
并发管理器测试脚本 - 验证并行抓取和 LLM 调用功能
"""
import time
import sys
from typing import List, Dict, Any

# 测试 ConcurrencyManager 基础功能
def test_limiters():
    """测试资源限制器"""
    print("\n=== Testing Limiters ===")
    from src.concurrency import TokenBucket, CircuitBreaker, ResourceLimiter
    
    # 测试 TokenBucket
    print("\n1. TokenBucket test:")
    bucket = TokenBucket(rate=5, capacity=10)
    
    # 快速消耗令牌
    start = time.time()
    for i in range(12):
        if bucket.acquire(blocking=False):
            print(f"  Token {i+1}: acquired")
        else:
            print(f"  Token {i+1}: rejected (bucket empty)")
            bucket.acquire(blocking=True, timeout=1)  # 等待
    elapsed = time.time() - start
    print(f"  Total time for 12 tokens at 5/s: {elapsed:.2f}s")
    
    # 测试批量申请
    print("\n2. TokenBucket batch test:")
    bucket2 = TokenBucket(rate=10, capacity=20)
    granted = bucket2.acquire_batch(15)
    print(f"  Requested 15, granted: {granted}")
    
    # 测试 CircuitBreaker
    print("\n3. CircuitBreaker test:")
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=2)
    
    def success_func():
        return "success"
    
    def fail_func():
        raise ValueError("intentional error")
    
    # 成功调用
    result = cb.call(success_func)
    print(f"  Success call: {result}, state: {cb.get_state()}")
    
    # 连续失败
    for i in range(3):
        try:
            cb.call(fail_func)
        except ValueError:
            print(f"  Fail call {i+1}: state={cb.get_state()}")
    
    # 断路器应该打开
    print(f"  After 3 failures, state: {cb.get_state()}")
    
    try:
        cb.call(success_func)
    except Exception as e:
        print(f"  Call while OPEN: {type(e).__name__}")
    
    # 等待恢复
    print("  Waiting 2s for recovery...")
    time.sleep(2)
    result = cb.call(success_func)
    print(f"  Call after recovery: {result}, state: {cb.get_state()}")
    
    # 测试 ResourceLimiter
    print("\n4. ResourceLimiter test:")
    limiter = ResourceLimiter(max_resources=2, name="test_resource")
    
    acquired = []
    for i in range(4):
        if limiter.acquire(timeout=0.1):
            acquired.append(i)
            print(f"  Resource {i}: acquired (active: {limiter.get_active_count()})")
        else:
            print(f"  Resource {i}: timeout (active: {limiter.get_active_count()})")
    
    # 释放资源
    for _ in acquired:
        limiter.release()
        print(f"  Released (active: {limiter.get_active_count()})")


def test_collectors():
    """测试结果收集器"""
    print("\n=== Testing Collectors ===")
    from src.concurrency import ThreadSafeResultCollector, StreamingResultCollector
    import threading
    
    # 测试 ThreadSafeResultCollector
    print("\n1. ThreadSafeResultCollector test:")
    collector = ThreadSafeResultCollector()
    
    def worker(worker_id):
        for i in range(5):
            if i % 2 == 0:
                collector.add_success(f"worker_{worker_id}", f"result_{i}")
            else:
                collector.add_error(f"worker_{worker_id}", Exception(f"error_{i}"))
    
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    stats = collector.get_stats()
    print(f"  Stats: {stats}")
    print(f"  Successes: {len(collector.get_successes())}")
    print(f"  Errors: {len(collector.get_errors())}")
    
    # 测试 StreamingResultCollector
    print("\n2. StreamingResultCollector test:")
    stream_collector = StreamingResultCollector(maxsize=5)
    
    def producer():
        for i in range(10):
            stream_collector.put_success("test", f"item_{i}")
        stream_collector.mark_completed()
    
    threading.Thread(target=producer).start()
    
    count = 0
    for result in stream_collector.iterate_results(timeout=0.5):
        count += 1
        if count <= 3:
            print(f"  Received: {result['type']} - {result.get('result', result.get('error'))}")
    
    print(f"  Total received: {count}")


def test_concurrency_manager():
    """测试 ConcurrencyManager"""
    print("\n=== Testing ConcurrencyManager ===")
    from src.concurrency import ConcurrencyManager
    
    # 模拟抓取函数
    def mock_fetch(sub: Dict) -> List[Dict]:
        time.sleep(0.1)  # 模拟网络延迟
        return [
            {"url": f"{sub['name']}_item_{i}", "title": f"Item {i}"}
            for i in range(3)
        ]
    
    # 模拟摘要函数
    def mock_summarize(item: Dict) -> str:
        time.sleep(0.05)  # 模拟 API 延迟
        return f"Summary of {item['title']}"
    
    print("\n1. Parallel fetch test:")
    subscriptions = [
        {"name": f"Sub_{i}", "url": f"http://example.com/{i}"}
        for i in range(10)
    ]
    
    with ConcurrencyManager(
        fetcher_workers=5,
        summarizer_workers=5,
        max_browsers=3,
        api_rate=20.0
    ) as cm:
        
        start = time.time()
        result = cm.fetch_subscriptions_parallel(
            subscriptions=subscriptions,
            fetch_func=mock_fetch,
            use_backpressure=True
        )
        elapsed = time.time() - start
        
        print(f"  Fetched {len(result['items'])} items from {len(subscriptions)} subs")
        print(f"  Time: {elapsed:.2f}s (expected ~0.2s with 5 workers)")
        print(f"  Stats: {result['stats']}")
        
        print("\n2. Parallel summarize test:")
        items = result['items'][:10]
        
        start = time.time()
        summary_result = cm.summarize_items_parallel(
            items=items,
            summarize_func=mock_summarize,
            use_backpressure=True
        )
        elapsed = time.time() - start
        
        print(f"  Generated {len(summary_result['summaries'])} summaries")
        print(f"  Time: {elapsed:.2f}s (expected ~0.1s with 5 workers)")
        print(f"  Stats: {summary_result['stats']}")
        
        print("\n3. Concurrency stats:")
        stats = cm.get_stats()
        print(f"  {stats}")


def test_database_batch():
    """测试数据库批量操作"""
    print("\n=== Testing Database Batch Operations ===")
    from src.database import DatabaseManager
    import tempfile
    import os
    
    # 使用临时数据库
    temp_db = tempfile.mktemp(suffix='.db')
    db = DatabaseManager(db_path=temp_db)
    
    # 生成测试数据
    test_items = [
        {
            'url': f'http://test.com/article_{i}',
            'title': f'Test Article {i}',
            'content': f'Content {i} ' * 100,
            'author': f'Author {i % 5}',
            'platform': 'test',
            'category': 'test',
            'publish_date': '2024-01-01'
        }
        for i in range(100)
    ]
    
    summaries = {item['url']: f'Summary {i}' for i, item in enumerate(test_items)}
    
    print(f"\n1. Batch save test (100 items, batch_size=20):")
    start = time.time()
    stats = db.save_articles_batch(test_items, summaries, batch_size=20)
    elapsed = time.time() - start
    print(f"  Saved: {stats['saved']}, Errors: {stats['errors']}")
    print(f"  Time: {elapsed:.3f}s")
    
    print(f"\n2. URL cache test:")
    start = time.time()
    urls = db.get_recent_urls(days=90)
    elapsed = time.time() - start
    print(f"  Loaded {len(urls)} URLs in {elapsed:.3f}s")
    print(f"  Sample URLs: {list(urls)[:3]}")
    
    print(f"\n3. Batch update test:")
    updates = [(f'http://test.com/article_{i}', f'Updated Summary {i}') for i in range(50)]
    start = time.time()
    stats = db.update_summaries_batch(updates, batch_size=10)
    elapsed = time.time() - start
    print(f"  Updated: {stats['updated']}, Errors: {stats['errors']}")
    print(f"  Time: {elapsed:.3f}s")
    
    # 清理
    os.unlink(temp_db)
    print(f"\n  Cleaned up temp database")


def test_integration():
    """集成测试 - 模拟完整流程"""
    print("\n=== Integration Test ===")
    from src.concurrency import ConcurrencyManager
    from src.database import DatabaseManager
    import tempfile
    import os
    
    temp_db = tempfile.mktemp(suffix='.db')
    db = DatabaseManager(db_path=temp_db)
    
    # 模拟订阅源
    subscriptions = [
        {"name": f"Source_{i}", "url": f"http://source{i}.com", "category": "test"}
        for i in range(20)
    ]
    
    def fetch_func(sub):
        # 模拟抓取：每个源返回 5 个 item
        time.sleep(0.05)
        return [
            {
                'url': f"{sub['url']}/item_{j}",
                'title': f"{sub['name']} Article {j}",
                'content': f"Content {j}",
                'author': sub['name'],
                'platform': 'test',
                'category': sub.get('category', 'General'),
                'publish_date': '2024-01-01'
            }
            for j in range(5)
        ]
    
    def summarize_func(item):
        time.sleep(0.02)
        return f"Summary of {item['title']}"
    
    print(f"\nProcessing {len(subscriptions)} subscriptions...")
    
    with ConcurrencyManager(
        fetcher_workers=5,
        summarizer_workers=10,
        max_browsers=3,
        api_rate=50.0
    ) as cm:
        
        # 1. 并行抓取
        start = time.time()
        fetch_result = cm.fetch_subscriptions_parallel(
            subscriptions=subscriptions,
            fetch_func=fetch_func,
            use_backpressure=True
        )
        fetch_time = time.time() - start
        
        all_items = fetch_result['items']
        print(f"  Fetch: {len(all_items)} items in {fetch_time:.2f}s")
        
        # 2. 去重（模拟）
        url_cache = db.get_recent_urls(days=90)
        new_items = [item for item in all_items if item['url'] not in url_cache]
        print(f"  Deduplication: {len(new_items)} new items")
        
        # 3. 并行摘要
        start = time.time()
        summary_result = cm.summarize_items_parallel(
            items=new_items,
            summarize_func=summarize_func,
            use_backpressure=True
        )
        summary_time = time.time() - start
        
        print(f"  Summarize: {len(summary_result['summaries'])} summaries in {summary_time:.2f}s")
        
        # 4. 批量保存
        for item in new_items:
            item['summary'] = summary_result['summaries'].get(item['url'], '')
        
        start = time.time()
        save_stats = db.save_articles_batch(new_items, batch_size=25)
        save_time = time.time() - start
        
        print(f"  Save: {save_stats['saved']} items in {save_time:.3f}s")
        
        # 5. 统计
        total_time = fetch_time + summary_time + save_time
        print(f"\n  Total time: {total_time:.2f}s")
        print(f"  Throughput: {len(new_items)/total_time:.1f} items/s")
    
    os.unlink(temp_db)


def main():
    """运行所有测试"""
    print("=" * 60)
    print("ConcurrencyManager Test Suite")
    print("=" * 60)
    
    try:
        test_limiters()
    except Exception as e:
        print(f"Limiters test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_collectors()
    except Exception as e:
        print(f"Collectors test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_concurrency_manager()
    except Exception as e:
        print(f"ConcurrencyManager test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_database_batch()
    except Exception as e:
        print(f"Database batch test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_integration()
    except Exception as e:
        print(f"Integration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
