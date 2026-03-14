from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseArchiver(ABC):
    """
    Abstract base class for archiving fetched content.
    """
    
    @abstractmethod
    def save(self, data: List[Dict[str, Any]], category: str) -> bool:
        """
        Save the fetched content to a persistent storage (file, database, etc.).
        
        Args:
            data (List[Dict[str, Any]]): The list of content items to save.
            category (str): The category under which to archive the content.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def generate_report(self, data: List[Dict[str, Any]], summary: str) -> str:
        """
        Generate a report (e.g., Markdown or HTML) for the day's content.
        
        Args:
            data (List[Dict[str, Any]]): The list of content items.
            summary (str): The overall summary of the content.
            
        Returns:
            str: The generated report content.
        """
        pass
