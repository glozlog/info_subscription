from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseSummarizer(ABC):
    """
    Abstract base class for content summarization.
    """
    
    @abstractmethod
    def summarize(self, content: str, video_url: Optional[str] = None) -> str:
        """
        Summarize the provided content, extracting core arguments and key points.
        
        Args:
            content (str): The full text content or transcript.
            
        Returns:
            str: A summary of the content, including core arguments.
        """
        pass
    
    @abstractmethod
    def extract_keywords(self, content: str) -> list[str]:
        """
        Extract relevant keywords from the content.
        
        Args:
            content (str): The full text content.
            
        Returns:
            list[str]: A list of keywords.
        """
        pass
