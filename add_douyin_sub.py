import yaml
import os
import sys
from src.fetchers.douyin_fetcher import DouyinFetcher

def add_douyin_subscription(url):
    print(f"Processing Douyin URL: {url}")
    
    # 1. Analyze the URL to get account name
    fetcher = DouyinFetcher()
    info = fetcher.get_account_info(url)
    
    account_name = info['name']
    print(f"Detected Douyin Account: {account_name}")
    
    # 2. Update config.yaml
    config_path = "config.yaml"
    
    # Load existing config
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    
    # Ensure subscriptions key exists
    if 'subscriptions' not in config:
        config['subscriptions'] = []
    
    # Check if already exists
    for sub in config['subscriptions']:
        if sub.get('url') == url:
            print(f"Subscription for '{account_name}' ({url}) already exists.")
            return

    # Add new subscription
    new_sub = {
        'platform': 'douyin',
        'name': account_name,
        'url': url,
        'category': 'Entertainment' # Default category
    }
    
    config['subscriptions'].append(new_sub)
    
    # Save config
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        
    print(f"Successfully added subscription for '{account_name}'!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        print("This tool helps you subscribe to a Douyin user by analyzing their profile link.")
        url = input("Please enter the Douyin user profile URL: ").strip()
        
    if url:
        add_douyin_subscription(url)
