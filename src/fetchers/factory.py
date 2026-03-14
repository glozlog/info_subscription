from .wechat2rss_fetcher import Wechat2RssFetcher
from .douyin_fetcher import DouyinFetcher
from .bilibili_fetcher import BilibiliFetcher
from .rss_fetcher import RssFetcher
from .base import BaseFetcher

class FetcherFactory:
    """
    Factory class to create fetchers based on platform configuration.
    """
    
    @staticmethod
    def get_fetcher(platform: str) -> BaseFetcher:
        """
        Get the fetcher instance for the given platform.
        """
        if platform == "douyin":
            return DouyinFetcher()
        elif platform == "bilibili":
            return BilibiliFetcher()
        elif platform == "rss":
            return RssFetcher()
        elif platform == "wechat2rss":
            return Wechat2RssFetcher()
        else:
            raise ValueError(f"Unknown platform: {platform}")
