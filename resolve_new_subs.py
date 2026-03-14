import requests
from bs4 import BeautifulSoup
import re

def resolve_douyin_short_link(short_url):
    print(f"Resolving short URL: {short_url}")
    try:
        # Douyin short links redirect to the actual page
        response = requests.get(short_url, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        final_url = response.url
        print(f"Final URL: {final_url}")
        
        # Pattern to extract sec_user_id
        # Usually format: https://www.douyin.com/user/MS4wLjABAAAA...
        match = re.search(r'user/([a-zA-Z0-9_\-]+)', final_url)
        if match:
            return match.group(1)
        else:
            print("Could not extract user ID from URL.")
            return None
    except Exception as e:
        print(f"Error resolving Douyin link: {e}")
        return None

def resolve_wechat_article(url):
    print(f"Resolving WeChat article: {url}")
    try:
        response = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to find account name
        # Usually in <a class="rich_media_meta rich_media_meta_text rich_media_meta_nickname" ...>
        nickname_tag = soup.find('a', {'class': 'rich_media_meta rich_media_meta_text rich_media_meta_nickname'})
        if not nickname_tag:
            # Try other selectors or regex
            nickname_tag = soup.find(id="js_name")
            
        if nickname_tag:
            name = nickname_tag.get_text(strip=True)
            print(f"Account Name: {name}")
            
            # Also try to find the unique ID (gh_...)
            # Often in var user_name = "gh_...";
            # or var appmsg_data = { ... "user_name":"gh_..." ... }
            match = re.search(r'var user_name = "(gh_[a-zA-Z0-9_]+)"', str(soup))
            if match:
                gh_id = match.group(1)
                print(f"WeChat ID (gh_id): {gh_id}")
                return gh_id  # Return ID instead of name for better search
            
            return name
        else:
            print("Could not find account name.")
            return None
    except Exception as e:
        print(f"Error resolving WeChat link: {e}")
        return None

if __name__ == "__main__":
    douyin_uid = resolve_douyin_short_link("https://v.douyin.com/fTGLVuQ5KwU/")
    print(f"Douyin UID: {douyin_uid}")
    
    wechat_name = resolve_wechat_article("https://mp.weixin.qq.com/s/rVCDqxb2w0kY-dgsBHLofg")
    print(f"WeChat Name: {wechat_name}")
