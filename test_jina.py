import requests

def test_jina_reader(url):
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        print(f"Requesting: {jina_url}")
        response = requests.get(jina_url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            content = response.text
            print(f"\n--- Success! Content Length: {len(content)} ---")
            print("Preview (First 500 chars):")
            print(content[:500])
            
            # Check for specific failure patterns
            if "Title: Just a moment..." in content or "Checking your browser" in content:
                print("\n[WARNING] Seems to be blocked by Cloudflare or similar.")
            return True
        else:
            print(f"Error: Status Code {response.status_code}")
            print(response.text[:200])
            return False
            
    except Exception as e:
        print(f"Exception: {e}")
        return False

if __name__ == "__main__":
    # Test with the WeChat article
    url = "https://mp.weixin.qq.com/s/ZigZJxotfd2bMbnUCCPNJg"
    test_jina_reader(url)
