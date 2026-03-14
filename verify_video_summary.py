import re
import dashscope
from dashscope import MultiModalConversation

# Set API Key
api_key = "sk-7a2537a586f34ab98b55f99bc1430c7e"
dashscope.api_key = api_key

# Example content with video link
content = """
趋势之王or虚有其表？ A股均线知多少？ #量化投资 #理财 #A股 #股票 #掘金计划2026<br /><br /><a href="https://www.douyin.com/aweme/v1/play/?video_id=v0200fg10000d66n9kfog65ibtq99acg&amp;line=0&amp;file_id=108fc269dd504038b9c9c6baf37ce035&amp;sign=e36389cfda803c31bec3aad6d3683ae7&amp;is_play_url=1&amp;source=PackSourceEnum_PUBLISH" rel="noreferrer"><img src="https://p3-pc-sign.douyinpic.com/obj/tos-cn-i-dy/dedaff5a17404e0b9e835396ce62aef2?lk3s=138a59ce&amp;x-expires=2087780400&amp;x-signature=VwiIgnmvew7UKRjWCsmZ6a3lHHM%3D&amp;from=327834062&amp;s=PackSourceEnum_PUBLISH&amp;se=false&amp;sc=cover&amp;biz_tag=pcweb_cover&amp;l=202603021141500856C82453D3FC49A535" style="width: 50%;" /></a><br /><br /><a href="https://www.douyin.com/aweme/v1/play/?video_id=v0200fg10000d66n9kfog65ibtq99acg&amp;line=0&amp;file_id=108fc269dd504038b9c9c6baf37ce035&amp;sign=e36389cfda803c31bec3aad6d3683ae7&amp;is_play_url=1&amp;source=PackSourceEnum_PUBLISH" rel="noreferrer">视频直链</a>
"""

def extract_video_url(content):
    # Try to find the "视频直链" href
    match = re.search(r'href="(https://www\.douyin\.com/aweme/v1/play/\?[^"]+)"[^>]*>视频直链', content)
    if match:
        url = match.group(1).replace("&amp;", "&")
        return url
    return None

video_url = extract_video_url(content)
print(f"Extracted Video URL: {video_url}")

if video_url:
    print("\n--- Calling Qwen-VL-Max ---")
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"video": video_url},
                    {"text": "请观看这个视频，详细总结其核心观点、关键论据和结论。如果视频包含图表或数据，请一并提取。"}
                ]
            }
        ]
        
        response = MultiModalConversation.call(
            model='qwen-vl-max',
            messages=messages,
            stream=True # Use stream for long video processing?
        )
        
        # For stream=True, response is a generator
        print("Response Stream:")
        full_content = ""
        for chunk in response:
            if chunk.status_code == 200:
                if hasattr(chunk.output.choices[0].message.content, 'text'):
                     # Some SDK versions structure
                     pass
                # The SDK usually returns full accumulated output or delta. 
                # Let's just print the final result for simplicity in non-stream mode first.
                pass
            else:
                print(f"Error: {chunk.code} - {chunk.message}")

    except Exception as e:
        print(f"Error calling Qwen-VL: {e}")

    # Retry with stream=False for simpler debugging
    try:
        response = MultiModalConversation.call(
            model='qwen-vl-max',
            messages=messages,
            stream=False
        )
        if response.status_code == 200:
            print("\n✅ Final Summary:")
            print(response.output.choices[0].message.content[0]['text'])
        else:
            print(f"❌ API Error: {response.code} - {response.message}")
            
    except Exception as e:
        print(f"❌ Execution Error: {e}")

else:
    print("No video URL found.")
