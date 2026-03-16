"""
并发管理器核心模块 - 统一调度线程池、资源限制和清理管理
"""
import logging
import threading
import gc
from typing import List, Dict, Any, Optional, Iterator, Callable
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED

from .limiters import TokenBucket, CircuitBreaker, ResourceLimiter, timeout
from .registry import CleanupRegistry
from .collectors import (
    ThreadSafeResultCollector, 
    StreamingResultCollector,
    BackpressureExecutor,
    BatchProcessor
)


class ConcurrencyManager:
    """
    统一并发管理器
    
    职责:
    1. 管理两个独立线程池（抓取 + 摘要）
    2. 资源限制（浏览器并发、API 速率）
    3. 断路器保护
    4. 自动清理
    
    使用方式:
        with ConcurrencyManager(...) as cm:
            results = cm.fetch_subscriptions_parallel(...)
            summaries = cm.summarize_items_parallel(...)
    """
    
    def __init__(
        self,
        fetcher_workers: int = 5,
        summarizer_workers: int = 10,
        max_browsers: int = 3,
        api_rate: float = 10.0,
        api_failure_threshold: int = 5,
        api_recovery_timeout: float = 60.0,
        enable_streaming: bool = True,
        streaming_queue_size: int = 100
    ):
        """
        Args:
            fetcher_workers: 抓取线程池大小
            summarizer_workers: 摘要线程池大小
            max_browsers: 最大并发浏览器实例数
            api_rate: API 调用速率限制（每秒）
            api_failure_threshold: API 断路器失败阈值
            api_recovery_timeout: API 断路器恢复超时（秒）
            enable_streaming: 是否启用流式处理
            streaming_queue_size: 流式队列大小
        """
        # 线程池
        self.fetcher_pool = ThreadPoolExecutor(
            max_workers=fetcher_workers,
            thread_name_prefix="fetcher"
        )
        self.summarizer_pool = ThreadPoolExecutor(
            max_workers=summarizer_workers,
            thread_name_prefix="summarizer"
        )
        
        # 资源限制器
        self.browser_limiter = ResourceLimiter(max_browsers, name="browser")
        self.api_token_bucket = TokenBucket(rate=api_rate, capacity=api_rate * 2)
        
        # 断路器
        self.api_circuit_breaker = CircuitBreaker(
            failure_threshold=api_failure_threshold,
            recovery_timeout=api_recovery_timeout
        )
        
        # 清理注册表
        self.cleanup_registry = CleanupRegistry()
        self._register_resources()
        
        # 流式处理配置
        self.enable_streaming = enable_streaming
        self.streaming_queue_size = streaming_queue_size
        
        # 批量处理器
        self.batch_processor = BatchProcessor(batch_size=100)
        
        # 背压执行器
        self.fetcher_backpressure = BackpressureExecutor(
            self.fetcher_pool, 
            max_inflight=fetcher_workers * 2
        )
        self.summarizer_backpressure = BackpressureExecutor(
            self.summarizer_pool,
            max_inflight=summarizer_workers
        )
        
        self._shutdown = False
        self._lock = threading.Lock()
    
    def _register_resources(self):
        """注册所有需要清理的资源"""
        # 注意：不注册线程池到 CleanupRegistry，因为它们由 shutdown() 直接管理
        # 这样可以避免重复清理的警告
        pass
    
    # ==================== 订阅抓取 ====================
    
    def fetch_subscriptions_parallel(
        self,
        subscriptions: List[Dict[str, Any]],
        fetch_func: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
        days_limit: int = 0,
        target_name: Optional[str] = None,
        timeout_per_fetch: float = 60.0,
        use_backpressure: bool = True
    ) -> Dict[str, Any]:
        """
        并行抓取多个订阅源
        
        Args:
            subscriptions: 订阅源列表
            fetch_func: 抓取函数，接收订阅配置返回内容列表
            days_limit: 日期限制（天）
            target_name: 目标订阅名称（筛选）
            timeout_per_fetch: 每个订阅源的超时时间
            use_backpressure: 是否使用背压控制
            
        Returns:
            {
                'items': List[Dict],  # 所有抓取到的内容
                'stats': Dict,        # 统计信息
                'errors': List        # 错误列表
            }
        """
        # 筛选订阅源
        if target_name:
            subscriptions = [s for s in subscriptions if s.get('name') == target_name]
        
        if not subscriptions:
            return {'items': [], 'stats': {'success': 0, 'error': 0}, 'errors': []}
        
        all_items = []
        errors = []
        
        def on_result(sub, result):
            """成功回调"""
            if isinstance(result, list):
                all_items.extend(result)
            logging.info(f"Fetched {len(result) if isinstance(result, list) else 0} items from {sub.get('name')}")
        
        def on_error(sub, error):
            """错误回调"""
            errors.append({
                'subscription': sub.get('name'),
                'error': str(error)
            })
            logging.error(f"Failed to fetch {sub.get('name')}: {error}")
        
        # 包装抓取函数（添加超时和资源限制）
        def wrapped_fetch(sub):
            # 获取浏览器许可
            if not self.browser_limiter.acquire(timeout=timeout_per_fetch):
                raise TimeoutError(f"Browser resource timeout for {sub.get('name')}")
            
            try:
                # 执行抓取（带超时）
                @timeout(timeout_per_fetch)
                def do_fetch():
                    return fetch_func(sub)
                
                return do_fetch()
            finally:
                self.browser_limiter.release()
        
        if use_backpressure:
            # 使用背压控制
            stats = self.fetcher_backpressure.map_with_backpressure(
                wrapped_fetch,
                subscriptions,
                on_result=on_result,
                on_error=on_error
            )
        else:
            # 使用传统批量提交
            collector = ThreadSafeResultCollector()
            futures = []
            
            for sub in subscriptions:
                future = self.fetcher_pool.submit(wrapped_fetch, sub)
                futures.append((future, sub))
            
            # 等待所有完成
            for future, sub in futures:
                try:
                    result = future.result(timeout=timeout_per_fetch * 2)
                    on_result(sub, result)
                except Exception as e:
                    on_error(sub, e)
            
            stats = {'success': len(subscriptions) - len(errors), 'error': len(errors)}
        
        return {
            'items': all_items,
            'stats': stats,
            'errors': errors
        }
    
    def fetch_subscriptions_streaming(
        self,
        subscriptions: List[Dict[str, Any]],
        fetch_func: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
        timeout_per_fetch: float = 60.0
    ) -> Iterator[Dict[str, Any]]:
        """
        流式抓取订阅源 - O(1) 内存
        
        使用方式:
            for item in cm.fetch_subscriptions_streaming(...):
                process(item)  # 立即处理，无需等待全部完成
        
        Yields:
            {'type': 'item', 'data': {...}} 或
            {'type': 'error', 'source': ..., 'error': ...}
        """
        collector = StreamingResultCollector(maxsize=self.streaming_queue_size)
        
        def producer(sub):
            """生产者 - 抓取并放入队列"""
            try:
                if not self.browser_limiter.acquire(timeout=timeout_per_fetch):
                    raise TimeoutError("Browser resource timeout")
                
                try:
                    @timeout(timeout_per_fetch)
                    def do_fetch():
                        return fetch_func(sub)
                    
                    items = do_fetch()
                    
                    # 逐个放入队列（流式）
                    if isinstance(items, list):
                        for item in items:
                            collector.put_success(sub, item)
                    else:
                        collector.put_success(sub, items)
                        
                finally:
                    self.browser_limiter.release()
                    
            except Exception as e:
                collector.put_error(sub, e)
        
        # 启动生产者线程
        futures = []
        for sub in subscriptions:
            future = self.fetcher_pool.submit(producer, sub)
            futures.append(future)
        
        # 等待所有完成的线程
        def wait_and_signal():
            wait(futures)
            collector.mark_completed()
        
        threading.Thread(target=wait_and_signal, daemon=True).start()
        
        # 流式返回结果
        yield from collector.iterate_results()
    
    # ==================== LLM 摘要 ====================
    
    def summarize_items_parallel(
        self,
        items: List[Dict[str, Any]],
        summarize_func: Callable[[Dict[str, Any]], str],
        timeout_per_item: float = 30.0,
        use_backpressure: bool = True,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        并行生成摘要
        
        Args:
            items: 需要摘要的内容列表
            summarize_func: 摘要函数，接收内容返回摘要文本
            timeout_per_item: 每个项目的超时时间
            use_backpressure: 是否使用背压控制
            max_retries: 最大重试次数
            
        Returns:
            {
                'summaries': Dict[str, str],  # URL -> 摘要
                'stats': Dict,
                'errors': List
            }
        """
        if not items:
            return {'summaries': {}, 'stats': {'success': 0, 'error': 0}, 'errors': []}
        
        summaries = {}
        errors = []
        
        def on_result(item, result):
            """成功回调"""
            url = item.get('url')
            if url:
                summaries[url] = result
            logging.info(f"Summarized: {item.get('title', 'Unknown')[:50]}...")
        
        def on_error(item, error):
            """错误回调"""
            errors.append({
                'url': item.get('url'),
                'title': item.get('title'),
                'error': str(error)
            })
        
        def wrapped_summarize(item):
            """带限流和断路器的摘要函数"""
            # 令牌桶限流
            if not self.api_token_bucket.acquire(timeout=10):
                raise TimeoutError("API rate limit")
            
            # 断路器保护
            def do_summarize():
                return summarize_func(item)
            
            return self.api_circuit_breaker.call(do_summarize)
        
        # 带重试的包装函数
        def summarize_with_retry(item):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return wrapped_summarize(item)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2 ** attempt)  # 指数退避
            raise last_error
        
        if use_backpressure:
            stats = self.summarizer_backpressure.map_with_backpressure(
                summarize_with_retry,
                items,
                on_result=on_result,
                on_error=on_error
            )
        else:
            futures = []
            for item in items:
                future = self.summarizer_pool.submit(summarize_with_retry, item)
                futures.append((future, item))
            
            for future, item in futures:
                try:
                    result = future.result(timeout=timeout_per_item * 2)
                    on_result(item, result)
                except Exception as e:
                    on_error(item, e)
            
            stats = {'success': len(items) - len(errors), 'error': len(errors)}
        
        return {
            'summaries': summaries,
            'stats': stats,
            'errors': errors
        }
    
    # ==================== 批量处理 ====================
    
    def process_batch(
        self,
        items: List[Any],
        process_func: Callable[[List[Any]], Any],
        use_parallel: bool = False
    ) -> List[Any]:
        """
        批量处理数据
        
        Args:
            items: 待处理数据
            process_func: 批量处理函数
            use_parallel: 是否并行处理批次
            
        Returns:
            各批次结果列表
        """
        if use_parallel:
            return self.batch_processor.process_batches_parallel(
                items, process_func, self.summarizer_pool
            )
        else:
            return self.batch_processor.process_batches(items, process_func)
    
    # ==================== 上下文管理 ====================
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口 - 自动清理"""
        self.shutdown()
    
    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """
        优雅关闭所有资源
        
        Args:
            wait: 是否等待任务完成
            timeout: 等待超时时间
        """
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        
        logging.info("Shutting down ConcurrencyManager...")
        
        # 1. 停止接受新任务
        if wait:
            # 等待现有任务完成
            self.fetcher_pool.shutdown(wait=True)
            self.summarizer_pool.shutdown(wait=True)
        else:
            self.fetcher_pool.shutdown(wait=False)
            self.summarizer_pool.shutdown(wait=False)
        
        # 2. 执行注册表清理
        remaining, errors = self.cleanup_registry.emergency_cleanup()
        
        # 3. 强制垃圾回收
        gc.collect()
        
        logging.info(f"Shutdown complete. Remaining: {remaining}, Errors: {len(errors)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        return {
            'browser_limiter': {
                'max': self.browser_limiter.max_resources,
                'active': self.browser_limiter.get_active_count()
            },
            'api_circuit_breaker': {
                'state': self.api_circuit_breaker.get_state()
            },
            'cleanup_registry': self.cleanup_registry.get_stats()
        }
