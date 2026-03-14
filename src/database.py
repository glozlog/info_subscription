import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import time

class DatabaseManager:
    """
    Manages SQLite database for storing articles and summaries.
    """
    
    def __init__(self, db_path: str = "data.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize database tables."""
        conn = sqlite3.connect(self.db_path)
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
        
        conn.commit()
        conn.close()
        
    def save_article(self, item: Dict[str, Any], summary: Optional[str] = None) -> bool:
        """
        Save or update an article. 
        If summary is provided, it updates the summary.
        If summary is None, it keeps existing summary if available.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        url = item.get('url')
        if not url:
            return False
            
        try:
            # Check if exists to preserve summary if not provided
            cursor.execute('SELECT summary FROM articles WHERE url = ?', (url,))
            row = cursor.fetchone()
            existing_summary = row[0] if row else None
            
            final_summary = summary if summary is not None else existing_summary
            
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
                item.get('publish_date'),
                item.get('video_url'),
                final_summary
            ))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving to DB: {e}")
            return False
        finally:
            conn.close()
            
    def update_summary(self, url: str, summary: str) -> bool:
        """Update only the summary for a specific article."""
        if not url:
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE articles 
            SET summary = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE url = ?
            ''', (summary, url))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating summary: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def update_content(self, url: str, content: str) -> bool:
        """Update only the content for a specific article."""
        if not url:
            return False
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE articles 
            SET content = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE url = ?
            ''', (content, url))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating content: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_article(self, url: str) -> Optional[Dict[str, Any]]:
        """Get article by URL."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM articles WHERE url = ?', (url,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
        
    def get_all_articles(self, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """Get all articles sorted by publish date desc with pagination."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM articles ORDER BY publish_date DESC LIMIT ? OFFSET ?', (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    def count_articles(self) -> int:
        """Get total count of articles."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM articles')
        count = cursor.fetchone()[0]
        conn.close()
        
        return count

    def delete_article(self, url: str) -> bool:
        """Delete an article by URL."""
        if not url:
            return False
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM articles WHERE url = ?', (url,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting article: {e}")
            return False

        
    def get_articles_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """Get articles for a specific date (YYYY-MM-DD)."""
        # This is a bit tricky with varied date formats, 
        # but for now we rely on the string comparison or filtering in app
        # A simple LIKE query might work for standard formats
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM articles WHERE publish_date LIKE ? ORDER BY publish_date DESC', (f"{date_str}%",))
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

