#!/usr/bin/env python3
"""
NY Times Undetected Chrome Authentication
Uses undetected-chromedriver to bypass DataDome protection
"""

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import logging

class NYTimesUndetectedAuth:
    def __init__(self):
        self.driver = None
        
    def create_undetected_driver(self):
        """Create undetected Chrome driver"""
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--no-first-run')
        options.add_argument('--disable-default-apps')
        
        self.driver = uc.Chrome(options=options, version_main=None)
        return self.driver
    
    def authenticate_and_extract(self, article_url, username, password):
        """Authenticate with NY Times and extract article content"""
        try:
            if not self.driver:
                self.create_undetected_driver()
            
            # Navigate to login page
            self.driver.get("https://myaccount.nytimes.com/auth/login")
            time.sleep(3)
            
            # Fill login form
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_field.send_keys(username)
            
            password_field = self.driver.find_element(By.ID, "password")
            password_field.send_keys(password)
            
            # Submit login
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            
            # Wait for login to complete
            time.sleep(5)
            
            # Navigate to article
            self.driver.get(article_url)
            time.sleep(5)
            
            # Extract article content
            content = self.driver.execute_script("""
                var selectors = [
                    'section[name="articleBody"]',
                    '.StoryBodyCompanionColumn',
                    '[data-module="ArticleBody"]',
                    '.css-53u6y8',
                    'section.meteredContent'
                ];
                
                for (var i = 0; i < selectors.length; i++) {
                    var elements = document.querySelectorAll(selectors[i]);
                    if (elements.length > 0) {
                        var text = '';
                        for (var j = 0; j < elements.length; j++) {
                            text += elements[j].innerText + '\\n\\n';
                        }
                        if (text.length > 500) {
                            return text;
                        }
                    }
                }
                return document.body.innerText;
            """)
            
            if content and len(content) > 500:
                return {'success': True, 'content': content}
            else:
                return {'success': False, 'error': 'Insufficient content extracted'}
                
        except Exception as e:
            logging.error(f"Undetected Chrome authentication failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def test_undetected_auth():
    """Test undetected Chrome authentication"""
    auth = NYTimesUndetectedAuth()
    
    test_article = "https://www.nytimes.com/2025/11/24/us/politics/mark-kelly-pentagon-investigation.html"
    username = "glikfamily@gmail.com"
    password = "Eight6Nine8"
    
    result = auth.authenticate_and_extract(test_article, username, password)
    
    if result['success']:
        print(f"✅ Authentication successful: {len(result['content'])} characters")
        print(f"Preview: {result['content'][:200]}...")
    else:
        print(f"❌ Authentication failed: {result['error']}")
    
    auth.cleanup()

if __name__ == "__main__":
    test_undetected_auth()