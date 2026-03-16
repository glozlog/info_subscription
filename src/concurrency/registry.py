"""
清理注册表模块 - 统一管理资源清理，防止内存泄漏
"""
import atexit
import gc
import weakref
import logging
import threading
from typing import Callable, Any, List, Tuple


class CleanupRegistry:
    """
    全局清理注册表 - 确保所有资源都被正确释放
    
    使用单例模式，在程序退出时自动执行清理
    
    时间复杂度:
    - register(): O(1)
    - emergency_cleanup(): O(k log k)，k=注册的资源数
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._resources = []
                    cls._instance._setup_atexit()
        return cls._instance
    
    def _setup_atexit(self):
        """设置程序退出时的清理钩子"""
        atexit.register(self._atexit_cleanup)
    
    def register(
        self, 
        resource_type: str, 
        obj: Any, 
        cleanup_method: Callable[[Any], None],
        priority: int = 0
    ):
        """
        注册需要清理的资源
        
        Args:
            resource_type: 资源类型标识（如 'thread_pool', 'browser'）
            obj: 资源对象
            cleanup_method: 清理函数，接收 obj 作为参数
            priority: 清理优先级，数字越小越早清理（0=最高优先级）
        """
        entry = {
            'type': resource_type,
            'obj_ref': weakref.ref(obj),
            'cleanup': cleanup_method,
            'priority': priority,
            'registered_at': time.time()
        }
        self._resources.append(entry)
    
    def unregister(self, obj: Any):
        """手动注销资源（资源已被提前清理时）"""
        self._resources = [
            e for e in self._resources 
            if e['obj_ref']() is not None and e['obj_ref']() is not obj
        ]
    
    def emergency_cleanup(self):
        """
        紧急清理所有资源 - 按优先级顺序执行
        
        优先级顺序（数字越小越早）:
        0: 浏览器实例、网络连接（需要立即释放）
        1: 线程池（等待任务完成）
        2: 文件句柄、数据库连接
        3: 缓存对象
        """
        # 按优先级排序
        sorted_resources = sorted(self._resources, key=lambda x: x['priority'])
        
        cleanup_errors = []
        
        for entry in sorted_resources:
            obj = entry['obj_ref']()
            if obj is not None:
                try:
                    entry['cleanup'](obj)
                    logging.debug(f"Cleaned up {entry['type']}")
                except Exception as e:
                    cleanup_errors.append((entry['type'], str(e)))
        
        # 强制垃圾回收
        gc.collect()
        
        # 报告未清理的资源
        remaining = [e for e in self._resources if e['obj_ref']() is not None]
        if remaining:
            logging.warning(f"{len(remaining)} resources still alive after cleanup")
            for e in remaining:
                logging.warning(f"  - {e['type']} (priority={e['priority']})")
        
        if cleanup_errors:
            logging.error(f"Cleanup errors: {cleanup_errors}")
        
        return len(remaining), cleanup_errors
    
    def _atexit_cleanup(self):
        """程序退出时的清理钩子"""
        logging.info("Running atexit cleanup...")
        remaining, errors = self.emergency_cleanup()
        if remaining == 0 and not errors:
            logging.info("Cleanup completed successfully")
        else:
            logging.warning(f"Cleanup completed with {remaining} remaining, {len(errors)} errors")
    
    def get_stats(self) -> dict:
        """获取注册表统计信息"""
        total = len(self._resources)
        alive = sum(1 for e in self._resources if e['obj_ref']() is not None)
        by_priority = {}
        for e in self._resources:
            p = e['priority']
            by_priority[p] = by_priority.get(p, 0) + 1
        
        return {
            'total_registered': total,
            'still_alive': alive,
            'by_priority': by_priority
        }


# 导入 time 模块（放在文件末尾避免循环导入）
import time
