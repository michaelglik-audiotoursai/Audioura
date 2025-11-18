#!/usr/bin/env python3
"""
Test Boston Globe Credentials Authentication
Direct test of login functionality
"""
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def test_boston_globe_login():
    """Test Boston Globe login with provided credentials"""
    
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    print("Testing Boston Globe Login")
    print("=" * 30)
    print(f"Username: {credentials['username']}")
    print(f"Password: {'*' * len(credentials['password'])}")
    
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Step 1: Navigate to Boston Globe login page
        print("\n1. Navigating to Boston Globe login page...")
        driver.get("https://www.bostonglobe.com/login")
        time.sleep(3)
        
        print(f"   Current URL: {driver.current_url}")
        print(f"   Page title: {driver.title}")
        
        # Step 2: Find login form elements
        print("\n2. Looking for login form elements...")
        
        try:
            # Wait for email field
            wait = WebDriverWait(driver, 10)
            email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
            print("   ✅ Email field found")
            
            # Find password field
            password_field = driver.find_element(By.NAME, "password")
            print("   ✅ Password field found")
            
            # Find submit button
            submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            print("   ✅ Submit button found")
            
        except Exception as e:
            print(f"   ❌ Login form elements not found: {e}")
            
            # Try alternative selectors
            print("   🔍 Trying alternative selectors...")
            try:
                email_field = driver.find_element(By.CSS_SELECTOR, "input[type='email']")
                password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button")
                print("   ✅ Alternative selectors worked")
            except Exception as alt_e:
                print(f"   ❌ Alternative selectors failed: {alt_e}")
                print("   📄 Page source preview:")
                print(driver.page_source[:500])
                return False
        
        # Step 3: Enter credentials
        print("\n3. Entering credentials...")
        
        try:
            email_field.clear()
            email_field.send_keys(credentials['username'])
            print("   ✅ Username entered")
            
            password_field.clear()
            password_field.send_keys(credentials['password'])
            print("   ✅ Password entered")
            
        except Exception as e:
            print(f"   ❌ Failed to enter credentials: {e}")
            return False
        
        # Step 4: Submit login
        print("\n4. Submitting login form...")
        
        try:
            original_url = driver.current_url
            submit_button.click()
            print("   ✅ Login form submitted")
            
            # Wait for page to change or error to appear
            time.sleep(5)
            
            new_url = driver.current_url
            print(f"   Original URL: {original_url}")
            print(f"   New URL: {new_url}")
            
        except Exception as e:
            print(f"   ❌ Failed to submit login: {e}")
            return False
        
        # Step 5: Check login result
        print("\n5. Checking login result...")
        
        # Check for success indicators
        success_indicators = [
            "account",
            "dashboard", 
            "profile",
            "subscriber",
            "welcome"
        ]
        
        # Check for error indicators
        error_indicators = [
            "invalid",
            "incorrect",
            "error",
            "failed",
            "try again"
        ]
        
        page_text = driver.page_source.lower()
        current_url = driver.current_url.lower()
        
        # Analyze results
        has_success = any(indicator in page_text or indicator in current_url for indicator in success_indicators)
        has_error = any(indicator in page_text for indicator in error_indicators)
        
        if has_success and not has_error:
            print("   ✅ LOGIN SUCCESSFUL!")
            print("   🎉 Credentials are valid")
            
            # Test accessing a premium article
            print("\n6. Testing premium article access...")
            test_article_url = "https://www.bostonglobe.com/2024/11/12/business/"
            
            try:
                driver.get(test_article_url)
                time.sleep(3)
                
                # Check if we can access content
                article_content = ""
                for selector in ['article', '.story-content', '.article-body']:
                    try:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        if element:
                            article_content = element.text.strip()
                            if len(article_content) > 200:
                                break
                    except:
                        continue
                
                if len(article_content) > 200:
                    print(f"   ✅ Premium content accessible: {len(article_content)} chars")
                    print(f"   📄 Content preview: {article_content[:150]}...")
                    return True
                else:
                    print(f"   ⚠️ Limited content access: {len(article_content)} chars")
                    print("   💡 May still be behind paywall or require additional steps")
                    return "partial"
                    
            except Exception as e:
                print(f"   ❌ Error accessing premium article: {e}")
                return "login_success_but_article_failed"
            
        elif has_error:
            print("   ❌ LOGIN FAILED")
            print("   🔍 Error detected in page response")
            
            # Look for specific error messages
            if "invalid" in page_text or "incorrect" in page_text:
                print("   💡 Likely cause: Invalid credentials")
            elif "captcha" in page_text:
                print("   💡 Likely cause: CAPTCHA required")
            elif "blocked" in page_text or "suspicious" in page_text:
                print("   💡 Likely cause: Account blocked or suspicious activity")
            else:
                print("   💡 Unknown login error")
            
            return False
            
        else:
            print("   ⚠️ LOGIN STATUS UNCLEAR")
            print("   🔍 No clear success or error indicators found")
            print(f"   📄 Page title: {driver.title}")
            
            # Check if we're still on login page
            if "login" in driver.current_url.lower():
                print("   💡 Still on login page - likely failed")
                return False
            else:
                print("   💡 Redirected away from login - possibly successful")
                return "unclear"
        
    except Exception as e:
        print(f"\n❌ Browser automation error: {e}")
        return False
        
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    result = test_boston_globe_login()
    
    print(f"\n" + "=" * 40)
    print("BOSTON GLOBE CREDENTIALS TEST RESULT:")
    
    if result is True:
        print("✅ CREDENTIALS WORK - Full access confirmed")
        print("   Phase 2 browser automation will work")
    elif result == "partial":
        print("⚠️ CREDENTIALS WORK - Limited access")
        print("   Login successful but premium content may need additional steps")
    elif result == "login_success_but_article_failed":
        print("⚠️ LOGIN WORKS - Article access needs investigation")
        print("   Credentials valid but article extraction needs refinement")
    elif result == "unclear":
        print("❓ UNCLEAR RESULT - Manual verification recommended")
        print("   Browser automation worked but results ambiguous")
    else:
        print("❌ CREDENTIALS DON'T WORK - Investigation needed")
        print("   Check credentials, login process, or anti-bot measures")