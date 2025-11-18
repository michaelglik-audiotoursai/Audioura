#!/usr/bin/env python3
"""
Boston Globe Authentication Debugger with HTML Page Capture
Saves HTML pages at each step for manual analysis
"""
import logging
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class BostonGlobeDebugger:
    def __init__(self, save_html_dir="boston_globe_html_debug"):
        self.save_html_dir = save_html_dir
        self.setup_logging()
        self.ensure_html_dir()
        
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def ensure_html_dir(self):
        """Create directory for HTML debugging files"""
        if not os.path.exists(self.save_html_dir):
            os.makedirs(self.save_html_dir)
            
    def save_html_page(self, driver, step_name, description=""):
        """Save current page HTML for debugging"""
        try:
            timestamp = time.strftime("%H%M%S")
            filename = f"{timestamp}_{step_name}.html"
            filepath = os.path.join(self.save_html_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"<!-- {description} -->\n")
                f.write(f"<!-- URL: {driver.current_url} -->\n")
                f.write(f"<!-- Title: {driver.title} -->\n")
                f.write(driver.page_source)
                
            self.logger.info(f"HTML saved: {filepath}")
            print(f"📄 HTML Page Saved: {filepath}")
            if description:
                print(f"   Description: {description}")
            print(f"   URL: {driver.current_url}")
            print(f"   Title: {driver.title}")
            
        except Exception as e:
            self.logger.error(f"Failed to save HTML: {e}")
            
    def create_enhanced_driver(self):
        """Create Chrome driver with enhanced stealth features"""
        chrome_options = Options()
        
        # For debugging, don't use headless mode so we can see what's happening
        # chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--window-size=1920,1080')
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
        
    def debug_boston_globe_login_flow(self, credentials):
        """Debug the complete Boston Globe login flow with HTML capture"""
        driver = None
        try:
            print("🚀 Starting Boston Globe Login Flow Debug")
            print("=" * 60)
            
            driver = self.create_enhanced_driver()
            
            # Step 1: Navigate to login page
            print("\n📍 Step 1: Navigating to Boston Globe login page")
            login_url = "https://www.bostonglobe.com/login"
            driver.get(login_url)
            time.sleep(3)
            
            self.save_html_page(driver, "01_initial_login_page", 
                              "Initial Boston Globe login page after navigation")
            
            # Step 2: Wait for page to load
            print("\n📍 Step 2: Waiting for page to fully load")
            time.sleep(5)
            
            self.save_html_page(driver, "02_after_page_load", 
                              "Login page after 5 second wait for JavaScript")
            
            # Step 3: Analyze page structure
            print("\n📍 Step 3: Analyzing page structure")
            self.analyze_page_structure(driver)
            
            # Step 4: Look for login forms
            print("\n📍 Step 4: Searching for login form elements")
            email_field, password_field = self.find_login_elements(driver)
            
            if email_field and password_field:
                print("✅ Found login form elements!")
                
                # Step 5: Fill credentials
                print("\n📍 Step 5: Filling login credentials")
                email_field.clear()
                email_field.send_keys(credentials['username'])
                time.sleep(1)
                
                password_field.clear()
                password_field.send_keys(credentials['password'])
                time.sleep(1)
                
                self.save_html_page(driver, "03_credentials_filled", 
                                  "Login form with credentials filled")
                
                # Step 6: Find and click submit
                print("\n📍 Step 6: Looking for submit button")
                submit_button = self.find_submit_button(driver)
                
                if submit_button:
                    print("✅ Found submit button!")
                    print(f"Button text: '{submit_button.text}'")
                    
                    submit_button.click()
                    time.sleep(3)
                    
                    self.save_html_page(driver, "04_after_submit", 
                                      "Page after clicking submit button")
                    
                    # Step 7: Check for redirects or errors
                    print("\n📍 Step 7: Checking for redirects or authentication")
                    time.sleep(5)
                    
                    self.save_html_page(driver, "05_final_result", 
                                      f"Final page after authentication attempt - URL: {driver.current_url}")
                    
                    # Check if we're still on login page
                    if '/login' in driver.current_url:
                        print("⚠️  Still on login page - authentication may have failed")
                        self.check_for_error_messages(driver)
                    else:
                        print(f"✅ Redirected to: {driver.current_url}")
                        
                else:
                    print("❌ Could not find submit button")
                    self.save_html_page(driver, "03_no_submit_button", 
                                      "Could not find submit button")
                    
            else:
                print("❌ Could not find login form elements")
                self.save_html_page(driver, "02_no_login_form", 
                                  "Could not find email/password fields")
                
            # Keep browser open for manual inspection
            print(f"\n🔍 HTML files saved to: {os.path.abspath(self.save_html_dir)}")
            print("📋 Browser will stay open for 30 seconds for manual inspection...")
            time.sleep(30)
            
        except Exception as e:
            print(f"❌ Debug session failed: {e}")
            if driver:
                self.save_html_page(driver, "error_state", f"Error occurred: {str(e)}")
        finally:
            if driver:
                driver.quit()
                
    def analyze_page_structure(self, driver):
        """Analyze the page structure and report findings"""
        try:
            # Check for common elements
            forms = driver.find_elements(By.TAG_NAME, "form")
            inputs = driver.find_elements(By.TAG_NAME, "input")
            buttons = driver.find_elements(By.TAG_NAME, "button")
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            
            print(f"   📊 Page Analysis:")
            print(f"      Forms found: {len(forms)}")
            print(f"      Input fields: {len(inputs)}")
            print(f"      Buttons: {len(buttons)}")
            print(f"      iFrames: {len(iframes)}")
            
            # Check for specific login indicators
            page_source = driver.page_source.lower()
            login_indicators = ['email', 'password', 'sign in', 'log in', 'login']
            found_indicators = [indicator for indicator in login_indicators if indicator in page_source]
            print(f"      Login indicators found: {found_indicators}")
            
            # Check for third-party auth
            auth_domains = ['auth.bostonglobe.com', 'tinypass.com', 'piano.io']
            found_auth = [domain for domain in auth_domains if domain in page_source]
            if found_auth:
                print(f"      Third-party auth detected: {found_auth}")
                
        except Exception as e:
            print(f"   ❌ Page analysis failed: {e}")
            
    def find_login_elements(self, driver):
        """Find login form elements with detailed reporting"""
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[id*="email"]',
            'input[placeholder*="email"]'
        ]
        
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="password"]'
        ]
        
        email_field = None
        password_field = None
        
        print("   🔍 Searching for email field...")
        for selector in email_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        email_field = element
                        print(f"      ✅ Found email field: {selector}")
                        break
                if email_field:
                    break
            except Exception as e:
                print(f"      ❌ Selector failed: {selector} - {e}")
                
        print("   🔍 Searching for password field...")
        for selector in password_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        password_field = element
                        print(f"      ✅ Found password field: {selector}")
                        break
                if password_field:
                    break
            except Exception as e:
                print(f"      ❌ Selector failed: {selector} - {e}")
                
        return email_field, password_field
        
    def find_submit_button(self, driver):
        """Find submit button with detailed reporting"""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:contains("Sign In")',
            'button:contains("Log In")',
            '.login-button',
            '.submit-button'
        ]
        
        print("   🔍 Searching for submit button...")
        for selector in submit_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        print(f"      ✅ Found submit button: {selector}")
                        print(f"         Text: '{element.text}'")
                        return element
            except Exception as e:
                print(f"      ❌ Selector failed: {selector} - {e}")
                
        # Look for any button with login-related text
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                if button.is_displayed() and button.is_enabled():
                    button_text = button.text.lower()
                    if any(word in button_text for word in ["sign", "log", "submit", "continue"]):
                        print(f"      ✅ Found potential submit button by text: '{button.text}'")
                        return button
        except Exception as e:
            print(f"      ❌ Button search failed: {e}")
            
        return None
        
    def check_for_error_messages(self, driver):
        """Check for error messages on the page"""
        error_selectors = [
            '.error',
            '.alert',
            '.warning',
            '[class*="error"]',
            '[class*="alert"]'
        ]
        
        print("   🔍 Checking for error messages...")
        for selector in error_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.text.strip():
                        print(f"      ⚠️  Error message found: {element.text}")
            except Exception as e:
                continue

def main():
    """Run Boston Globe authentication debugging"""
    print("🔍 BOSTON GLOBE AUTHENTICATION DEBUGGER")
    print("This will capture HTML pages at each step for analysis")
    print("=" * 60)
    
    # Test credentials
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    debugger = BostonGlobeDebugger()
    debugger.debug_boston_globe_login_flow(credentials)
    
    print("\n✅ Debug session complete!")
    print(f"📁 HTML files saved to: {os.path.abspath(debugger.save_html_dir)}")
    print("📋 You can now examine the HTML files to understand the login flow")

if __name__ == "__main__":
    main()