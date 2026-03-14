from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseFetcher(ABC):
    """
    Abstract base class for all content fetchers.
    Each platform (WeChat, Douyin, Bilibili) should implement this interface.
    """
    
    @abstractmethod
    def fetch(self, url: str) -> List[Dict[str, Any]]:
        """
        Fetch content from the given URL or account ID.
        
        Args:
            url (str): The URL or identifier for the content source.
            
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
