from .base import BaseSummarizer
from openai import OpenAI
from typing import List, Optional
import httpx

class OpenAISummarizer(BaseSummarizer):
    """
    Summarizer implementation using OpenAI's GPT models or DashScope.
    
    使用HTTP连接池复用，减少TCP握手开销，提升API调用吞吐量。
    """
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", base_url: str = None, provider: str = "openai"):
        """
        Initialize the summarizer with connection pooling.
        
        Args:
            api_key: API密钥
            model: 模型名称
            base_url: 自定义API基础URL
            provider: 提供商 ('openai' 或 'dashscope')
        """
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self._dashscope = None
        self._dashscope_mm = None
        self._http_client = None  # HTTP连接池客户端
        
        if not api_key or api_key == "YOUR_API_KEY":
            print("Warning: API Key not configured. Summarization will be disabled.")
            self.client = None
            return

        if provider == "dashscope":
            try:
                import dashscope
                from dashscope import MultiModalConversation
            except Exception as e:
                raise ModuleNotFoundError("dashscope is required when provider=dashscope. Install it with: pip install dashscope") from e
            dashscope.api_key = api_key
            self._dashscope = dashscope
            self._dashscope_mm = MultiModalConversation
            self.client = "dashscope" # Marker
            # DashScope使用自己的HTTP客户端，不需要额外配置
        else:
            # OpenAI兼容API - 使用HTTP连接池
            # 创建带连接池的HTTP客户端
            self._http_client = httpx.Client(
                limits=httpx.Limits(
                    max_keepalive_connections=5,      # 保持5个活跃连接
                    max_connections=10,               # 最大10个连接
                    keepalive_expiry=30.0             # 连接保持30秒
                ),
                timeout=httpx.Timeout(
                    connect=10.0,                     # 连接超时10秒
                    read=60.0,                        # 读取超时60秒
                    write=10.0,                       # 写入超时10秒
                    pool=5.0                          # 连接池获取超时5秒
                )
            )
            
            # 使用自定义HTTP客户端初始化OpenAI客户端
            self.client = OpenAI(
                api_key=api_key, 
                base_url=base_url,
                http_client=self._http_client
            )
            print(f"OpenAI client initialized with connection pooling (max_keepalive=5, max_connections=10)")
    
    def __del__(self):
        """析构时关闭HTTP连接池"""
        if self._http_client:
            try:
                self._http_client.close()
            except:
                pass
    
    def close(self):
        """手动关闭HTTP连接池"""
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    def summarize(self, content: str, video_url: Optional[str] = None) -> str:
        """
        Summarize content. If video_url is provided and provider supports it, summarize video.
        """
        if not content and not video_url:
            return ""
            
        if not self.client:
            return "Summary not available (API Key missing)."

        system_prompt = "你是一个擅长总结文章并提炼核心论点的助手。请用中文输出。"
        user_prompt = f"请用中文对以下内容做精炼总结，突出核心观点、关键论据与结论：\n\n{content[:4000]}"

        try:
            if self.provider == "dashscope":
                dashscope = self._dashscope
                MultiModalConversation = self._dashscope_mm
                if not dashscope or not MultiModalConversation:
                    raise RuntimeError("DashScope client not initialized.")
                # Handle Video Summary
                if video_url:
                    messages = [
                        {
                            "role": "user",
                            "content": [
                                {"video": video_url},
                                {"text": "请观看这个视频，用中文详细总结其核心观点、关键论据和结论。如果视频包含图表或数据，请一并提取。"}
                            ]
                        }
                    ]
                    response = MultiModalConversation.call(
                        model='qwen-vl-max', # Use VL model for video
                        messages=messages,
                        stream=False,
                    )
                    if response.status_code == 200:
                        return response.output.choices[0].message.content[0]['text'].strip()
                    else:
                        print(f"DashScope Video Error: {response.code} - {response.message}")
                        return f"Error generating video summary: {response.message}"
                
                # Text Summary
                response = dashscope.Generation.call(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    result_format='message',
                )
                if response.status_code == 200:
                    return response.output.choices[0].message.content.strip()
                else:
                    print(f"DashScope Error: {response.code} - {response.message}")
                    return f"Error generating summary: {response.message}"
            else:
                # OpenAI Compatible
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error during summarization: {e}")
            return "Error generating summary."

    def extract_keywords(self, content: str) -> List[str]:
        """
        Extract keywords.
        """
        if not content:
            return []
            
        prompt = f"Extract 5-10 main keywords from the following text, separated by commas:\n\n{content[:2000]}"
        
        try:
            if self.provider == "dashscope":
                dashscope = self._dashscope
                if not dashscope:
                    raise RuntimeError("DashScope client not initialized.")
                response = dashscope.Generation.call(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    result_format='message',
                )
                if response.status_code == 200:
                    keywords_str = response.output.choices[0].message.content.strip()
                    return [k.strip() for k in keywords_str.split(',')]
                else:
                    return []
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}]
                )
                keywords_str = response.choices[0].message.content.strip()
                return [k.strip() for k in keywords_str.split(',')]
        except Exception as e:
            print(f"Error extracting keywords: {e}")
            return []
