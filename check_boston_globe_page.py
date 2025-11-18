#!/usr/bin/env python3
"""
Check Boston Globe login page structure
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

def check_boston_globe_page():
    """Check what's actually on the Boston Globe login page"""
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        print("Checking Boston Globe login page...")
        driver.get("https://www.bostonglobe.com/login")
        time.sleep(5)  # Wait for page to fully load
        
        print(f"Final URL: {driver.current_url}")
        print(f"Page title: {driver.title}")
        
        # Check for various input types
        inputs = driver.find_elements("tag name", "input")
        print(f"\nFound {len(inputs)} input elements:")
        
        for i, inp in enumerate(inputs):
            input_type = inp.get_attribute("type") or "text"
            input_name = inp.get_attribute("name") or "unnamed"
            input_id = inp.get_attribute("id") or "no-id"
            input_placeholder = inp.get_attribute("placeholder") or ""
            
            print(f"  {i+1}. Type: {input_type}, Name: {input_name}, ID: {input_id}")
            if input_placeholder:
                print(f"      Placeholder: {input_placeholder}")
        
        # Check for buttons
        buttons = driver.find_elements("tag name", "button")
        print(f"\nFound {len(buttons)} button elements:")
        
        for i, btn in enumerate(buttons):
            btn_type = btn.get_attribute("type") or "button"
            btn_text = btn.text.strip()
            btn_class = btn.get_attribute("class") or ""
            
            print(f"  {i+1}. Type: {btn_type}, Text: '{btn_text}', Class: {btn_class}")
        
        # Check for forms
        forms = driver.find_elements("tag name", "form")
        print(f"\nFound {len(forms)} form elements")
        
        # Look for any text that might indicate login
        page_text = driver.page_source.lower()
        login_keywords = ["email", "password", "username", "sign in", "log in", "login"]
        
        print(f"\nLogin-related keywords found:")
        for keyword in login_keywords:
            if keyword in page_text:
                print(f"  ✅ '{keyword}' found in page")
            else:
                print(f"  ❌ '{keyword}' not found")
        
        # Check if this is a redirect or different login system
        if "auth.bostonglobe.com" in driver.current_url:
            print(f"\n🔍 Redirected to auth subdomain - different login system")
        
        # Save page source for analysis
        with open("/app/boston_globe_login_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"\n📄 Page source saved to /app/boston_globe_login_page.html")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False
        
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    check_boston_globe_page()