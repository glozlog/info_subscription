
import os
from playwright.sync_api import sync_playwright

def manual_login():
    """
    Launch a browser for manual login.
    Saves state to 'douyin_test/browser_data'.
    """
    user_data_dir = os.path.abspath("douyin_test/browser_data")
    if not os.path.exists(user_data_dir):
        os.makedirs(user_data_dir)
        
    print(f"Launching LOGIN browser... (Data dir: {user_data_dir})")
    print("Please scan QR code or login manually.")
    print("Close the browser window when finished.")
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome", # Try real chrome
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.douyin.com/")
        
        # Wait until closed
        try:
            page.wait_for_timeout(300000)
        except:
            pass
            
        context.close()
        print("Login session saved.")

if __name__ == "__main__":
    manual_login()
