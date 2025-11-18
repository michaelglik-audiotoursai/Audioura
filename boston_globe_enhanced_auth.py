#!/usr/bin/env python3
"""
Enhanced Boston Globe Authentication System
Handles iframe-based login and post-login content extraction
"""

import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import requests
from bs4 import BeautifulSoup

class BostonGlobeEnhancedAuth:
    def __init__(self):
        self.driver = None
        self.session = requests.Session()
        
    def create_driver(self):
        """Create enhanced Chrome driver with stealth options"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Enhanced stealth options
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self.driver
        
    def authenticate_and_extract(self, article_url, username, password):
        """
        Authenticate with Boston Globe and extract article content
        Returns: dict with success status and content
        """
        try:
            if not self.driver:
                self.create_driver()
                
            logging.info(f"Starting Boston Globe authentication for: {article_url}")
            
            # Step 1: Navigate to article URL
            self.driver.get(article_url)
            time.sleep(3)
            
            # Step 2: Check if we need to login (look for paywall or login prompt)
            if self._needs_authentication():
                logging.info("Authentication required, proceeding with login")
                
                # Step 3: Navigate to login page
                login_success = self._perform_login(username, password)
                if not login_success:
                    return {"success": False, "error": "Login failed"}
                    
                # Step 4: Navigate back to article after successful login
                logging.info("Login successful, navigating back to article")
                self.driver.get(article_url)
                time.sleep(5)  # Wait for page to load with authenticated session
                
            # Step 5: Extract article content
            content = self._extract_article_content()
            
            if len(content) < 100:
                return {"success": False, "error": f"Insufficient content extracted: {len(content)} chars"}
                
            logging.info(f"Successfully extracted {len(content)} characters")
            return {"success": True, "content": content}
            
        except Exception as e:
            logging.error(f"Boston Globe authentication error: {str(e)}")
            return {"success": False, "error": str(e)}
        finally:
            if self.driver:
                self.driver.quit()
                
    def _needs_authentication(self):
        """Check if the page requires authentication"""
        try:
            # Look for common paywall indicators
            paywall_indicators = [
                "subscribe",
                "paywall",
                "premium",
                "subscriber",
                "login",
                "sign in"
            ]
            
            page_text = self.driver.page_source.lower()
            for indicator in paywall_indicators:
                if indicator in page_text:
                    logging.info(f"Paywall indicator found: {indicator}")
                    return True
                    
            # Check for specific Boston Globe paywall elements
            paywall_selectors = [
                ".paywall",
                ".subscription-required",
                ".premium-content",
                "[data-paywall]"
            ]
            
            for selector in paywall_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        logging.info(f"Paywall element found: {selector}")
                        return True
                except NoSuchElementException:
                    continue
                    
            return False
            
        except Exception as e:
            logging.warning(f"Error checking authentication need: {e}")
            return True  # Assume authentication needed if we can't determine
            
    def _perform_login(self, username, password):
        """Perform the actual login process"""
        try:
            # Navigate to Boston Globe login page
            login_url = "https://pages.bostonglobe.com/login/"
            logging.info(f"Navigating to login page: {login_url}")
            self.driver.get(login_url)
            time.sleep(5)
            
            # Wait for iframe to load
            iframe_selector = "iframe[id*='piano-id']"
            wait = WebDriverWait(self.driver, 30)
            iframe = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, iframe_selector)))
            
            logging.info("Switching to iframe")
            self.driver.switch_to.frame(iframe)
            time.sleep(3)
            
            # Find and fill email field
            email_selectors = [
                "#email",
                "input[type='email']",
                "input[name='email']",
                "input[fieldusername]"
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except TimeoutException:
                    continue
                    
            if not email_field:
                return False
                
            logging.info("Filling email field")
            email_field.clear()
            self._human_type(email_field, username)
            time.sleep(1)
            
            # Find and fill password field
            password_selectors = [
                "#fieldLoginPassword",
                "input[type='password']",
                "input[name='password']",
                "input[fieldloginpassword]"
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue
                    
            if not password_field:
                return False
                
            logging.info("Filling password field")
            password_field.clear()
            self._human_type(password_field, password)
            time.sleep(1)
            
            # Find and click login button
            login_selectors = [
                "#login-submit-btn",
                "button[actionlogin]",
                "button[type='submit']",
                ".btn.prime"
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue
                    
            if not login_button:
                return False
                
            logging.info("Clicking login button")
            login_button.click()
            time.sleep(5)
            
            # Switch back to main content
            self.driver.switch_to.default_content()
            
            # Wait for login to complete (look for redirect or success indicators)
            time.sleep(10)
            
            # Check if login was successful
            current_url = self.driver.current_url
            if "login" not in current_url.lower() or "dashboard" in current_url.lower():
                logging.info("Login appears successful")
                return True
            else:
                logging.warning("Login may have failed - still on login page")
                return False
                
        except Exception as e:
            logging.error(f"Login process error: {str(e)}")
            return False
            
    def _human_type(self, element, text):
        """Type text with human-like delays"""
        for char in text:
            element.send_keys(char)
            time.sleep(0.05 + (0.1 * (len(char) % 3)))  # Variable delay
            
    def _extract_article_content(self):
        """Extract article content from the page"""
        try:
            # Wait for content to load
            time.sleep(5)
            
            # Boston Globe article content selectors
            content_selectors = [
                ".article-content",
                ".story-content",
                ".entry-content",
                "[data-module='ArticleBody']",
                ".article-body",
                ".story-body",
                ".content-body",
                "main article",
                ".post-content"
            ]
            
            content_text = ""
            
            for selector in content_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.get_attribute('textContent') or element.text
                        if text and len(text) > len(content_text):
                            content_text = text
                            logging.info(f"Found content with selector {selector}: {len(text)} chars")
                except Exception as e:
                    logging.debug(f"Selector {selector} failed: {e}")
                    continue
                    
            # If no specific selectors work, try general content extraction
            if len(content_text) < 100:
                try:
                    # Get all paragraph text
                    paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                    paragraph_text = " ".join([p.text for p in paragraphs if p.text])
                    
                    if len(paragraph_text) > len(content_text):
                        content_text = paragraph_text
                        logging.info(f"Using paragraph extraction: {len(content_text)} chars")
                        
                except Exception as e:
                    logging.debug(f"Paragraph extraction failed: {e}")
                    
            # Clean and return content
            content_text = content_text.strip()
            
            # Save debug HTML if content is insufficient
            if len(content_text) < 100:
                debug_file = "/tmp/boston_globe_post_login_debug.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                logging.info(f"Saved debug HTML to {debug_file}")
                
            return content_text
            
        except Exception as e:
            logging.error(f"Content extraction error: {str(e)}")
            return ""

def test_boston_globe_auth():
    """Test the enhanced Boston Globe authentication"""
    auth = BostonGlobeEnhancedAuth()
    
    # Test credentials
    username = "glikfamily@gmail.com"
    password = "Eight2Four"
    test_url = "https://www.bostonglobe.com/2024/11/13/business/"
    
    print("Testing Enhanced Boston Globe Authentication")
    print(f"URL: {test_url}")
    print(f"Username: {username}")
    
    result = auth.authenticate_and_extract(test_url, username, password)
    
    print(f"\nResult: {result}")
    
    if result["success"]:
        print(f"Content length: {len(result['content'])} characters")
        print(f"Content preview: {result['content'][:200]}...")
    else:
        print(f"Error: {result['error']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_boston_globe_auth()