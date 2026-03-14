import argparse
import sys
import os
import json
import traceback

# Ensure src is in path
sys.path.append(os.getcwd())

# Setup logging function
def log_error(msg):
    try:
        with open("summary_error.log", "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except:
        pass

# Debug: Log sys.executable and sys.path
log_error(f"DEBUG: sys.executable: {sys.executable}")
log_error(f"DEBUG: sys.path: {sys.path}")

try:
    from src.summarizer.llm_summarizer import OpenAISummarizer
    from src.utils.config_loader import ConfigLoader
except Exception as e:
    sys.stderr.write(f"Import Error: {e}\n")
    log_error(f"Import Error: {e}\n{traceback.format_exc()}")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate AI Summary for a specific content.")
    parser.add_argument("--url", help="URL of the content")
    parser.add_argument("--content", help="Text content (optional if passed via stdin)")
    parser.add_argument("--video_url", help="Video URL if available")
    
    args = parser.parse_args()
    
    url = args.url
    content = args.content
    video_url = args.video_url
    
    # Check if data is passed via stdin (for handling large content)
    if not sys.stdin.isatty():
        try:
            stdin_data = sys.stdin.read().strip()
            if stdin_data:
                data = json.loads(stdin_data)
                url = data.get('url', url)
                content = data.get('content', content)
                video_url = data.get('video_url', video_url)
        except json.JSONDecodeError:
            log_error(f"JSON Decode Error. Raw input: {stdin_data[:100]}...")
            pass
            
    if not content and not video_url:
        msg = "Error: Content or Video URL is required."
        sys.stderr.write(msg + "\n")
        log_error(msg)
        if not sys.stdin.isatty():
            log_error(f"Debug - Stdin used but content empty. content={bool(content)}, video_url={bool(video_url)}")
        sys.exit(1)
    
    try:
        # Load config
        config_loader = ConfigLoader()
        config = config_loader.load()
        summarizer_config = config.get('summarizer', {})
        
        api_key = summarizer_config.get('api_key')
        base_url = summarizer_config.get('base_url')
        model = summarizer_config.get('model', 'gpt-3.5-turbo')
        provider = summarizer_config.get('provider', 'openai')
        
        if not api_key:
            sys.stderr.write("Error: API Key not configured.\n")
            log_error("Error: API Key not configured.")
            sys.exit(1)
            
        summarizer = OpenAISummarizer(api_key=api_key, base_url=base_url, model=model, provider=provider)
        
        # Generate summary
        summary = summarizer.summarize(content, video_url=video_url)
        
        # Output ONLY the summary to stdout
        # Ensure encoding is handled correctly
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
            
        print(summary)
        
    except Exception as e:
        sys.stderr.write(f"Error: {str(e)}\n")
        log_error(f"Error: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
