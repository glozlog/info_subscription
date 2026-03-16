import sqlite3
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union
import time


class DateTimeUtil:
    """
    日期时间标准化工具类
    
    统一将所有日期格式转换为 ISO 8601 格式: YYYY-MM-DD HH:MM:SS
    """
    
    # 支持的日期格式列表
    DATE_FORMATS = [
        "%Y-%m-%d %H:%M:%S",      # 2024-01-15 14:30:00
        "%Y-%m-%dT%H:%M:%S",      # 2024-01-15T14:30:00
        "%Y-%m-%d %H:%M",         # 2024-01-15 14:30
        "%Y-%m-%d",               # 2024-01-15
        "%Y/%m/%d %H:%M:%S",      # 2024/01/15 14:30:00
        "%Y/%m/%d",               # 2024/01/15
        "%d-%m-%Y %H:%M:%S",      # 15-01-2024 14:30:00
        "%d/%m/%Y %H:%M:%S",      # 15/01/2024 14:30:00
        "%a, %d %b %Y %H:%M:%S %Z",  # RFC 2822: Mon, 15 Jan 2024 14:30:00 GMT
        "%a, %d %b %Y %H:%M:%S GMT", # RFC 2822 variant
    ]
    
    # 相对时间映射
    RELATIVE_TIME_MAP = {
        '刚刚': 0,
        '分钟前': 0,
        '小时前': 0,
        '今天': 0,
        '昨天': 1,
        '前天': 2,
    }
    
    @classmethod
    def standardize(cls, date_input: Union[str, datetime, None], default_now: bool = True) -> str:
        """
        将各种日期格式标准化为 YYYY-MM-DD HH:MM:SS
        
        Args:
            date_input: 输入日期（字符串或 datetime 对象）
            default_now: 如果解析失败，是否返回当前时间
            
        Returns:
            标准化后的日期字符串 YYYY-MM-DD HH:MM:SS
        """
        if date_input is None:
            return cls._get_default(default_now)
        
        # 如果已经是 datetime 对象
        if isinstance(date_input, datetime):
            return cls._format_datetime(date_input)
        
        # 转换为字符串
        date_str = str(date_input).strip()
        
        if not date_str:
            return cls._get_default(default_now)
        
        # 尝试直接解析已知格式
        result = cls._try_parse_formats(date_str)
        if result:
            return result
        
        # 尝试解析相对时间
        result = cls._try_parse_relative(date_str)
        if result:
            return result
        
        # 尝试解析中文日期格式
        result = cls._try_parse_chinese(date_str)
        if result:
            return result
        
        # 尝试提取日期部分
        result = cls._try_extract_date(date_str)
        if result:
            return result
        
        return cls._get_default(default_now)
    
    @classmethod
    def _try_parse_formats(cls, date_str: str) -> Optional[str]:
        """尝试解析已知格式"""
        # 处理带时区的 RFC 2822 格式
        if 'GMT' in date_str or 'UTC' in date_str or any(x in date_str for x in ['+', '-']):
            try:
                # 使用 email.utils 解析 RFC 2822
                import email.utils
                parsed = email.utils.parsedate_to_datetime(date_str)
                if parsed:
                    # 转换为本地时间
                    local = parsed.astimezone(timezone(timedelta(hours=8)))
                    return cls._format_datetime(local)
            except:
                pass
        
        # 尝试各种格式 - 优先尝试完整格式（包含时间）
        # 按长度降序排列，优先匹配更具体的格式
        sorted_formats = sorted(cls.DATE_FORMATS, key=lambda x: len(x), reverse=True)
        
        for fmt in sorted_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return cls._format_datetime(dt)
            except ValueError:
                continue
        
        return None
    
    @classmethod
    def _try_parse_relative(cls, date_str: str) -> Optional[str]:
        """解析相对时间（如：昨天、2小时前）"""
        now = datetime.now()
        
        # 检查相对时间关键词
        for keyword, days_offset in cls.RELATIVE_TIME_MAP.items():
            if keyword in date_str:
                target_date = now - timedelta(days=days_offset)
                return cls._format_datetime(target_date)
        
        # 匹配 "X天前"
        match = re.search(r'(\d+)\s*天前', date_str)
        if match:
            days = int(match.group(1))
            target_date = now - timedelta(days=days)
            return cls._format_datetime(target_date)
        
        # 匹配 "X小时前"
        match = re.search(r'(\d+)\s*小时前', date_str)
        if match:
            hours = int(match.group(1))
            target_date = now - timedelta(hours=hours)
            return cls._format_datetime(target_date)
        
        # 匹配 "X分钟前"
        match = re.search(r'(\d+)\s*分钟前', date_str)
        if match:
            minutes = int(match.group(1))
            target_date = now - timedelta(minutes=minutes)
            return cls._format_datetime(target_date)
        
        return None
    
    @classmethod
    def _try_parse_chinese(cls, date_str: str) -> Optional[str]:
        """解析中文日期格式（如：2024年1月15日 14:30）"""
        # 匹配 "2024年1月15日" 或 "2024年01月15日"
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            year, month, day = match.groups()
            
            # 尝试提取时间
            time_match = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', date_str)
            if time_match:
                hour = time_match.group(1)
                minute = time_match.group(2)
                second = time_match.group(3) or '00'
            else:
                hour, minute, second = '00', '00', '00'
            
            try:
                dt = datetime(int(year), int(month), int(day), 
                            int(hour), int(minute), int(second))
                return cls._format_datetime(dt)
            except ValueError:
                pass
        
        # 匹配 "1月15日"（当年）
        match = re.search(r'(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            month, day = match.groups()
            year = datetime.now().year
            
            # 提取时间
            time_match = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', date_str)
            if time_match:
                hour = time_match.group(1)
                minute = time_match.group(2)
                second = time_match.group(3) or '00'
            else:
                hour, minute, second = '00', '00', '00'
            
            try:
                dt = datetime(year, int(month), int(day),
                            int(hour), int(minute), int(second))
                # 如果日期在未来，可能是去年的
                if dt > datetime.now() + timedelta(days=1):
                    dt = dt.replace(year=year-1)
                return cls._format_datetime(dt)
            except ValueError:
                pass
        
        return None
    
    @classmethod
    def _try_extract_date(cls, date_str: str) -> Optional[str]:
        """尝试从字符串中提取日期部分"""
        # 匹配 YYYY-MM-DD 格式
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return cls._format_datetime(dt)
            except ValueError:
                pass
        
        # 匹配 YYYY/MM/DD 格式
        match = re.search(r'(\d{4})/(\d{2})/(\d{2})', date_str)
        if match:
            year, month, day = match.groups()
            try:
                dt = datetime(int(year), int(month), int(day))
                return cls._format_datetime(dt)
            except ValueError:
                pass
        
        return None
    
    @classmethod
    def _format_datetime(cls, dt: datetime) -> str:
        """格式化为标准字符串"""
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    @classmethod
    def _get_default(cls, use_now: bool) -> str:
        """获取默认值"""
        if use_now:
            return cls._format_datetime(datetime.now())
        return "1970-01-01 00:00:00"
    
    @classmethod
    def to_date_only(cls, standardized_date: str) -> str:
        """从标准化日期提取日期部分"""
        return standardized_date[:10]
    
    @classmethod
    def parse_to_datetime(cls, date_str: str) -> Optional[datetime]:
        """将标准化日期字符串解析为 datetime 对象"""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


class DatabaseManager:
    """
    Manages SQLite database for storing articles and summaries.
    
    使用线程本地存储实现连接池复用，减少频繁创建/关闭连接的开销。
    每个线程维护自己的数据库连接，线程结束时自动清理。
    """
    
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        # 线程本地存储 - 每个线程一个连接
        self._local = threading.local()
        # 全局锁保护连接统计
        self._lock = threading.Lock()
        self._connection_count = 0
        self._init_db()
        
    def _get_connection(self) -> sqlite3.Connection:
        """
        获取线程本地的数据库连接（连接池模式）。
        
        如果当前线程没有连接，则创建新连接。
        连接在线程结束时自动关闭。
        
        性能优化:
        - WAL模式: 写性能提升 2-5x，读不阻塞写
        - 同步模式: NORMAL 平衡性能与安全性
        - 缓存大小: 增加页面缓存减少磁盘IO
        - 外键: 启用数据完整性检查
        
        Returns:
            sqlite3.Connection: 数据库连接
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.connection.row_factory = sqlite3.Row
            with self._lock:
                self._connection_count += 1
            
            # 性能优化配置
            cursor = self._local.connection.cursor()
            # WAL模式: 提升并发写入性能，读不阻塞写
            cursor.execute("PRAGMA journal_mode = WAL")
            # 同步模式: NORMAL 在性能和安全性间取得平衡
            cursor.execute("PRAGMA synchronous = NORMAL")
            # 增加缓存页面数 (约 4MB 缓存)
            cursor.execute("PRAGMA cache_size = -4000")
            # 启用外键支持
            cursor.execute("PRAGMA foreign_keys = ON")
            
        return self._local.connection
    
    def _close_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
            with self._lock:
                self._connection_count -= 1
    
    @contextmanager
    def _transaction(self):
        """
        事务上下文管理器 - 自动处理提交/回滚。
        
        使用方式:
            with self._transaction() as conn:
                conn.execute(...)
                # 自动提交或回滚
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def close_all_connections(self):
        """关闭所有连接（主要用于测试或程序退出）"""
        self._close_connection()
        
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._lock:
            return {
                'active_connections': self._connection_count,
                'current_thread_has_connection': hasattr(self._local, 'connection') and self._local.connection is not None
            }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        获取数据库性能统计
        
        Returns:
            {
                'page_count': 总页数,
                'page_size': 页面大小,
                'wal_mode': 是否启用WAL模式,
                'journal_mode': 日志模式,
                'cache_size': 缓存大小,
                'synchronous': 同步模式
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        try:
            # 数据库文件信息
            cursor.execute("PRAGMA page_count")
            stats['page_count'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA page_size")
            stats['page_size'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA journal_mode")
            stats['journal_mode'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA synchronous")
            stats['synchronous'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA cache_size")
            stats['cache_size'] = cursor.fetchone()[0]
            
            # WAL模式检查
            cursor.execute("PRAGMA wal_checkpoint")
            wal_result = cursor.fetchone()
            stats['wal_checkpoint'] = wal_result[0] if wal_result else None
            
        except Exception as e:
            stats['error'] = str(e)
        
        return stats
        
    def _init_db(self):
        """Initialize database tables."""
        # 使用新的连接池方式初始化
        with self._transaction() as conn:
            cursor = conn.cursor()
        
            # Articles table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                content TEXT,
                subtitle TEXT,
                author TEXT,
                platform TEXT,
                category TEXT,
                publish_date TEXT,
                video_url TEXT,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Stats cache table - 统计缓存表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats_cache (
                key TEXT PRIMARY KEY,
                value INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
        
        # 创建索引（单独处理，确保即使表已存在也能创建索引）
        self._create_indexes()
        
        # 迁移现有数据的日期格式
        self._migrate_dates()
        
        # 初始化统计缓存
        self._init_stats_cache()
        
    def _create_indexes(self):
        """创建数据库索引（如果不存在）"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            
            # 索引定义
            indexes = [
                ('idx_publish_date', 'CREATE INDEX IF NOT EXISTS idx_publish_date ON articles(publish_date DESC)'),
                ('idx_author', 'CREATE INDEX IF NOT EXISTS idx_author ON articles(author)'),
                ('idx_platform', 'CREATE INDEX IF NOT EXISTS idx_platform ON articles(platform)'),
                ('idx_category', 'CREATE INDEX IF NOT EXISTS idx_category ON articles(category)'),
                ('idx_author_platform', 'CREATE INDEX IF NOT EXISTS idx_author_platform ON articles(author, platform)'),
            ]
            
            created_count = 0
            for index_name, create_sql in indexes:
                try:
                    cursor.execute(create_sql)
                    created_count += 1
                except sqlite3.OperationalError as e:
                    # 索引已存在或其他错误
                    if 'already exists' not in str(e).lower():
                        print(f"Warning: Failed to create index {index_name}: {e}")
            
        if created_count > 0:
            print(f"Created {created_count} database indexes")
        
    def _migrate_dates(self):
        """
        将数据库中现有的非标准日期格式转换为标准格式
        这是一个一次性迁移操作，后续会自动处理新数据
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 查找所有日期格式不正确的记录
            # 标准格式是 YYYY-MM-DD HH:MM:SS（19个字符）
            cursor.execute('''
                SELECT url, publish_date FROM articles 
                WHERE publish_date IS NOT NULL 
                AND length(publish_date) != 19
            ''')
            
            rows = cursor.fetchall()
            if not rows:
                return
            
            print(f"Migrating {len(rows)} articles to standardized date format...")
            
            migrated = 0
            for url, old_date in rows:
                try:
                    # 标准化日期
                    new_date = DateTimeUtil.standardize(old_date)
                    
                    # 更新记录
                    cursor.execute('''
                        UPDATE articles 
                        SET publish_date = ? 
                        WHERE url = ?
                    ''', (new_date, url))
                    
                    migrated += 1
                    
                    # 每 100 条提交一次
                    if migrated % 100 == 0:
                        conn.commit()
                        print(f"  Migrated {migrated}/{len(rows)}...")
                        
                except Exception as e:
                    print(f"  Failed to migrate {url}: {e}")
                    continue
            
            conn.commit()
            print(f"Date migration completed: {migrated} articles updated")
            
        except Exception as e:
            print(f"Error during date migration: {e}")
        # 注意：连接池模式下不关闭连接，由线程结束时自动清理
        
    def save_article(self, item: Dict[str, Any], summary: Optional[str] = None) -> bool:
        """
        Save or update an article. 
        If summary is provided, it updates the summary.
        If summary is None, it keeps existing summary if available.
        
        日期会被自动标准化为 YYYY-MM-DD HH:MM:SS 格式
        
        使用连接池复用数据库连接。
        """
        url = item.get('url')
        if not url:
            return False
            
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                
                # Check if exists to preserve summary if not provided
                cursor.execute('SELECT summary FROM articles WHERE url = ?', (url,))
                row = cursor.fetchone()
                existing_summary = row[0] if row else None
                
                final_summary = summary if summary is not None else existing_summary
                
                # 标准化日期
                raw_date = item.get('publish_date')
                standardized_date = DateTimeUtil.standardize(raw_date)
                
                cursor.execute('''
                INSERT OR REPLACE INTO articles (
                    url, title, content, subtitle, author, platform, category, 
                    publish_date, video_url, summary, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    url,
                    item.get('title'),
                    item.get('content'),
                    item.get('subtitle'),
                    item.get('author'),
                    item.get('platform'),
                    item.get('category'),
                    standardized_date,
                    item.get('video_url'),
                    final_summary
                ))
            return True
        except Exception as e:
            print(f"Error saving to DB: {e}")
            return False
            
    def update_summary(self, url: str, summary: str) -> bool:
        """Update only the summary for a specific article."""
        if not url:
            return False
            
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE articles 
                SET summary = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE url = ?
                ''', (summary, url))
            return True
        except Exception as e:
            print(f"Error updating summary: {e}")
            return False

    def update_content(self, url: str, content: str) -> bool:
        """Update only the content for a specific article."""
        if not url:
            return False
            
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE articles 
                SET content = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE url = ?
                ''', (content, url))
            return True
        except Exception as e:
            print(f"Error updating content: {e}")
            return False
    def get_article(self, url: str) -> Optional[Dict[str, Any]]:
        """Get article by URL."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM articles WHERE url = ?', (url,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
        
    def get_all_articles(self, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all articles sorted by publish date desc with pagination."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM articles ORDER BY publish_date DESC LIMIT ? OFFSET ?', (limit, offset))
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
        
    def count_articles(self, use_cache: bool = True, cache_ttl: int = 60) -> int:
        """
        Get total count of articles.
        
        Args:
            use_cache: 是否使用缓存
            cache_ttl: 缓存有效期（秒）
            
        Big O: O(1) 缓存命中时，O(n) 缓存失效时
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if use_cache:
            # 尝试从缓存读取
            cursor.execute('''
                SELECT value, updated_at FROM stats_cache 
                WHERE key = 'total_count'
                AND updated_at > datetime('now', '-{} seconds')
            '''.format(cache_ttl))
            
            row = cursor.fetchone()
            if row:
                return row[0]
        
        # 缓存失效或不用缓存，重新计算
        cursor.execute('SELECT COUNT(*) FROM articles')
        count = cursor.fetchone()[0]
        
        # 更新缓存
        cursor.execute('''
            INSERT OR REPLACE INTO stats_cache (key, value, updated_at)
            VALUES ('total_count', ?, CURRENT_TIMESTAMP)
        ''', (count,))
        
        conn.commit()
        return count
    
    def _init_stats_cache(self):
        """初始化统计缓存"""
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                
                # 预计算并缓存常用统计
                # 总文章数
                cursor.execute('SELECT COUNT(*) FROM articles')
                total = cursor.fetchone()[0]
                cursor.execute('''
                    INSERT OR REPLACE INTO stats_cache (key, value, updated_at)
                    VALUES ('total_count', ?, CURRENT_TIMESTAMP)
                ''', (total,))
                
                # 作者数
                cursor.execute('SELECT COUNT(DISTINCT author) FROM articles')
                author_count = cursor.fetchone()[0]
                cursor.execute('''
                    INSERT OR REPLACE INTO stats_cache (key, value, updated_at)
                    VALUES ('author_count', ?, CURRENT_TIMESTAMP)
                ''', (author_count,))
                
        except Exception as e:
            print(f"Error initializing stats cache: {e}")
    
    def get_author_count(self, use_cache: bool = True, cache_ttl: int = 60) -> int:
        """
        获取作者数量（带缓存）
        
        Big O: O(1) 缓存命中时
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if use_cache:
            cursor.execute('''
                SELECT value, updated_at FROM stats_cache 
                WHERE key = 'author_count'
                AND updated_at > datetime('now', '-{} seconds')
            '''.format(cache_ttl))
            
            row = cursor.fetchone()
            if row:
                return row[0]
        
        # 重新计算
        cursor.execute('SELECT COUNT(DISTINCT author) FROM articles')
        count = cursor.fetchone()[0]
        
        cursor.execute('''
            INSERT OR REPLACE INTO stats_cache (key, value, updated_at)
            VALUES ('author_count', ?, CURRENT_TIMESTAMP)
        ''', (count,))
        
        conn.commit()
        return count
    
    def invalidate_stats_cache(self):
        """使统计缓存失效（在数据变更后调用）"""
        with self._transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stats_cache")

    def delete_article(self, url: str) -> bool:
        """Delete an article by URL."""
        if not url:
            return False
        try:
            with self._transaction() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM articles WHERE url = ?', (url,))
            return True
        except Exception as e:
            print(f"Error deleting article: {e}")
            return False

    def save_articles_batch(
        self, 
        items: List[Dict[str, Any]], 
        summaries: Optional[Dict[str, str]] = None,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """
        批量保存文章 - O(n/batch) 次数据库操作
        
        相比单条保存，批量操作可减少 90%+ 的数据库连接开销
        
        Args:
            items: 文章列表
            summaries: URL -> 摘要 的字典（可选）
            batch_size: 每批处理数量
            
        Returns:
            {'saved': n, 'errors': n}
        """
        if not items:
            return {'saved': 0, 'errors': 0}
        
        summaries = summaries or {}
        stats = {'saved': 0, 'errors': 0}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 分批处理
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                
                # 准备批量数据
                batch_data = []
                for item in batch:
                    url = item.get('url')
                    if not url:
                        continue
                    
                    # 获取摘要（优先使用传入的 summaries）
                    summary = summaries.get(url)
                    if summary is None:
                        summary = item.get('summary')
                    
                    # 标准化日期
                    raw_date = item.get('publish_date')
                    standardized_date = DateTimeUtil.standardize(raw_date)
                    
                    batch_data.append((
                        url,
                        item.get('title'),
                        item.get('content'),
                        item.get('subtitle'),
                        item.get('author'),
                        item.get('platform'),
                        item.get('category'),
                        standardized_date,
                        item.get('video_url'),
                        summary
                    ))
                
                if not batch_data:
                    continue
                
                # 批量插入/更新
                try:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO articles (
                            url, title, content, subtitle, author, platform, category,
                            publish_date, video_url, summary, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', batch_data)
                    
                    conn.commit()
                    stats['saved'] += len(batch_data)
                    
                except Exception as e:
                    print(f"Error saving batch {i//batch_size}: {e}")
                    stats['errors'] += len(batch_data)
                    
        except Exception as e:
            print(f"Error in batch save: {e}")
        
        return stats

    def update_summaries_batch(
        self,
        url_summary_pairs: List[tuple],
        batch_size: int = 100
    ) -> Dict[str, int]:
        """
        批量更新摘要
        
        Args:
            url_summary_pairs: [(url, summary), ...]
            batch_size: 每批处理数量
            
        Returns:
            {'updated': n, 'errors': n}
        """
        if not url_summary_pairs:
            return {'updated': 0, 'errors': 0}
        
        stats = {'updated': 0, 'errors': 0}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            for i in range(0, len(url_summary_pairs), batch_size):
                batch = url_summary_pairs[i:i + batch_size]
                
                try:
                    cursor.executemany('''
                        UPDATE articles 
                        SET summary = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE url = ?
                    ''', [(summary, url) for url, summary in batch])
                    
                    conn.commit()
                    stats['updated'] += len(batch)
                    
                except Exception as e:
                    print(f"Error updating summary batch {i//batch_size}: {e}")
                    stats['errors'] += len(batch)
                    
        except Exception as e:
            print(f"Error in batch update: {e}")
        
        return stats

    def get_recent_urls(self, days: int = 90) -> set:
        """
        获取最近 N 天的所有 URL - 用于内存去重缓存
        
        时间复杂度: O(n) 一次性加载，之后查询 O(1)
        使用标准化的日期格式，可以利用索引
        
        Args:
            days: 最近多少天
            
        Returns:
            URL 集合
        """
        # 计算截止日期（标准化格式）
        cutoff_datetime = DateTimeUtil.standardize(
            datetime.now() - timedelta(days=days)
        )
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 使用 publish_date 索引
            cursor.execute(
                'SELECT url FROM articles WHERE publish_date >= ?',
                (cutoff_datetime,)
            )
            urls = {row[0] for row in cursor.fetchall()}
            return urls
        except Exception as e:
            print(f"Error getting recent URLs: {e}")
            # 降级：返回所有 URL
            cursor.execute('SELECT url FROM articles')
            return {row[0] for row in cursor.fetchall()}
        
    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Get articles for a specific date (YYYY-MM-DD).
        
        使用标准化的日期格式查询，可以利用索引
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 使用范围查询以利用索引
        # date_str 是 YYYY-MM-DD 格式，匹配 YYYY-MM-DD HH:MM:SS
        start_time = f"{date_str} 00:00:00"
        end_time = f"{date_str} 23:59:59"
        
        cursor.execute('''
            SELECT * FROM articles 
            WHERE publish_date >= ? AND publish_date <= ?
            ORDER BY publish_date DESC
        ''', (start_time, end_time))
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_articles_by_date_range(
        self, 
        start_date: str, 
        end_date: str
    ) -> List[Dict[str, Any]]:
        """
        获取日期范围内的文章
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
            end_date: 结束日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)
        """
        # 标准化日期
        start_std = DateTimeUtil.standardize(start_date)
        end_std = DateTimeUtil.standardize(end_date)
        
        # 如果只提供了日期部分，设置结束时间为当天最后一秒
        if len(end_date) <= 10:
            end_std = end_std[:10] + " 23:59:59"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM articles 
            WHERE publish_date >= ? AND publish_date <= ?
            ORDER BY publish_date DESC
        ''', (start_std, end_std))
        
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_articles_paginated(
        self,
        limit: int = 30,
        offset: int = 0,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        分页获取文章 - 使用 SQL 索引排序，避免内存排序
        
        相比 load_data 的内存排序方案：
        - Big O: O(log n) 索引查询 + O(limit) 返回，而非 O(n log n) 内存排序
        - 内存占用: O(limit) 而非 O(n)
        
        Args:
            limit: 每页数量
            offset: 偏移量
            filters: 筛选条件 {
                'date': 'YYYY-MM-DD' 或 None,
                'platforms': ['wechat', 'douyin', ...] 或 None,
                'categories': ['金融', 'AI', ...] 或 None,
                'authors': ['author1', ...] 或 None
            }
            
        Returns:
            {
                'articles': [...],
                'total': int,
                'has_more': bool
            }
        """
        filters = filters or {}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 构建 WHERE 子句
        where_clauses = []
        params = []
        
        # 日期筛选（范围查询，利用索引）
        if filters.get('date') and filters['date'] != "全部":
            date_str = filters['date']
            if len(date_str) == 10:  # YYYY-MM-DD
                where_clauses.append("publish_date >= ? AND publish_date <= ?")
                params.append(f"{date_str} 00:00:00")
                params.append(f"{date_str} 23:59:59")
        
        # 平台筛选
        if filters.get('platforms'):
            placeholders = ','.join(['?' for _ in filters['platforms']])
            where_clauses.append(f"platform IN ({placeholders})")
            params.extend(filters['platforms'])
        
        # 分类筛选
        if filters.get('categories'):
            placeholders = ','.join(['?' for _ in filters['categories']])
            where_clauses.append(f"category IN ({placeholders})")
            params.extend(filters['categories'])
        
        # 作者筛选
        if filters.get('authors'):
            placeholders = ','.join(['?' for _ in filters['authors']])
            where_clauses.append(f"author IN ({placeholders})")
            params.extend(filters['authors'])
        
        # 构建 WHERE 字符串
        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)
        
        # 1. 先获取总数（使用索引覆盖扫描）
        count_sql = f"SELECT COUNT(*) FROM articles {where_sql}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        # 2. 获取分页数据（利用 publish_date 索引排序）
        query = f'''
            SELECT url, title, subtitle, author, platform, category, 
                   publish_date, summary, video_url, content
            FROM articles 
            {where_sql}
            ORDER BY publish_date DESC
            LIMIT ? OFFSET ?
        '''
        
        cursor.execute(query, params + [limit, offset])
        rows = cursor.fetchall()
        
        articles = [dict(row) for row in rows]
        
        return {
            'articles': articles,
            'total': total,
            'has_more': offset + len(articles) < total
        }
    
    def get_available_dates(self, days: int = 90) -> List[str]:
        """
        获取最近 N 天的可用日期列表
        
        相比全表 DISTINCT：
        - Big O: O(k) k=最近日期数量，而非 O(n) 全表扫描
        - 利用 publish_date 索引，只扫描指定范围
        
        Args:
            days: 最近多少天（默认90天）
            
        Returns:
            日期字符串列表 ['YYYY-MM-DD', ...] 降序排列
        """
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        start_str = start_date.strftime('%Y-%m-%d 00:00:00')
        end_str = end_date.strftime('%Y-%m-%d 23:59:59')
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 使用索引范围查询 + DISTINCT，避免全表扫描
        cursor.execute('''
            SELECT DISTINCT substr(publish_date, 1, 10) as date_only
            FROM articles 
            WHERE publish_date >= ? AND publish_date <= ?
            ORDER BY date_only DESC
        ''', (start_str, end_str))
        
        dates = [row[0] for row in cursor.fetchall()]
        
        return dates

