import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from collections import Counter
import glob
import subprocess
import time
import sys
import re
import html
import secrets
import urllib.parse
import feedparser
import requests
from bs4 import BeautifulSoup # Restored for clean_html
from src.database import DatabaseManager # Import DatabaseManager
from src.concurrency import ConcurrencyManager # Import ConcurrencyManager for batch fetching
# from src.summarizer.llm_summarizer import OpenAISummarizer # Removed to avoid import errors in Streamlit

# Set page config
st.set_page_config(
    page_title="信息订阅日报",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Constants
ARCHIVES_DIR = "archives" # Kept for backward compatibility if needed, but primary source is DB

# Custom CSS
st.markdown("""
<style>
    .reportview-container {
        background: #f0f2f6;
    }
    .main .block-container {
        padding-top: 2rem;
    }
    .stCard {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    .platform-tag {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.8rem;
        font-weight: 600;
        color: white;
        margin-right: 0.5rem;
    }
    .tag-wechat { background-color: #07c160; }
    .tag-douyin { background-color: #000000; }
    .tag-bilibili { background-color: #fb7299; }
    .tag-rss { background-color: #07c160; } /* Use WeChat color for RSS as it's mostly WeChat now */
    .tag-default { background-color: #6c757d; }
    
    .new-badge {
        background-color: #dc3545;
        color: white;
        padding: 0.1rem 0.4rem;
        border-radius: 1rem;
        font-size: 0.7rem;
        vertical-align: middle;
        margin-left: 0.5rem;
    }
    .summary-box {
        background-color: #f8f9fa;
        border-left: 4px solid #0366d6;
        padding: 1rem;
        margin-top: 1rem;
        border-radius: 0 0.25rem 0.25rem 0;
    }

    .card-title {
        display: block;
        font-size: 1.0rem;
        font-weight: 700;
        line-height: 1.25;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .card-title a {
        color: inherit;
        text-decoration: none;
    }
    .meta-row {
        display: flex;
        justify-content: flex-end;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
    }
    .meta-chip {
        display: inline-block;
        padding: 0.10rem 0.35rem;
        border: 1px solid rgba(0,0,0,0.12);
        border-radius: 999px;
        font-size: 0.72rem;
        line-height: 1.2;
        color: #444;
        background: #fff;
    }
</style>
""", unsafe_allow_html=True)

from src.utils.config_loader import ConfigLoader
import yaml

def update_subscription_category(author_name, new_category):
    try:
        # Load config properly
        loader = ConfigLoader()
        config = loader.load()
        if not config: return False
        
        subscriptions = config.get('subscriptions', [])
        
        updated = False
        for sub in subscriptions:
            if sub.get('name') == author_name:
                sub['category'] = new_category
                updated = True
        
        if updated:
            # Save back to config.yaml
            with open("config.yaml", 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            # Update DB
            try:
                db = DatabaseManager()
                import sqlite3
                with sqlite3.connect(db.db_path) as conn:
                    conn.execute("UPDATE articles SET category = ? WHERE author = ?", (new_category, author_name))
                    conn.commit()
            except Exception as e:
                print(f"Error updating DB: {e}")
            return True
        return False
    except Exception as e:
        print(f"Error updating category: {e}")
        return False

# Helper to add subscription configuration only
def add_subscription_config(platform, name, url, category):
    try:
        loader = ConfigLoader()
        config = loader.load()
        if not config: return False, "Config load failed"
        
        subscriptions = config.get('subscriptions', [])
        
        # Check for duplicates
        for sub in subscriptions:
            if sub.get('url') == url:
                return False, "Subscription URL already exists"
            if sub.get('name') == name:
                return False, "Subscription name already exists"
                
        new_sub = {
            "platform": platform,
            "name": name,
            "url": url,
            "category": category
        }
        subscriptions.append(new_sub)
        config['subscriptions'] = subscriptions
        
        # Save config
        with open("config.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
        return True, "Success"
    except Exception as e:
        return False, str(e)

@st.cache_data(ttl=60)
def load_global_stats():
    """Load global statistics directly from DB (bypassing pagination)."""
    try:
        db = DatabaseManager()
        
        # 1. Total articles - 使用带缓存的 count
        total_count = db.count_articles(use_cache=True, cache_ttl=60)
        
        # 2. Today's count
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_articles = db.get_articles_by_date(today_str)
        today_count = len(today_articles)
        
        # 3. Unique authors/sources - 使用带缓存的 count
        author_count = db.get_author_count(use_cache=True, cache_ttl=60)
        
        # Get author distribution for the expander
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT author, platform, category, COUNT(*) as c FROM articles GROUP BY author ORDER BY c DESC")
        author_stats = [{"author": r[0], "platform": r[1], "category": r[2], "count": r[3]} for r in cursor.fetchall()]
        conn.close()
        
        return {
            "total": total_count,
            "today": today_count,
            "authors": author_count,
            "author_stats": author_stats
        }
    except Exception as e:
        print(f"Error loading stats: {e}")
        return {"total": 0, "today": 0, "authors": 0, "author_stats": []}


@st.cache_data(ttl=60)
def load_data(limit=30, offset=0, filters=None):
    """
    Load articles from SQLite database with server-side filtering and pagination.
    使用优化的 get_articles_paginated 方法，利用 SQL 索引排序。
    
    filters: dict with keys 'date', 'platforms', 'categories', 'authors'
    """
    try:
        db = DatabaseManager()
        
        # 使用优化后的分页查询方法（利用 publish_date 索引）
        result = db.get_articles_paginated(
            limit=limit,
            offset=offset,
            filters=filters
        )
        
        articles = result['articles']
        total_items = result['total']
        
        if not articles:
            return pd.DataFrame(), 0
        
        # 转换为 DataFrame
        df = pd.DataFrame(articles)
        
        # 添加用于显示的日期列（已经是标准化格式）
        df['sort_date'] = pd.to_datetime(df['publish_date'], errors='coerce')
        df['report_date'] = df['sort_date'].dt.strftime('%Y-%m-%d')
        df['report_date_dt'] = df['sort_date']
        
        return df, total_items
        
    except Exception as e:
        st.error(f"Error loading data from database: {e}")
        return pd.DataFrame(), 0

def get_platform_color(platform):
    colors = {
        'wechat': 'tag-wechat',
        'douyin': 'tag-douyin',
        'bilibili': 'tag-bilibili',
        'rss': 'tag-rss'
    }
    return colors.get(platform.lower(), 'tag-default')

def get_platform_label(platform):
    """Map internal platform codes to user-friendly labels."""
    labels = {
        'wechat': '微信公众号',
        'rss': '微信公众号(RSS)', # Mapped as requested
        'douyin': '抖音',
        'bilibili': 'Bilibili'
    }
    return labels.get(platform.lower(), platform.upper())

def clean_html(raw_html):
    """Clean HTML tags from text."""
    if not isinstance(raw_html, str):
        return ""
    # Use BeautifulSoup to strip tags
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ")
    # Collapse whitespace
    return re.sub(r'\s+', ' ', text).strip()

def truncate_text(text: str, max_chars: int = 30) -> str:
    if not isinstance(text, str):
        return ""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"

def format_date(date_obj):
    """Format datetime object to friendly string."""
    if pd.isna(date_obj):
        return ""
    # Check if it's a pandas Timestamp or datetime
    try:
        # 如果时间是 00:00:00，只显示日期部分
        if hasattr(date_obj, 'hour') and date_obj.hour == 0 and date_obj.minute == 0:
            return date_obj.strftime('%Y-%m-%d')
        return date_obj.strftime('%Y-%m-%d %H:%M')
    except:
        return str(date_obj)

def _python_executable():
    python_exe = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
    if os.path.exists(python_exe):
        return python_exe
    return sys.executable

def _wechat2rss_base_url() -> str:
    return os.environ.get("WECHAT2RSS_BASE_URL", "http://localhost:8080").rstrip("/")

def _wechat2rss_token_file() -> str:
    return os.path.join(os.getcwd(), "wechat2rss", "token.txt")

def _read_wechat2rss_token() -> str:
    path = _wechat2rss_token_file()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return (f.readline() or "").strip()
    except Exception:
        return ""
    return ""

def _start_wechat2rss() -> bool:
    script_path = os.path.join(os.getcwd(), "scripts", "start_wechat2rss.ps1")
    if not os.path.exists(script_path):
        return False
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception:
        return False

def _feishu_oauth_config():
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    redirect_uri = os.environ.get("FEISHU_REDIRECT_URI", "").strip()
    if not (app_id and app_secret and redirect_uri):
        try:
            sec = st.secrets.get("feishu", {})
            app_id = app_id or str(sec.get("app_id", "")).strip()
            app_secret = app_secret or str(sec.get("app_secret", "")).strip()
            redirect_uri = redirect_uri or str(sec.get("redirect_uri", "")).strip()
        except Exception:
            pass
    return app_id, app_secret, redirect_uri

def _feishu_auth_enabled() -> bool:
    app_id, app_secret, redirect_uri = _feishu_oauth_config()
    return bool(app_id and app_secret and redirect_uri)

def _get_query_params() -> dict:
    qp = getattr(st, "query_params", None)
    if qp is not None:
        try:
            return {k: list(v) if isinstance(v, (list, tuple)) else [str(v)] for k, v in qp.items()}
        except Exception:
            return {}
    try:
        return st.experimental_get_query_params()
    except Exception:
        return {}

def _clear_query_params() -> None:
    qp = getattr(st, "query_params", None)
    if qp is not None:
        try:
            qp.clear()
            return
        except Exception:
            pass
    try:
        st.experimental_set_query_params()
    except Exception:
        pass

def _feishu_login_url() -> str:
    app_id, _, redirect_uri = _feishu_oauth_config()
    state = secrets.token_urlsafe(24)
    st.session_state["feishu_oauth_state"] = state
    qs = {
        "client_id": app_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return "https://accounts.feishu.cn/open-apis/authen/v1/authorize?" + urllib.parse.urlencode(qs, quote_via=urllib.parse.quote)

def _feishu_exchange_code(code: str) -> str:
    app_id, app_secret, redirect_uri = _feishu_oauth_config()
    payload = {
        "grant_type": "authorization_code",
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    r = requests.post(
        "https://open.feishu.cn/open-apis/authen/v2/oauth/token",
        json=payload,
        timeout=10,
    )
    data = r.json() if r.content else {}
    if not isinstance(data, dict) or data.get("code") != 0:
        raise RuntimeError(str(data))
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Missing access_token")
    return token

def _feishu_get_user_info(access_token: str) -> dict:
    r = requests.get(
        "https://open.feishu.cn/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    data = r.json() if r.content else {}
    if not isinstance(data, dict) or data.get("code") not in (0, 20001, 20005, 20008, 20021, 20022, 20023):
        raise RuntimeError(str(data))
    if data.get("code") != 0:
        raise RuntimeError(str(data))
    u = data.get("data") or {}
    if not isinstance(u, dict):
        u = {}
    return {
        "name": u.get("name") or u.get("en_name") or "",
        "open_id": u.get("open_id") or u.get("sub") or "",
        "user_id": u.get("user_id") or "",
        "tenant_key": u.get("tenant_key") or "",
        "email": u.get("email") or "",
        "avatar_url": u.get("avatar_url") or u.get("avatar_big") or "",
    }

def _feishu_handle_oauth_callback() -> None:
    params = _get_query_params()
    code = (params.get("code") or [""])[0]
    state = (params.get("state") or [""])[0]
    if not code:
        return
    expected = st.session_state.get("feishu_oauth_state", "")
    if expected and state != expected:
        raise RuntimeError("Invalid state")
    token = _feishu_exchange_code(code)
    user = _feishu_get_user_info(token)
    st.session_state["feishu_user"] = user
    _clear_query_params()

def regenerate_summary(url, content, video_url=None):
    """Regenerate summary for a specific article using external script."""
    try:
        # Use subprocess to call generate_summary.py
        # This isolates the environment and avoids module import issues in Streamlit
        
        # Prepare input data for stdin
        input_data = {
            "url": url,
            "content": content if content else "",
            "video_url": video_url
        }
        
        json_input = json.dumps(input_data, ensure_ascii=False)
        
        # Determine Python executable
        # If running in venv, use the venv python
        # Hardcode the venv python path to ensure it uses the correct environment
        # D:\TRAE\信息订阅\.venv\Scripts\python.exe
        python_exe = _python_executable()
        
        # Debug: Print python executable being used
        print(f"DEBUG: Using Python Executable: {python_exe}")
            
        cmd = [python_exe, "generate_summary.py"]
            
        # Run process
        # Use CREATE_NO_WINDOW on Windows to avoid popping up console windows
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8', # Ensure UTF-8
            creationflags=creationflags
        )
        
        stdout, stderr = process.communicate(input=json_input)
        
        if process.returncode == 0:
            return stdout.strip() if stdout else ""
        else:
            error_msg = stderr.strip() if stderr else "Unknown error"
            return f"Error regenerating summary: {error_msg} (Exit Code {process.returncode})"
            
    except Exception as e:
        return f"Error executing regeneration script: {e}"

def fetch_content_via_playwright(url):
    """单篇文章抓取（兼容旧接口）"""
    try:
        data = {"url": url}
        json_input = json.dumps(data, ensure_ascii=False)
        python_exe = _python_executable()
        cmd = [python_exe, "fetch_wechat_playwright.py"]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            creationflags=creationflags
        )
        stdout, stderr = process.communicate(input=json_input)
        if process.returncode == 0:
            try:
                result = json.loads(stdout.strip()) if stdout else {"content": ""}
                # 兼容新旧接口格式
                if result.get("mode") == "single":
                    return result.get("result", {})
                return result
            except:
                return {"error": "解析失败"}
        else:
            msg = stderr.strip() if stderr else "未知错误"
            return {"error": msg}
    except Exception as e:
        return {"error": str(e)}


def fetch_contents_batch_via_playwright(urls: list) -> dict:
    """
    批量抓取文章内容 - 使用 ConcurrencyManager 控制并发
    
    Args:
        urls: 文章URL列表
        
    Returns:
        {
            'results': [{'url': '...', 'title': '...', 'content': '...', 'success': True}, ...],
            'stats': {'total': N, 'success': N, 'failed': N}
        }
    """
    if not urls:
        return {'results': [], 'stats': {'total': 0, 'success': 0, 'failed': 0}}
    
    python_exe = _python_executable()
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    
    # 将URL列表分批，每批最多5个（在单个进程中复用浏览器）
    batch_size = 5
    url_batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]
    
    def fetch_batch(batch_urls: list) -> list:
        """抓取一批URL"""
        try:
            data = {"urls": batch_urls}
            json_input = json.dumps(data, ensure_ascii=False)
            
            process = subprocess.Popen(
                [python_exe, "fetch_wechat_playwright.py"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                creationflags=creationflags
            )
            
            stdout, stderr = process.communicate(input=json_input, timeout=120)
            
            if process.returncode == 0:
                result = json.loads(stdout.strip()) if stdout else {}
                return result.get("results", [])
            else:
                # 返回所有失败的标记
                return [{'url': url, 'success': False, 'error': stderr.strip()} for url in batch_urls]
        except subprocess.TimeoutExpired:
            process.kill()
            return [{'url': url, 'success': False, 'error': 'Timeout'} for url in batch_urls]
        except Exception as e:
            return [{'url': url, 'success': False, 'error': str(e)} for url in batch_urls]
    
    all_results = []
    
    # 使用 ConcurrencyManager 控制并发（最多3个浏览器实例同时运行）
    with ConcurrencyManager(
        fetcher_workers=3,      # 最多3个并发进程
        summarizer_workers=1,   # 不需要摘要功能
        max_browsers=3,         # 最多3个浏览器实例
        use_backpressure=True   # 启用背压控制
    ) as cm:
        
        def wrapped_fetch(batch):
            """包装抓取函数，获取浏览器资源许可"""
            if not cm.browser_limiter.acquire(timeout=60):
                raise TimeoutError("Browser resource timeout")
            try:
                return fetch_batch(batch)
            finally:
                cm.browser_limiter.release()
        
        # 并行处理所有批次
        result = cm.fetcher_backpressure.map_with_backpressure(
            wrapped_fetch,
            url_batches,
            on_result=lambda batch, res: all_results.extend(res),
            on_error=lambda batch, err: all_results.extend(
                [{'url': url, 'success': False, 'error': str(err)} for url in batch]
            )
        )
    
    # 统计结果
    success_count = sum(1 for r in all_results if r.get('success'))
    failed_count = len(all_results) - success_count
    
    return {
        'results': all_results,
        'stats': {
            'total': len(urls),
            'success': success_count,
            'failed': failed_count,
            'batches': len(url_batches)
        }
    }

def regenerate_all_summaries_and_archives():
    try:
        python_exe = _python_executable()
        cmd = [python_exe, "main.py", "--regenerate-all"]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            creationflags=creationflags
        )
        stdout, stderr = process.communicate()
        ok = process.returncode == 0
        return ok, stdout or "", stderr or ""
    except Exception as e:
        return False, "", str(e)

def bootstrap_subscription(platform: str, name: str, url: str, category: str, backfill_days: int = 90):
    try:
        python_exe = _python_executable()
        cmd = [python_exe, "bootstrap_subscription.py"]
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        payload = {
            "platform": platform,
            "name": name,
            "url": url,
            "category": category,
            "backfill_days": backfill_days,
        }
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            creationflags=creationflags
        )
        stdout, stderr = process.communicate(input=json.dumps(payload, ensure_ascii=False))
        if process.returncode != 0:
            return False, None, stdout or "", stderr or ""
        try:
            data = json.loads(stdout.strip()) if stdout else None
        except Exception:
            data = None
        return True, data, stdout or "", stderr or ""
    except Exception as e:
        return False, None, "", str(e)

# Helper to manage background tasks
def get_task_state():
    if 'task_state' not in st.session_state:
        st.session_state['task_state'] = {
            'running': False,
            'pid': None,
            'log_file': None,
            'start_time': None,
            'description': ""
        }
    return st.session_state['task_state']

def start_background_task(command, description):
    state = get_task_state()
    if state['running']:
        st.warning(f"已有任务在运行中: {state['description']}")
        return False
        
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    log_file = os.path.join(log_dir, f"run_{int(time.time())}.log")
    
    try:
        # Open log file for writing
        with open(log_file, "w", encoding='utf-8') as f:
            # Start process, redirecting stdout/stderr to file
            process = subprocess.Popen(
                command,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
        state['running'] = True
        state['pid'] = process.pid
        state['log_file'] = log_file
        state['start_time'] = time.time()
        state['description'] = description
        return True
    except Exception as e:
        st.error(f"启动任务失败: {e}")
        return False

def stop_background_task():
    state = get_task_state()
    if not state['running'] or not state['pid']:
        return
        
    try:
        import psutil
        parent = psutil.Process(state['pid'])
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
        state['running'] = False
        state['pid'] = None # Clear PID to prevent zombie checks
        st.success("任务已手动停止")
    except Exception as e:
        # Process might already be dead
        state['running'] = False
        state['pid'] = None
        st.warning(f"停止任务时提示: {e}")

def check_task_status():
    state = get_task_state()
    if not state['running']:
        return
        
    # Check if process is still running
    import psutil
    try:
        if not psutil.pid_exists(state['pid']):
            state['running'] = False
            state['pid'] = None
            st.success(f"任务完成: {state['description']}")
            load_data.clear() # Clear cache to show new data
            return
            
        p = psutil.Process(state['pid'])
        if p.status() == psutil.STATUS_ZOMBIE:
            state['running'] = False
            state['pid'] = None
            st.success(f"任务完成: {state['description']}")
            load_data.clear()
            return
    except:
        state['running'] = False
        state['pid'] = None
        st.success(f"任务已结束: {state['description']}")
        load_data.clear()
        return

def render_task_sidebar():
    state = get_task_state()
    check_task_status()
    
    if state['running']:
        st.sidebar.info(f"🔄 正在运行: {state['description']}")
        
        # Show logs
        if state['log_file'] and os.path.exists(state['log_file']):
            try:
                # Read last 20 lines
                with open(state['log_file'], 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                    last_lines = lines[-20:] if len(lines) > 20 else lines
                    log_content = "".join(last_lines)
                    st.sidebar.code(log_content, language="bash")
            except:
                st.sidebar.text("读取日志失败...")
        
        if st.sidebar.button("🛑 停止任务", type="primary"):
            stop_background_task()
            st.rerun()
            
        # Auto refresh
        time.sleep(2)
        st.rerun()

def main():
    # Sidebar
    st.sidebar.title("📰 信息订阅控制台")

    if _feishu_auth_enabled():
        try:
            _feishu_handle_oauth_callback()
        except Exception as e:
            st.sidebar.error(f"飞书登录回调处理失败: {e}")
            _clear_query_params()

        user = st.session_state.get("feishu_user")
        if not user:
            st.title("🔐 登录")
            st.link_button("使用飞书登录", _feishu_login_url())
            st.caption("需要先在飞书开放平台配置网页应用与重定向 URL，并在本机配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_REDIRECT_URI。")
            return

        label = user.get("name") or user.get("email") or user.get("open_id") or "已登录"
        st.sidebar.success(f"飞书登录：{label}")
        if st.sidebar.button("退出飞书登录", key="btn_feishu_logout"):
            if "feishu_user" in st.session_state:
                del st.session_state["feishu_user"]
            if "feishu_oauth_state" in st.session_state:
                del st.session_state["feishu_oauth_state"]
            st.rerun()
    
    # Render Task Status Area (Always visible at top)
    render_task_sidebar()
    
    # 1. 刷新数据 (Refresh UI) - Priority 1
    if st.sidebar.button("🔄 刷新数据"):
        load_data.clear()
        st.rerun()

    # 2. 抓取更新 (Fetch Updates)
    st.sidebar.markdown("### 抓取更新")
    
    # 2.1 近3天抓取 (Fetch 3 Days) - Priority 2
    if st.sidebar.button("🚀 近3天抓取 (快速)"):
        start_background_task(
            [_python_executable(), "-u", "main.py", "--run-3days"],
            "近3天抓取 (快速)"
        )
        st.rerun()

    # 2.2 近20条抓取 (Fetch 20 Items) - Priority 3
    if st.sidebar.button("🛠️ 近20条抓取 (深度)"):
        start_background_task(
            [_python_executable(), "-u", "main.py", "--run-now"],
            "近20条抓取 (深度)"
        )
        st.rerun()

    # 2.3 选定源抓取 (Selected Source) - Priority 4
    with st.sidebar.expander("🎯 选定源抓取", expanded=False):
        # Load author/source list from both DB and config
        stats = load_global_stats()
        db_sources = [s['author'] for s in stats['author_stats']]
        
        # Also load sources from config (including newly added ones)
        config_sources = []
        try:
            loader = ConfigLoader()
            config = loader.load()
            if config:
                for sub in config.get('subscriptions', []):
                    name = sub.get('name')
                    if name and name not in db_sources:
                        config_sources.append(name)
        except:
            pass
        
        # Combine: DB sources first, then config-only sources (marked as NEW)
        sources = db_sources + [f"{s} (NEW)" for s in config_sources]
        
        selected_source = st.selectbox("选择要抓取的订阅源", options=sources if sources else ["无可用订阅源"])
        
        # Strip the (NEW) marker if present
        if selected_source and " (NEW)" in selected_source:
            selected_source = selected_source.replace(" (NEW)", "")
        fetch_mode = st.radio("抓取模式", ["近20条 (深度)", "近3天 (快速)"])
        
        if st.button("🚀 开始抓取该源"):
            if not selected_source:
                st.error("请先选择订阅源")
            else:
                mode_arg = "--run-now" if "深度" in fetch_mode else "--run-3days"
                description = f"抓取 {selected_source} ({'深度' if '深度' in fetch_mode else '快速'})"
                
                start_background_task(
                    [_python_executable(), "-u", "main.py", mode_arg, selected_source],
                    description
                )
                st.rerun()

    # 3. 新增抖音订阅 (Add Douyin)
    with st.sidebar.expander("➕ 新增抖音订阅", expanded=False):
        st.caption("添加订阅源配置，添加后请使用“选定源抓取”功能获取内容。")
        douyin_url = st.text_input("抖音博主主页 URL", placeholder="https://www.douyin.com/user/...")
        douyin_name = st.text_input("订阅名称", placeholder="例如：某某博主")
        douyin_category = st.selectbox("分类", ["金融", "AI", "硬件", "时政", "生活", "其他"], index=0)
        
        if st.button("✅ 仅添加订阅配置"):
            if not douyin_url or "douyin.com/user/" not in douyin_url:
                st.error("请输入正确的抖音主页 URL（需包含 /user/ ）")
            elif not douyin_name.strip():
                st.error("请输入订阅名称")
            else:
                ok, msg = add_subscription_config(
                    platform="douyin",
                    name=douyin_name.strip(),
                    url=douyin_url.strip(),
                    category=douyin_category
                )
                if ok:
                    st.success(f"订阅源 '{douyin_name}' 已添加！")
                    st.info("请前往上方“🎯 选定源抓取”选择该源并开始抓取。")
                    time.sleep(2)
                    load_global_stats.clear()
                    st.rerun()
                else:
                    st.error(f"添加失败: {msg}")

    with st.sidebar.expander("➕ 新增公众号订阅（Wechat2RSS / BID）", expanded=False):
        st.caption("输入公众号 BID，写入 config.yaml。需要先在 Wechat2RSS 控制台完成登录并添加公众号。")
        base_url = _wechat2rss_base_url()
        col_w2r_a, col_w2r_b = st.columns(2)
        with col_w2r_a:
            if st.button("🚀 启动 Wechat2RSS"):
                ok = _start_wechat2rss()
                if ok:
                    st.session_state["wechat2rss_started_at"] = time.time()
                    st.success("已启动（或已在运行），将自动打开 8080 并把 Token 复制到剪贴板。")
                else:
                    st.error("启动失败：未找到启动脚本 scripts/start_wechat2rss.ps1 或执行异常。")
        with col_w2r_b:
            st.link_button("打开 8080 控制台", base_url)

        token_val = _read_wechat2rss_token()
        st.text_input("Token（自动读取；复制用）", value=token_val, disabled=False)
        if not token_val:
            st.caption("Token 为空时：先点“启动 Wechat2RSS”，或在 8080 登录页查看容器日志里的 Token。")

        wechat2rss_bid = st.text_input("BID", placeholder="例如：3224422740")
        wechat2rss_name = st.text_input("订阅名称（可选）", placeholder="留空则自动从 RSS 标题读取")
        wechat2rss_category = st.selectbox("分类（公众号）", ["金融", "AI", "硬件", "时政", "生活", "其他"], index=0)

        if st.button("✅ 添加公众号订阅配置"):
            bid = (wechat2rss_bid or "").strip()
            if not bid.isdigit():
                st.error("请输入正确的 BID（纯数字）")
            else:
                feed_url = f"{base_url}/feed/{bid}.xml"
                fp = feedparser.parse(feed_url)
                detected_name = ""
                try:
                    detected_name = getattr(getattr(fp, "feed", {}), "title", "") or ""
                except Exception:
                    detected_name = ""

                final_name = (wechat2rss_name or "").strip() or detected_name.strip()
                if not final_name:
                    st.error("无法从 RSS 读取标题，请确认 BID 已在 Wechat2RSS 中添加且 feed 可访问。")
                else:
                    ok, msg = add_subscription_config(
                        platform="wechat2rss",
                        name=final_name,
                        url=bid,
                        category=wechat2rss_category
                    )
                    if ok:
                        st.success(f"订阅源 '{final_name}' 已添加！")
                        st.info("可在“🎯 选定源抓取”中选择该源开始抓取。")
                        time.sleep(1)
                        load_global_stats.clear()
                        st.rerun()
                    else:
                        st.error(f"添加失败: {msg}")

    with st.sidebar.expander("🛠️ 高级操作", expanded=False):
        st.warning("该操作会重算数据库内全部文章摘要并覆盖现有存档，耗时较长且可能触发外部风控。")
        confirm = st.checkbox("我确认要执行全量重算与覆盖存档", value=False)
        if st.button("♻️ 全量重算摘要并覆盖存档", disabled=not confirm):
            with st.spinner("正在全量重算并覆盖存档..."):
                ok, out, err = regenerate_all_summaries_and_archives()
                if ok:
                    st.success("全量重算完成")
                else:
                    st.error("全量重算失败")
                with st.expander("查看执行日志"):
                    if err:
                        st.code(err)
                    if out:
                        st.code(out)
                load_data.clear()
                st.rerun()
        
        st.divider()
        st.markdown("#### 🧭 批量抓取正文")
        st.caption("对当前筛选结果中的微信/RSS文章批量抓取正文（最多50篇）")
        
        # 批量抓取需要的数据在 main() 函数中处理，这里添加占位按钮
        if st.button("🚀 批量抓取正文（当前筛选）", key="btn_batch_fetch_sidebar"):
            st.session_state['trigger_batch_fetch'] = True
            st.rerun()

    # Load Global Stats (Independent of pagination)
    global_stats = load_global_stats()
    
    # --- GLOBAL FILTERS ---
    st.sidebar.header("🔍 全局筛选")
    
    # 1. Date Filter
    # 使用优化后的 get_available_dates 方法（限制90天范围，利用索引）
    @st.cache_data(ttl=600)
    def get_available_dates_cached():
        try:
            db = DatabaseManager()
            return db.get_available_dates(days=90)
        except:
            return []

    available_dates = get_available_dates_cached()
    # Add "Today" explicitly if missing? No, rely on DB.
    
    selected_date = st.sidebar.selectbox(
        "📅 日期", 
        options=["全部"] + available_dates,
        index=0
    )
    
    # 2. Platform Filter
    # Get from global stats
    all_platforms = list(set([s['platform'] for s in global_stats['author_stats']]))
    selected_platforms = st.sidebar.multiselect(
        "📱 平台", 
        options=all_platforms,
        default=[] # Empty means All
    )
    
    # 3. Category Filter
    all_categories = list(set([s.get('category', 'General') for s in global_stats['author_stats']]))
    selected_categories = st.sidebar.multiselect(
        "🏷️ 分类", 
        options=all_categories,
        default=[]
    )
    
    # 4. Source/Author Filter (New)
    # 使用Counter优化：从O(n^2)降到O(n log n)
    author_counter = Counter(s['author'] for s in global_stats['author_stats'])
    # most_common()返回按计数降序排列的列表
    db_authors = [author for author, _ in author_counter.most_common()]
    
    # Also load sources from config (including newly added ones not yet fetched)
    config_authors = []
    try:
        loader = ConfigLoader()
        config = loader.load()
        if config:
            for sub in config.get('subscriptions', []):
                name = sub.get('name')
                if name and name not in db_authors:
                    config_authors.append(name)
    except:
        pass
    
    # Combine: DB authors first, then config-only authors
    all_authors = db_authors + config_authors
    
    selected_authors = st.sidebar.multiselect(
        "👤 订阅源", 
        options=all_authors,
        default=[]
    )
    
    # Construct Filter Dict
    filters = {
        'date': selected_date,
        'platforms': selected_platforms,
        'categories': selected_categories,
        'authors': selected_authors
    }
    
    # --- DATA LOADING & PAGINATION ---
    
    # Initial load to get total count for these filters (limit=1 is enough? No, we need count)
    # Our load_data returns (df, total_count).
    # But wait, load_data fetches metadata for ALL matching rows then slices.
    # So we can just call it with current page offset.
    
    PAGE_SIZE = 30
    
    # We need to maintain page state. If filters change, reset page to 1.
    # Streamlit re-runs script on interaction.
    # We can't easily detect "filter changed" vs "page changed" without session state hacks.
    # Standard Streamlit way: Pagination widget.
    
    # However, we need to know total_items BEFORE rendering pagination.
    # And load_data does the query.
    # Let's call load_data with a large limit? No.
    # Let's separate "get_count" and "get_page"?
    # Our modified load_data returns total_items calculated from FULL filtered list (metadata).
    # So we can call it once for the current page.
    
    # But we don't know the page number yet because number of pages depends on total_items!
    # Chicken and egg.
    # Solution: 
    # 1. Fetch ALL metadata matching filters (cached).
    # 2. Calculate total.
    # 3. Render pagination.
    # 4. Slice DF.
    
    # Let's call load_data with limit=PAGE_SIZE, but we need offset.
    # If we use st.number_input for page, we need min/max.
    # Let's assume page 1 first, get total, then if user is on page 5 but total < 5*30, reset?
    
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 1
        
    # We can use a callback to reset page when filters change?
    # Hard to bind callback to sidebar multiselects directly in a clean way without keys.
    # Let's use session state keys for filters and check if they changed.
    
    filter_state_key = f"{selected_date}_{selected_platforms}_{selected_categories}_{selected_authors}"
    if 'last_filter_state' not in st.session_state:
        st.session_state.last_filter_state = filter_state_key
    
    if st.session_state.last_filter_state != filter_state_key:
        st.session_state.current_page = 1
        st.session_state.last_filter_state = filter_state_key
        # st.rerun() # Optional, but script continues so it's fine
    
    # Now we can calculate offset
    page = st.session_state.current_page
    offset = (page - 1) * PAGE_SIZE
    
    # Load Data
    df, total_items = load_data(limit=PAGE_SIZE, offset=offset, filters=filters)
    
    # Pagination UI
    num_pages = (total_items // PAGE_SIZE) + (1 if total_items % PAGE_SIZE > 0 else 0)
    if num_pages == 0: num_pages = 1
    
    # Ensure current page is valid
    if page > num_pages:
        page = num_pages
        st.session_state.current_page = page
        offset = (page - 1) * PAGE_SIZE
        # Reload with correct offset
        df, total_items = load_data(limit=PAGE_SIZE, offset=offset, filters=filters)

    
    if total_items == 0:
        st.info("👋 没有找到符合条件的文章。")

    # Main Content
    if selected_date == "全部":
        st.title("📚 历史归档查看")
    else:
        st.title(f"📅 订阅日报 ({selected_date})")
    
    # Metrics (Using Global Stats)
    col1, col2, col3 = st.columns(3)
    
    col1.metric("今日更新", f"{global_stats['today']} 条")
    col2.metric("数据库总数", f"{global_stats['total']} 条")
    col3.metric("总订阅源", f"{global_stats['authors']} 个", help="点击查看详情")

    if "subscription_details_open" not in st.session_state:
        st.session_state.subscription_details_open = False

    if st.button("查看/隐藏订阅源详情", key="btn_toggle_subscription_details"):
        st.session_state.subscription_details_open = not st.session_state.subscription_details_open

    if st.session_state.subscription_details_open:
        for stat in global_stats['author_stats']:
            author = stat['author']
            count = stat['count']
            platform = stat['platform']
            current_category = stat.get('category', 'General')

            col_info, col_cat, col_btn = st.columns([0.5, 0.3, 0.2])
            with col_info:
                st.write(f"- **{author}** ({get_platform_label(platform)}): {count} 条")
                st.caption(f"当前分类: {current_category}")

            with col_cat:
                CATEGORIES = ["金融", "AI", "硬件", "时政", "生活", "其他"]
                try:
                    default_idx = CATEGORIES.index(current_category)
                except:
                    default_idx = 0

                new_cat = st.selectbox(
                    "修改分类",
                    options=CATEGORIES,
                    key=f"cat_sel_{author}",
                    index=default_idx,
                    label_visibility="collapsed"
                )

            with col_btn:
                if st.button("更新", key=f"btn_upd_cat_{author}"):
                    if update_subscription_category(author, new_cat):
                        st.success("已更新")
                        time.sleep(0.2)
                        load_data.clear()
                        load_global_stats.clear()
                        st.rerun()
                    else:
                        st.error("失败")

    st.markdown("---")
    
    # --- BATCH FETCH CONTENT HANDLER ---
    # 处理批量抓取正文的触发
    if st.session_state.get('trigger_batch_fetch', False):
        st.session_state['trigger_batch_fetch'] = False
        
        # 获取当前筛选条件下所有文章（不只是当前页）
        with st.spinner("正在准备批量抓取..."):
            # 加载所有符合条件的文章（限制最多50篇）
            all_df, _ = load_data(limit=50, offset=0, filters=filters)
            
            # 筛选出 wechat/rss 平台且内容为空或较短的文章
            articles_to_fetch = []
            for _, row in all_df.iterrows():
                if row.get('platform') in ['wechat', 'rss']:
                    content = row.get('content', '') or ''
                    if len(content) < 100:  # 内容较短才需要抓取
                        articles_to_fetch.append({
                            'url': row.get('url'),
                            'title': row.get('title'),
                            'index': row.name
                        })
            
            if not articles_to_fetch:
                st.info("✅ 当前筛选条件下没有需要抓取正文的文章")
            else:
                urls = [a['url'] for a in articles_to_fetch]
                st.info(f"🚀 开始批量抓取 {len(urls)} 篇文章的正文（最多3个浏览器并发）...")
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 执行批量抓取
                start_time = time.time()
                result = fetch_contents_batch_via_playwright(urls)
                elapsed = time.time() - start_time
                
                # 更新数据库
                db = DatabaseManager()
                updated_count = 0
                failed_updates = []
                
                for item in result['results']:
                    if item.get('success') and item.get('content'):
                        try:
                            db.update_content(item['url'], item['content'])
                            updated_count += 1
                        except Exception as e:
                            failed_updates.append((item['url'], str(e)))
                
                progress_bar.empty()
                status_text.empty()
                
                # 显示结果
                col_stats1, col_stats2, col_stats3 = st.columns(3)
                col_stats1.metric("总计", result['stats']['total'])
                col_stats2.metric("成功", result['stats']['success'], delta=f"{result['stats']['success'] - result['stats']['total']}")
                col_stats3.metric("失败", result['stats']['failed'])
                
                st.success(f"✅ 批量抓取完成！耗时 {elapsed:.1f} 秒，成功更新 {updated_count} 篇文章")
                
                if failed_updates:
                    with st.expander(f"查看 {len(failed_updates)} 个数据库更新失败"):
                        for url, err in failed_updates[:10]:
                            st.caption(f"- {url[:60]}...: {err}")
                
                # 刷新数据
                load_data.clear()
                st.rerun()
    
    # Display Items
    for index, row in df.iterrows():
        with st.container(border=True):
            author_text = str(row.get('author', '') or '')
            title_text = str(row.get('title', '') or '')
            if row.get('platform') == 'wechat' and author_text:
                prefix_cn = f"{author_text}："
                prefix_en = f"{author_text}:"
                if title_text and not (title_text.startswith(prefix_cn) or title_text.startswith(prefix_en)):
                    title_text = prefix_cn + title_text
            title_text = truncate_text(title_text, 60)

            platform_label = get_platform_label(str(row.get('platform', '') or ''))
            platform_class = get_platform_color(str(row.get('platform', '') or ''))
            display_date = format_date(row.get('sort_date'))
            is_article = row.get('platform') in ['wechat', 'rss'] or "/article/" in str(row.get('url')) or "/note/" in str(row.get('url'))
            type_label = "文章/图文" if is_article else "短视频"

            title_html = html.escape(title_text)
            url_html = html.escape(str(row.get('url', '') or ''))
            author_html = html.escape(author_text)
            category_html = html.escape(str(row.get('category', '') or ''))
            date_html = html.escape(str(display_date or ''))
            platform_html = html.escape(platform_label)

            col_left, col_right = st.columns([0.68, 0.32])
            with col_left:
                st.markdown(
                    f"""<span class="card-title"><a href="{url_html}" target="_blank">{title_html}</a></span>""",
                    unsafe_allow_html=True,
                )
            with col_right:
                st.markdown(
                    f"""
<div class="meta-row">
  <span class="platform-tag {platform_class}" style="padding: 0.10rem 0.35rem; font-size: 0.72rem; margin-right: 0;">{platform_html}</span>
  <span class="meta-chip">{author_html}</span>
  <span class="meta-chip">{date_html}</span>
  <span class="meta-chip">{category_html}</span>
  <span class="meta-chip">{type_label}</span>
</div>
""",
                    unsafe_allow_html=True,
                )

            if row.get('subtitle'):
                sub_text = clean_html(str(row.get('subtitle')))
                sub_text = truncate_text(sub_text, 80)
                if sub_text:
                    st.caption(sub_text)

            # AI Summary Section (Collapsed by default)
            with st.expander("💡 核心观点摘要", expanded=False):
                col_sum, col_btn = st.columns([0.85, 0.15])
                
                with col_sum:
                    if row.get('summary'):
                        st.info(f"{row['summary']}")
                    else:
                        st.warning("暂无摘要")
                
                with col_btn:
                    # Unique key for each item
                    if st.button("🔄 重新生成", key=f"btn_regen_{index}", help="重新调用AI生成摘要"):
                        # Initialize session state for manual edit mode if not already set
                        if f'manual_edit_mode_{index}' not in st.session_state:
                            st.session_state[f'manual_edit_mode_{index}'] = True
                            st.rerun()
                    
                    if row['platform'] in ['wechat', 'rss']:
                        if st.button("🧭 抓取正文", key=f"btn_pw_{index}", help="使用模拟浏览器抓取正文并生成摘要"):
                            with st.spinner("正在通过 Playwright 抓取正文..."):
                                res = fetch_content_via_playwright(row['url'])
                                if isinstance(res, dict) and res.get("error"):
                                    st.error(f"抓取失败: {res.get('error')}")
                                else:
                                    fetched_content = res.get("content", "") if isinstance(res, dict) else ""
                                    if not fetched_content or len(fetched_content) < 50:
                                        st.warning("抓取内容过短或为空")
                                    else:
                                        new_summary = regenerate_summary(row['url'], fetched_content, row.get('video_url'))
                                        st.session_state[f'new_summary_{index}'] = new_summary
                                        st.session_state[f'edited_content_{index}'] = fetched_content
                                        st.rerun()

            # Manual Edit Mode
            if st.session_state.get(f'manual_edit_mode_{index}', False):
                st.info("⚠️ 检测到原文内容可能为空或过短，请检查并在下方文本框中补充或粘贴全文，然后点击生成。")
                
                # Text area for manual content input
                # Pre-fill with existing content or empty string
                current_content = row.get('content', '')
                if current_content is None:
                    current_content = ""
                    
                edited_content = st.text_area(
                    "文章正文 (可手动修改):", 
                    value=current_content, 
                    height=200, 
                    key=f"txt_content_{index}"
                )
                
                col_gen_confirm, col_gen_cancel = st.columns(2)
                
                with col_gen_confirm:
                    if st.button("🚀 开始生成", key=f"btn_start_gen_{index}"):
                        with st.spinner("正在基于输入内容生成摘要..."):
                            # Call the isolated script with EDITED content
                            new_summary = regenerate_summary(row['url'], edited_content, row.get('video_url'))
                            
                            # Store in session state to persist after rerun
                            st.session_state[f'new_summary_{index}'] = new_summary
                            # Also store the edited content to update DB later
                            st.session_state[f'edited_content_{index}'] = edited_content
                            # Turn off manual edit mode, move to preview mode
                            del st.session_state[f'manual_edit_mode_{index}']
                            st.rerun()
                            
                with col_gen_cancel:
                    if st.button("❌ 取消编辑", key=f"btn_abort_edit_{index}"):
                        del st.session_state[f'manual_edit_mode_{index}']
                        st.rerun()

            # Check if there is a pending new summary for this item (Preview Mode)
            if f'new_summary_{index}' in st.session_state:
                new_sum = st.session_state[f'new_summary_{index}']
                st.success("✅ 新摘要已生成 (预览):")
                st.info(new_sum)
                
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("💾 确认保存", key=f"btn_save_{index}"):
                        # Update Database
                        try:
                            db = DatabaseManager()
                            # Update Summary
                            summary_updated = db.update_summary(row['url'], new_sum)
                            
                            # Update Content if it was edited
                            content_updated = True
                            if f'edited_content_{index}' in st.session_state:
                                edited_content_val = st.session_state[f'edited_content_{index}']
                                content_updated = db.update_content(row['url'], edited_content_val)

                            if summary_updated and content_updated:
                                st.success("摘要与正文保存成功！")
                                
                                # Clear session state
                                if f'new_summary_{index}' in st.session_state: del st.session_state[f'new_summary_{index}']
                                if f'edited_content_{index}' in st.session_state: del st.session_state[f'edited_content_{index}']
                                
                                load_data.clear() # Clear cache
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("保存失败 (部分或全部)")
                        except Exception as e:
                            st.error(f"保存异常: {e}")
                
                with col_cancel:
                    if st.button("❌ 取消保存", key=f"btn_cancel_{index}"):
                        if f'new_summary_{index}' in st.session_state: del st.session_state[f'new_summary_{index}']
                        if f'edited_content_{index}' in st.session_state: del st.session_state[f'edited_content_{index}']
                        st.rerun()

    if total_items > 0:
        st.markdown("---")
        col_pg1, col_pg2, col_pg3, col_pg4, col_pg5 = st.columns([0.16, 0.34, 0.22, 0.12, 0.16])
        with col_pg1:
            if st.button("⬅️ 上一页", disabled=page == 1, key="btn_page_prev_bottom"):
                st.session_state.current_page -= 1
                st.rerun()
        with col_pg2:
            st.markdown(
                f"<div style='text-align: center'>第 {page} / {num_pages} 页 (共 {total_items} 条)</div>",
                unsafe_allow_html=True,
            )
        with col_pg3:
            # 使用单独的 key 存储跳转输入值，避免与 widget 冲突
            jump_page = st.number_input(
                "跳转到页",
                min_value=1,
                max_value=num_pages,
                value=page,
                step=1,
                key="page_jump_input",
            )
        with col_pg4:
            if st.button("跳转", key="btn_page_jump"):
                st.session_state.current_page = int(jump_page)
                st.rerun()
        with col_pg5:
            if st.button("下一页 ➡️", disabled=page == num_pages, key="btn_page_next_bottom"):
                st.session_state.current_page += 1
                st.rerun()

if __name__ == "__main__":
    main()
