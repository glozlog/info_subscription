
import yaml
import os
import time
from src.fetchers.douyin_fetcher import DouyinFetcher

def update_config():
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        print("Config file not found.")
        return

    # Load Config
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    fetcher = DouyinFetcher()
    subscriptions = config.get("subscriptions", [])
    updated_count = 0
    
    print("Checking Douyin subscriptions for generic names...")
    
    for sub in subscriptions:
        if sub.get("platform") == "douyin":
            name = sub.get("name", "")
            url = sub.get("url", "")
            
            # Check if name needs update
            if "抖音用户" in name or "Douyin User" in name or not name:
                print(f"Updating name for {url} (Current: {name})...")
                
                # We need to fetch the page to get the nickname
                # Since fetcher.fetch returns a list of items, we need a way to just get the nickname.
                # But fetcher._fetch_playwright logic now extracts nickname internally.
                # However, calling fetch() runs the whole scraping process which might be slow.
                # Let's use a modified approach or just run fetch() and see if we can capture the printed output?
                # No, better to add a method or just use the fetch result's author field if available.
                # Wait, fetch() returns items with 'author' field. 
                # If we updated _fetch_playwright to use extracted nickname, the items will have it!
                
                try:
                    # Fetch just a few items to trigger nickname extraction
                    # We can't easily limit items inside fetch without changing code, 
                    # but it only scrolls 5 times, so it's acceptable.
                    items = fetcher.fetch(url, source_name=name)
                    
                    if items and items[0].get("author"):
                        new_name = items[0]["author"]
                        # Verify it's not still generic
                        if "抖音用户" not in new_name and "Douyin User" not in new_name:
                            print(f"  -> Found real name: {new_name}")
                            sub["name"] = new_name
                            updated_count += 1
                        else:
                            print("  -> Could not extract real name (still generic).")
                    else:
                        print("  -> No items found or no author info.")
                        
                except Exception as e:
                    print(f"  -> Error updating: {e}")
                
                time.sleep(2) # Be nice
            else:
                # print(f"Skipping {name} (looks valid)")
                pass

    if updated_count > 0:
        print(f"Saving {updated_count} updates to config.yaml...")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)
        print("Done.")
    else:
        print("No updates needed.")

if __name__ == "__main__":
    update_config()
