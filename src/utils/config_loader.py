import yaml
import os
from typing import Dict, Any, Optional, List

class ConfigLoader:
    """
    Loads configuration from a YAML file with index support for fast lookup.
    
    Provides O(1) lookup for subscriptions by name, URL, or platform.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the config loader.
        
        Args:
            config_path (str): Path to the YAML configuration file.
        """
        self.config_path = config_path
        self.config = {}
        # 索引字典 - 用于O(1)查找
        self._sub_by_name: Dict[str, dict] = {}      # name -> subscription
        self._sub_by_url: Dict[str, dict] = {}       # url -> subscription  
        self._subs_by_platform: Dict[str, List[dict]] = {}  # platform -> [subscriptions]
        self._subs_by_category: Dict[str, List[dict]] = {}  # category -> [subscriptions]
        self._loaded = False
        
    def load(self) -> dict:
        """
        Load the configuration from the file and build indexes.
        
        Returns:
            dict: The configuration as a dictionary.
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 构建索引
        self._build_indexes()
        self._loaded = True
            
        return self.config
    
    def _build_indexes(self):
        """
        Build lookup indexes for O(1) subscription access.
        时间复杂度: O(n)，n为订阅数量
        """
        # 清空现有索引
        self._sub_by_name.clear()
        self._sub_by_url.clear()
        self._subs_by_platform.clear()
        self._subs_by_category.clear()
        
        subscriptions = self.config.get('subscriptions', [])
        
        for sub in subscriptions:
            name = sub.get('name')
            url = sub.get('url')
            platform = sub.get('platform', 'unknown')
            category = sub.get('category', 'General')
            
            # 按名称索引
            if name:
                self._sub_by_name[name] = sub
            
            # 按URL索引
            if url:
                self._sub_by_url[url] = sub
            
            # 按平台索引
            if platform not in self._subs_by_platform:
                self._subs_by_platform[platform] = []
            self._subs_by_platform[platform].append(sub)
            
            # 按分类索引
            if category not in self._subs_by_category:
                self._subs_by_category[category] = []
            self._subs_by_category[category].append(sub)
    
    def get_subscription_by_name(self, name: str) -> Optional[dict]:
        """
        Get subscription by name - O(1) lookup.
        
        Args:
            name: Subscription name
            
        Returns:
            Subscription dict or None
        """
        if not self._loaded:
            self.load()
        return self._sub_by_name.get(name)
    
    def get_subscription_by_url(self, url: str) -> Optional[dict]:
        """
        Get subscription by URL - O(1) lookup.
        
        Args:
            url: Subscription URL
            
        Returns:
            Subscription dict or None
        """
        if not self._loaded:
            self.load()
        return self._sub_by_url.get(url)
    
    def get_subscriptions_by_platform(self, platform: str) -> List[dict]:
        """
        Get all subscriptions for a platform - O(1) lookup.
        
        Args:
            platform: Platform name (e.g., 'wechat2rss', 'douyin')
            
        Returns:
            List of subscription dicts
        """
        if not self._loaded:
            self.load()
        return self._subs_by_platform.get(platform, [])
    
    def get_subscriptions_by_category(self, category: str) -> List[dict]:
        """
        Get all subscriptions for a category - O(1) lookup.
        
        Args:
            category: Category name
            
        Returns:
            List of subscription dicts
        """
        if not self._loaded:
            self.load()
        return self._subs_by_category.get(category, [])
    
    def has_subscription_name(self, name: str) -> bool:
        """
        Check if a subscription name exists - O(1) lookup.
        
        Args:
            name: Subscription name to check
            
        Returns:
            True if exists
        """
        if not self._loaded:
            self.load()
        return name in self._sub_by_name
    
    def has_subscription_url(self, url: str) -> bool:
        """
        Check if a subscription URL exists - O(1) lookup.
        
        Args:
            url: Subscription URL to check
            
        Returns:
            True if exists
        """
        if not self._loaded:
            self.load()
        return url in self._sub_by_url
    
    def get_all_subscription_names(self) -> List[str]:
        """
        Get all subscription names.
        
        Returns:
            List of subscription names
        """
        if not self._loaded:
            self.load()
        return list(self._sub_by_name.keys())
    
    def get_subscription_stats(self) -> Dict[str, Any]:
        """
        Get subscription statistics.
        
        Returns:
            Dict with counts by platform and category
        """
        if not self._loaded:
            self.load()
        return {
            'total': len(self._sub_by_name),
            'by_platform': {k: len(v) for k, v in self._subs_by_platform.items()},
            'by_category': {k: len(v) for k, v in self._subs_by_category.items()}
        }
    
    def reload(self) -> dict:
        """
        Force reload configuration and rebuild indexes.
        
        Returns:
            The configuration as a dictionary.
        """
        self._loaded = False
        return self.load()

    def save(self, config: dict):
        """
        Save the configuration to the file and rebuild indexes.
        
        Args:
            config (dict): The configuration dictionary to save.
        """
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        
        # 更新配置并重建索引
        self.config = config
        self._build_indexes()
        self._loaded = True
