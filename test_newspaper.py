from newspaper import Article
import sys

def test_newspaper(url):
    print(f"Fetching: {url}")
    try:
        article = Article(url, language='zh')
        article.download()
        article.parse()
        
        print(f"\nTitle: {article.title}")
        print(f"Authors: {article.authors}")
        print(f"Publish Date: {article.publish_date}")
        print(f"Text Length: {len(article.text)}")
        
        if len(article.text) > 0:
            print("\n--- Preview (First 500 chars) ---")
            print(article.text[:500])
        else:
            print("\n[WARNING] No text extracted.")
            
        return article.text
        
    except Exception as e:
        print(f"Error: {e}")
        return ""

if __name__ == "__main__":
    url = "https://mp.weixin.qq.com/s/ZigZJxotfd2bMbnUCCPNJg"
    test_newspaper(url)
