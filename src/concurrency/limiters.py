"""
资源限制器模块 - 令牌桶限流、断路器、资源信号量
"""
import threading
import time
import functools
from typing import Optional, Callable, Any


class TokenBucket:
    """
    令牌桶限流器 - 控制 API 调用速率
    
    时间复杂度:
    - acquire(): O(1) 平均, 最坏 O(wait_time)
    - acquire_batch(): O(1)
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: 每秒产生的令牌数
            capacity: 桶的最大容量
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.time()
        self._lock = threading.Lock()
    
    def _add_tokens(self):
        """根据时间流逝添加令牌"""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
    
    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        申请一个令牌
        
        Returns:
            True: 申请成功
            False: 申请失败（非阻塞模式）或超时
        """
        with self._lock:
            self._add_tokens()
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            
            if not blocking:
                return False
            
            # 计算需要等待的时间
            wait_time = (1 - self.tokens) / self.rate
            if timeout is not None and wait_time > timeout:
                return False
        
        # 在锁外等待
        if blocking:
            time.sleep(wait_time)
            return self.acquire(blocking=True, timeout=None)
        return False
    
    def acquire_batch(self, n: int, timeout: Optional[float] = None) -> int:
        """
        批量申请令牌 - O(1) 锁操作
        
        Args:
            n: 需要的令牌数
            timeout: 等待超时时间
            
        Returns:
            实际获得的令牌数（可能少于请求的）
        """
        with self._lock:
            self._add_tokens()
            granted = min(n, int(self.tokens))
            self.tokens -= granted
            return granted
    
    def try_acquire(self) -> bool:
        """非阻塞申请一个令牌"""
        return self.acquire(blocking=False)


class CircuitBreaker:
    """
    断路器 - 快速失败机制，防止级联故障
    
    状态转换:
    CLOSED -> (失败次数达到阈值) -> OPEN -> (恢复超时) -> HALF_OPEN -> (成功) -> CLOSED
                                      -> (失败) -> OPEN
    """
    
    STATE_CLOSED = 'CLOSED'      # 正常状态，允许请求
    STATE_OPEN = 'OPEN'          # 断开状态，拒绝请求
    STATE_HALF_OPEN = 'HALF_OPEN'  # 半开状态，试探性允许请求
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        """
        Args:
            failure_threshold: 触发断路的连续失败次数
            recovery_timeout: 从 OPEN 到 HALF_OPEN 的等待时间（秒）
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = self.STATE_CLOSED
        self._lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        在断路器保护下执行函数
        
        Raises:
            CircuitBreakerOpenError: 断路器处于 OPEN 状态
            Exception: 被保护函数抛出的异常
        """
        with self._lock:
            if self.state == self.STATE_OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = self.STATE_HALF_OPEN
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """成功时重置状态"""
        with self._lock:
            self.failure_count = 0
            self.state = self.STATE_CLOSED
    
    def _on_failure(self):
        """失败时增加计数，可能触发断路"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = self.STATE_OPEN
    
    def get_state(self) -> str:
        """获取当前状态"""
        with self._lock:
            return self.state


class CircuitBreakerOpenError(Exception):
    """断路器打开异常"""
    pass


class ResourceLimiter:
    """
    资源限制器 - 管理重资源（如浏览器实例）的并发访问
    
    使用信号量控制最大并发数，并提供超时机制
    """
    
    def __init__(self, max_resources: int, name: str = "resource"):
        """
        Args:
            max_resources: 最大并发资源数
            name: 资源名称（用于日志）
        """
        self.max_resources = max_resources
        self.name = name
        self.semaphore = threading.Semaphore(max_resources)
        self._active_count = 0
        self._lock = threading.Lock()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        获取资源许可
        
        Args:
            timeout: 等待超时时间（秒），None 表示无限等待
            
        Returns:
            True: 获取成功
            False: 获取失败（超时）
        """
        result = self.semaphore.acquire(timeout=timeout)
        if result:
            with self._lock:
                self._active_count += 1
        return result
    
    def release(self):
        """释放资源许可"""
        with self._lock:
            self._active_count -= 1
        self.semaphore.release()
    
    def get_active_count(self) -> int:
        """获取当前活跃资源数"""
        with self._lock:
            return self._active_count
    
    def __enter__(self):
        """上下文管理器入口"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()


def timeout(seconds: float):
    """
    超时装饰器 - 在指定时间内完成函数执行
    
    注意：此装饰器会创建新线程，适用于 I/O 绑定操作
    对于 CPU 绑定操作，请使用 multiprocessing
    
    Args:
        seconds: 超时时间（秒）
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            result = [None]
            exception = [None]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=seconds)
            
            if thread.is_alive():
                raise TimeoutError(f"Function {func.__name__} timed out after {seconds}s")
            if exception[0]:
                raise exception[0]
            return result[0]
        return wrapper
    return decorator
