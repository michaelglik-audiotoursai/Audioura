#!/usr/bin/env python3
"""
Debug NY Times Login Page
"""
import sys
sys.path.append('/app')

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def debug_nytimes_login():
    """Debug NY Times login page structure"""
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print("Loading NY Times login page...")
        driver.get("https://myaccount.nytimes.com/auth/login")
        time.sleep(5)
        
        print(f"Current URL: {driver.current_url}")
        print(f"Page title: {driver.title}")
        
        # Get page source and look for form elements
        page_source = driver.page_source
        
        # Look for input fields
        if 'email' in page_source.lower():
            print("✅ Found 'email' in page source")
        if 'password' in page_source.lower():
            print("✅ Found 'password' in page source")
        if 'login' in page_source.lower():
            print("✅ Found 'login' in page source")
            
        # Save page source for analysis
        with open('/app/nytimes_login_debug.html', 'w', encoding='utf-8') as f:
            f.write(page_source)
        print("✅ Page source saved to /app/nytimes_login_debug.html")
        
    except Exception as e:
        print(f"❌ Debug error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    debug_nytimes_login()