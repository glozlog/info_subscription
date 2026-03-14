import requests
from bs4 import BeautifulSoup
import sys

def fetch_wechat_article(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # WeChat content is usually in a div with id="js_content"
        content_div = soup.find(id="js_content")
        
        if content_div:
            # Extract text, remove scripts and styles
            for script in content_div(["script", "style"]):
                script.extract()
            text = content_div.get_text(separator="\n", strip=True)
            return text
        else:
            return "Error: Could not find #js_content in the page."
            
    except Exception as e:
        return f"Error fetching URL: {e}"

if __name__ == "__main__":
    test_url = "https://mp.weixin.qq.com/s/ZigZJxotfd2bMbnUCCPNJg" # The article from user's example
    print(f"Fetching: {test_url}")
    content = fetch_wechat_article(test_url)
    print(f"Content Length: {len(content)}")
    print(f"Preview: {content[:500]}")
