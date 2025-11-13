#!/usr/bin/env python3
"""
Boston Globe Session-Aware Authentication
Maintains login session for multiple article requests
"""

import time
import logging
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

class BostonGlobeSessionAuth:
    def __init__(self):
        self.driver = None
        self.authenticated = False
        self.session_file = "/tmp/bg_session.pkl"
        
    def create_driver(self):
        """Create persistent Chrome driver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
        
    def authenticate_once(self, username, password):
        """Authenticate once and save session"""
        if not self.driver:
            self.create_driver()
            
        try:
            # Try to load existing session
            if self._load_session():
                logging.info("Loaded existing session")
                return True
                
            # Perform fresh login
            logging.info("Performing fresh login")
            self.driver.get("https://pages.bostonglobe.com/login/")
            time.sleep(5)
            
            # Handle iframe login
            iframe = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[id*='piano-id']"))
            )
            self.driver.switch_to.frame(iframe)
            
            # Fill credentials
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#email"))
            )
            email_field.send_keys(username)
            
            password_field = self.driver.find_element(By.CSS_SELECTOR, "#fieldLoginPassword")
            password_field.send_keys(password)
            
            # Submit login
            login_button = self.driver.find_element(By.CSS_SELECTOR, "#login-submit-btn")
            login_button.click()
            
            self.driver.switch_to.default_content()
            time.sleep(10)
            
            # Save session
            self._save_session()
            self.authenticated = True
            logging.info("Authentication successful, session saved")
            return True
            
        except Exception as e:
            logging.error(f"Authentication failed: {e}")
            return False
            
    def extract_article(self, article_url):
        """Extract article using authenticated session"""
        if not self.authenticated:
            return {"success": False, "error": "Not authenticated"}
            
        try:
            self.driver.get(article_url)
            time.sleep(5)
            
            # Enhanced content extraction
            content = self._extract_content()
            
            if len(content) < 100:
                return {"success": False, "error": f"Insufficient content: {len(content)} chars"}
                
            return {"success": True, "content": content}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def _extract_content(self):
        """Extract article content with Boston Globe specific selectors"""
        selectors = [
            ".story-body-text p",
            ".article-body p", 
            "[data-module='ArticleBody'] p",
            ".paywall-content p",
            "article p"
        ]
        
        best_content = ""
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    content = " ".join([el.text.strip() for el in elements if el.text.strip()])
                    if len(content) > len(best_content):
                        best_content = content
                        logging.info(f"Content found with {selector}: {len(content)} chars")
            except:
                continue
                
        return best_content
        
    def _save_session(self):
        """Save browser cookies and session data"""
        try:
            session_data = {
                'cookies': self.driver.get_cookies(),
                'local_storage': self.driver.execute_script("return window.localStorage;"),
                'session_storage': self.driver.execute_script("return window.sessionStorage;")
            }
            with open(self.session_file, 'wb') as f:
                pickle.dump(session_data, f)
        except Exception as e:
            logging.warning(f"Failed to save session: {e}")
            
    def _load_session(self):
        """Load saved session data"""
        try:
            with open(self.session_file, 'rb') as f:
                session_data = pickle.load(f)
                
            # Navigate to Boston Globe first
            self.driver.get("https://www.bostonglobe.com")
            time.sleep(2)
            
            # Restore cookies
            for cookie in session_data['cookies']:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    continue
                    
            # Restore storage
            for key, value in session_data.get('local_storage', {}).items():
                self.driver.execute_script(f"window.localStorage.setItem('{key}', '{value}');")
                
            self.authenticated = True
            return True
            
        except Exception as e:
            logging.info(f"No valid session found: {e}")
            return False
            
    def close(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def test_session_auth():
    """Test session-aware authentication"""
    auth = BostonGlobeSessionAuth()
    
    # Authenticate once
    success = auth.authenticate_once("glikfamily@gmail.com", "Eight2Four")
    if not success:
        print("Authentication failed")
        return
        
    # Test multiple articles with same session
    test_urls = [
        "https://www.bostonglobe.com/2024/11/13/business/",
        "https://www.bostonglobe.com/2024/11/12/business/"
    ]
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        result = auth.extract_article(url)
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Content: {len(result['content'])} chars")
            print(f"Preview: {result['content'][:200]}...")
        else:
            print(f"Error: {result['error']}")
            
    auth.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_session_auth()