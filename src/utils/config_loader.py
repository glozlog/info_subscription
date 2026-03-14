import yaml
import os

class ConfigLoader:
    """
    Loads configuration from a YAML file.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the config loader.
        
        Args:
            config_path (str): Path to the YAML configuration file.
        """
        self.config_path = config_path
        self.config = {}
        
    def load(self) -> dict:
        """
        Load the configuration from the file.
        
        Returns:
            dict: The configuration as a dictionary.
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        return self.config

    def save(self, config: dict):
        """
        Save the configuration to the file.
        
        Args:
            config (dict): The configuration dictionary to save.
        """
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
