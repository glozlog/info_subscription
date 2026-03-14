import subprocess
import sys
import json
import os

def test_regenerate():
    url = "http://test.com"
    content = "This is a test content."
    video_url = None
    
    input_data = {
        "url": url,
        "content": content,
        "video_url": video_url
    }
    
    json_input = json.dumps(input_data, ensure_ascii=False)
    
    cmd = [sys.executable, "generate_summary.py"]
    print(f"Executing: {cmd}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        stdout, stderr = process.communicate(input=json_input)
        
        print(f"Exit Code: {process.returncode}")
        print(f"STDOUT: {stdout}")
        print(f"STDERR: {stderr}")
        
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_regenerate()
