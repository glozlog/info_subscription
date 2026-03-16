"""
结果收集器模块 - 线程安全的结果收集，支持流式处理
"""
import threading
import queue
from typing import List, Dict, Any, Optional, Iterator, Callable
from concurrent.futures import Future, wait, FIRST_COMPLETED


class ThreadSafeResultCollector:
    """
    线程安全的结果收集器 - 全量存储模式
    
    时间复杂度:
    - add_success/add_error: O(1)
    - get_results: O(n)
    - 空间: O(n)
    
    适用于结果量较小的场景
    """
    
    def __init__(self):
        self._successes: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._success_count = 0
        self._error_count = 0
    
    def add_success(self, source: Any, result: Any):
        """添加成功结果"""
        with self._lock:
            self._successes.append({
                'source': source,
                'result': result,
                'index': self._success_count
            })
            self._success_count += 1
    
    def add_error(self, source: Any, error: Exception):
        """添加错误结果"""
        with self._lock:
            self._errors.append({
                'source': source,
                'error': str(error),
                'error_type': type(error).__name__,
                'index': self._error_count
            })
            self._error_count += 1
    
    def get_successes(self) -> List[Dict[str, Any]]:
        """获取所有成功结果"""
        with self._lock:
            return self._successes.copy()
    
    def get_errors(self) -> List[Dict[str, Any]]:
        """获取所有错误结果"""
        with self._lock:
            return self._errors.copy()
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {
                'success_count': self._success_count,
                'error_count': self._error_count,
                'total': self._success_count + self._error_count
            }


class StreamingResultCollector:
    """
    流式结果收集器 - 完成一个处理一个，O(1) 内存
    
    使用有界队列实现背压控制，适用于大数据量场景
    
    时间复杂度:
    - put: O(1) 平均，队列满时阻塞
    - iterate_results: O(1) 每元素
    - 空间: O(queue_size)，与数据量无关
    """
    
    def __init__(self, maxsize: int = 100):
        """
        Args:
            maxsize: 队列最大容量，控制内存使用和背压
        """
        self._queue = queue.Queue(maxsize=maxsize)
        self._completed = threading.Event()
        self._error_count = 0
        self._success_count = 0
        self._lock = threading.Lock()
    
    def put_success(self, source: Any, result: Any, block: bool = True, timeout: Optional[float] = None):
        """
        放入成功结果
        
        Args:
            block: 队列满时是否阻塞
            timeout: 阻塞超时时间
        """
        item = {
            'type': 'success',
            'source': source,
            'result': result
        }
        self._queue.put(item, block=block, timeout=timeout)
        with self._lock:
            self._success_count += 1
    
    def put_error(self, source: Any, error: Exception, block: bool = True, timeout: Optional[float] = None):
        """放入错误结果"""
        item = {
            'type': 'error',
            'source': source,
            'error': str(error),
            'error_type': type(error).__name__
        }
        self._queue.put(item, block=block, timeout=timeout)
        with self._lock:
            self._error_count += 1
    
    def mark_completed(self):
        """标记所有任务已完成"""
        self._completed.set()
    
    def iterate_results(self, timeout: Optional[float] = 1.0) -> Iterator[Dict[str, Any]]:
        """
        流式迭代结果
        
        使用方式:
            for result in collector.iterate_results():
                process(result)
        
        Args:
            timeout: 每次获取的超时时间
        """
        while True:
            try:
                item = self._queue.get(timeout=timeout)
                yield item
            except queue.Empty:
                # 检查是否已完成且队列为空
                if self._completed.is_set() and self._queue.empty():
                    break
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {
                'success_count': self._success_count,
                'error_count': self._error_count,
                'queue_size': self._queue.qsize(),
                'completed': self._completed.is_set()
            }


class BackpressureExecutor:
    """
    带背压控制的执行器 - 控制内存使用，与数据量无关
    
    特性:
    - 只保持 max_inflight 个并发任务
    - 完成一个，提交一个
    - 内存占用: O(max_inflight)
    """
    
    def __init__(self, executor, max_inflight: int = 20):
        """
        Args:
            executor: ThreadPoolExecutor 实例
            max_inflight: 最大并发任务数
        """
        self.executor = executor
        self.max_inflight = max_inflight
    
    def map_with_backpressure(
        self, 
        func: Callable, 
        items: List[Any],
        on_result: Optional[Callable[[Any, Any], None]] = None,
        on_error: Optional[Callable[[Any, Exception], None]] = None
    ) -> Dict[str, int]:
        """
        带背压的批量执行
        
        Args:
            func: 执行函数
            items: 输入数据列表
            on_result: 成功回调 (item, result) -> None
            on_error: 错误回调 (item, error) -> None
            
        Returns:
            统计信息 {'success': n, 'error': n}
        """
        item_iterator = iter(items)
        inflight: Dict[Future, Any] = {}
        stats = {'success': 0, 'error': 0}
        
        # 初始提交一批任务
        for _ in range(min(self.max_inflight, len(items))):
            self._submit_next(item_iterator, func, inflight)
        
        # 完成一个，提交一个
        while inflight:
            done, _ = wait(inflight.keys(), return_when=FIRST_COMPLETED)
            
            for future in done:
                item = inflight.pop(future)
                
                try:
                    result = future.result()
                    stats['success'] += 1
                    if on_result:
                        on_result(item, result)
                except Exception as e:
                    stats['error'] += 1
                    if on_error:
                        on_error(item, e)
                
                # 提交新任务保持并发度
                self._submit_next(item_iterator, func, inflight)
        
        return stats
    
    def _submit_next(self, iterator, func, inflight: Dict[Future, Any]):
        """提交下一个任务"""
        try:
            item = next(iterator)
            future = self.executor.submit(func, item)
            inflight[future] = item
        except StopIteration:
            pass


class BatchProcessor:
    """
    批量处理器 - 将数据分批处理，减少操作次数
    
    时间复杂度:
    - 处理 n 个元素: O(n/batch_size) 次批量操作
    """
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
    
    def process_batches(
        self, 
        items: List[Any], 
        process_func: Callable[[List[Any]], Any]
    ) -> List[Any]:
        """
        批量处理数据
        
        Args:
            items: 待处理数据
            process_func: 批量处理函数，接收 List[Any] 返回 Any
            
        Returns:
            各批次的处理结果列表
        """
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            result = process_func(batch)
            results.append(result)
        return results
    
    def process_batches_parallel(
        self,
        items: List[Any],
        process_func: Callable[[List[Any]], Any],
        executor,
        max_concurrent_batches: int = 3
    ) -> List[Any]:
        """
        并行批量处理
        
        适用于批次之间无依赖的场景
        """
        batches = [items[i:i + self.batch_size] for i in range(0, len(items), self.batch_size)]
        
        futures = []
        for batch in batches[:max_concurrent_batches]:
            future = executor.submit(process_func, batch)
            futures.append(future)
        
        results = []
        for future in futures:
            results.append(future.result())
        
        return results
