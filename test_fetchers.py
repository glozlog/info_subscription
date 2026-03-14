from src.fetchers.factory import FetcherFactory
import json

def test_fetcher(platform, url):
    print(f"\nTesting {platform} with URL: {url}")
    try:
        fetcher = FetcherFactory.get_fetcher(platform)
        if not fetcher:
            print(f"Fetcher not found for {platform}")
            return

        if not fetcher.validate_url(url):
            print(f"URL validation failed for {url}")
            # Continue anyway for testing
        
        results = fetcher.fetch(url)
        print(f"Fetched {len(results)} items.")
        for item in results:
            print(f"- Title: {item.get('title')}")
            print(f"  Author: {item.get('author')}")
            print(f"  Platform: {item.get('platform')}")
            print(f"  Date: {item.get('publish_date')}")
            print(f"  URL: {item.get('url')}")
            content = item.get('content', '')
            print(f"  Content Length: {len(content)}")
            print(f"  Content Preview: {content[:100]}...")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test cases
    
    # User provided WeChat Article
    url = "https://mp.weixin.qq.com/s/pf0ZKYFbMTLHpk9Kb1-TJg"
    test_fetcher("wechat", url)
