#!/usr/bin/env python3
"""
NY Times Cookie-Based Authentication Module
Uses imported session cookies to access subscription content with undetected Chrome
"""

import json
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time

class NYTimesAuthenticator:
    def __init__(self, cookies_file="NYTimes_Cookies.json"):
        self.cookies_file = cookies_file
        self.session = None
        self.driver = None
        
    def load_cookies(self):
        """Load NY Times session cookies from JSON file"""
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            logging.info(f"Loaded {len(cookies)} NY Times session cookies")
            return cookies
        except Exception as e:
            logging.error(f"Failed to load cookies: {e}")
            return []
    
    def create_authenticated_session(self):
        """Create requests session with NY Times cookies"""
        self.session = requests.Session()
        
        # Load and add cookies
        cookies = self.load_cookies()
        for cookie in cookies:
            self.session.cookies.set(
                name=cookie['name'],
                value=cookie['value'],
                domain=cookie['domain'],
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', True)
            )
        
        # Set realistic headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        })
        
        logging.info("Created authenticated session with NY Times cookies")
        return self.session
    
    def test_authentication(self, test_url="https://www.nytimes.com/section/us"):
        """Test if authentication is working"""
        if not self.session:
            self.create_authenticated_session()
        
        try:
            response = self.session.get(test_url, timeout=30)
            content = response.text.lower()
            
            # Check for subscription indicators
            if 'subscriber' in content or 'account' in content:
                logging.info("✅ NY Times authentication successful - subscriber content detected")
                return True
            elif 'subscribe' in content and 'paywall' not in content:
                logging.info("✅ NY Times authentication working - logged in user detected")
                return True
            else:
                logging.warning("⚠️ NY Times authentication unclear - may need verification")
                return False
                
        except Exception as e:
            logging.error(f"Authentication test failed: {e}")
            return False
    
    def extract_article_content(self, article_url):
        """Extract full article content using authenticated session"""
        if not self.session:
            self.create_authenticated_session()
        
        try:
            response = self.session.get(article_url, timeout=30)
            content = response.text
            
            # Check for paywall indicators
            if 'preview view of this article' in content.lower():
                logging.warning("⚠️ Still seeing paywall preview - trying undetected Chrome")
                return self._extract_with_undetected_chrome(article_url)
            
            # Extract article content using multiple selectors
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # NY Times article selectors
            selectors = [
                'section[name="articleBody"]',
                '.StoryBodyCompanionColumn',
                '[data-module="ArticleBody"]',
                '.css-53u6y8',  # Common NY Times article class
                'section.meteredContent',
                '.ArticleBody-articleBody'
            ]
            
            article_text = ""
            for selector in selectors:
                elements = soup.select(selector)
                if elements:
                    for element in elements:
                        article_text += element.get_text(strip=True) + "\n\n"
                    break
            
            if article_text and len(article_text) > 500:
                logging.info(f"✅ Extracted {len(article_text)} chars from NY Times article")
                return article_text.strip()
            else:
                logging.warning("⚠️ Limited content extracted, trying undetected Chrome fallback")
                return self._extract_with_undetected_chrome(article_url)
                
        except Exception as e:
            logging.error(f"Content extraction failed: {e}")
            return self._extract_with_undetected_chrome(article_url)
    
    def _extract_with_undetected_chrome(self, article_url):
        """Fallback extraction using undetected Chrome with cookies"""
        try:
            # Create undetected Chrome driver
            chrome_options = uc.ChromeOptions()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            
            driver = uc.Chrome(options=chrome_options)
            
            # Navigate to NY Times first to set domain
            driver.get("https://www.nytimes.com")
            time.sleep(2)
            
            # Add cookies
            cookies = self.load_cookies()
            for cookie in cookies:
                try:
                    driver.add_cookie({
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': cookie['domain'],
                        'path': cookie.get('path', '/'),
                        'secure': cookie.get('secure', True),
                        'httpOnly': cookie.get('httpOnly', False)
                    })
                except Exception as e:
                    logging.warning(f"Failed to add cookie {cookie['name']}: {e}")
            
            # Navigate to article
            driver.get(article_url)
            time.sleep(5)  # Wait for dynamic content
            
            # Extract content using JavaScript
            article_text = driver.execute_script("""
                var selectors = [
                    'section[name="articleBody"]',
                    '.StoryBodyCompanionColumn', 
                    '[data-module="ArticleBody"]',
                    '.css-53u6y8',
                    'section.meteredContent',
                    '.ArticleBody-articleBody'
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
                
                // Fallback: get all paragraph text
                var paragraphs = document.querySelectorAll('p');
                var text = '';
                for (var i = 0; i < paragraphs.length; i++) {
                    if (paragraphs[i].innerText.length > 50) {
                        text += paragraphs[i].innerText + '\\n\\n';
                    }
                }
                return text;
            """)
            
            driver.quit()
            
            if article_text and len(article_text) > 500:
                logging.info(f"✅ Undetected Chrome extracted {len(article_text)} chars from NY Times article")
                return article_text.strip()
            else:
                logging.error("❌ Undetected Chrome extraction failed - insufficient content")
                return None
                
        except Exception as e:
            logging.error(f"Undetected Chrome extraction failed: {e}")
            return None
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
        if self.session:
            self.session.close()

def test_nytimes_authentication():
    """Test NY Times cookie authentication"""
    auth = NYTimesAuthenticator()
    
    # Test authentication
    if auth.test_authentication():
        print("✅ NY Times authentication working")
        
        # Test article extraction
        test_article = "https://www.nytimes.com/2025/11/24/us/politics/mark-kelly-pentagon-investigation.html"
        content = auth.extract_article_content(test_article)
        
        if content:
            print(f"✅ Article content extracted: {len(content)} characters")
            print(f"Preview: {content[:200]}...")
        else:
            print("❌ Article content extraction failed")
    else:
        print("❌ NY Times authentication failed")
    
    auth.cleanup()

if __name__ == "__main__":
    test_nytimes_authentication()