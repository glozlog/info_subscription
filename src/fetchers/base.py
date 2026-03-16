from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

class BaseFetcher(ABC):
    """
    Abstract base class for all content fetchers.
    Each platform (WeChat, Douyin, Bilibili) should implement this interface.
    """
    
    @abstractmethod
    def fetch(self, url: str, limit: int = 20, days_limit: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch content from the given URL or account ID.
        
        Args:
            url (str): The URL or identifier for the content source.
            limit (int): Maximum number of items to fetch. Default 20.
            days_limit (int): If > 0, only fetch items published within the last N days. Default 0 (no limit).
            
        Returns:
            List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a piece of content.
            Expected keys:
                - title (str): Title of the content.
                - url (str): Direct link to the content.
                - content (str): The main text content or transcript.
                - publish_date (str): Date of publication.
                - author (str): Author or channel name.
                - platform (str): Source platform name.
        """
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """
        Validate if the URL is supported by this fetcher.
        """
        pass
    
    def _filter_by_date(self, items: List[Dict[str, Any]], days_limit: int) -> List[Dict[str, Any]]:
        """
        Filter items by publish date.
        
        Args:
            items: List of items with 'publish_date' field
            days_limit: Number of days to look back
            
        Returns:
            Filtered list of items
        """
        if days_limit <= 0:
            return items
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
        filtered = []
        
        for item in items:
            pd = item.get("publish_date")
            if not pd:
                continue
            
            # Parse date using common formats
            dt = self._parse_date_to_utc(pd)
            if dt and dt > cutoff:
                filtered.append(item)
        
        return filtered
    
    def _parse_date_to_utc(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string to UTC datetime.
        
        Args:
            date_str: Date string in various formats
            
        Returns:
            UTC datetime or None if parsing fails
        """
        if not date_str:
            return None
        
        s = str(date_str).strip()
        
        # Try common formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        
        for fmt in formats:
            try:
                if s.endswith(" GMT") and fmt.endswith(" GMT"):
                    dt = datetime.strptime(s, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                
                # Try parsing with format
                dt = datetime.strptime(s, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except:
                continue
        
        # Fallback: try parsing ISO format
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc)
        except:
            pass
        
        return None
