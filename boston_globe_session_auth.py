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
        """Extract article using authenticated session with enhanced tracking URL handling"""
        if not self.authenticated:
            return {"success": False, "error": "Not authenticated"}
            
        try:
            # Enhanced Boston Globe tracking URL handling
            if 'click.email.bostonglobe.com' in article_url:
                # Follow redirect chain manually with enhanced validation
                import requests
                session = requests.Session()
                
                # Add cookies from browser to requests session
                for cookie in self.driver.get_cookies():
                    try:
                        session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
                    except Exception as cookie_error:
                        logging.debug(f"Cookie error: {cookie_error}")
                        continue
                
                # Follow redirects with multiple attempts
                max_redirects = 5
                current_url = article_url
                
                for redirect_attempt in range(max_redirects):
                    try:
                        response = session.get(current_url, allow_redirects=True, timeout=10)
                        final_url = response.url
                        
                        # Validate redirect destination
                        if self._is_valid_boston_globe_url(final_url):
                            logging.info(f"Valid Boston Globe redirect: {article_url} -> {final_url}")
                            article_url = final_url
                            break
                        elif self._is_external_advertising_url(final_url):
                            logging.warning(f"External advertising redirect detected: {final_url}")
                            return {"success": False, "error": f"Tracking URL redirects to external advertising site: {final_url}"}
                        else:
                            # Try to extract Boston Globe URL from redirect chain
                            bg_url = self._extract_boston_globe_url_from_redirect(response)
                            if bg_url:
                                logging.info(f"Extracted Boston Globe URL from redirect: {bg_url}")
                                article_url = bg_url
                                break
                            else:
                                logging.warning(f"Unrecognized redirect destination: {final_url}")
                                current_url = final_url
                                continue
                                
                    except Exception as redirect_error:
                        logging.error(f"Redirect attempt {redirect_attempt + 1} failed: {redirect_error}")
                        if redirect_attempt == max_redirects - 1:
                            return {"success": False, "error": f"All redirect attempts failed: {redirect_error}"}
                        continue
                
                # If we exhausted all attempts without finding a valid URL
                if not self._is_valid_boston_globe_url(article_url):
                    return {"success": False, "error": "Unable to resolve tracking URL to valid Boston Globe article"}
            
            # Navigate to the final article URL
            self.driver.get(article_url)
            time.sleep(5)
            
            # Check if we're on a paywall or login page
            if self._is_paywall_page():
                logging.info("Paywall detected, attempting to bypass")
                if not self._handle_paywall():
                    return {"success": False, "error": "Unable to bypass paywall"}
            
            # Enhanced content extraction
            content = self._extract_content()
            
            if len(content) < 100:
                return {"success": False, "error": f"Insufficient content: {len(content)} chars"}
                
            return {"success": True, "content": content}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def _extract_content(self):
        """Extract article content with enhanced Boston Globe specific selectors"""
        # Enhanced selectors for Boston Globe articles
        selectors = [
            ".story-body-text p",
            ".article-body p", 
            "[data-module='ArticleBody'] p",
            ".paywall-content p",
            "article p",
            ".story-content p",
            ".article-content p",
            ".entry-content p",
            ".post-content p",
            "main p",
            ".content-body p",
            ".article-text p"
        ]
        
        best_content = ""
        best_selector = None
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    # Filter out empty or very short paragraphs
                    meaningful_paragraphs = []
                    for el in elements:
                        text = el.text.strip()
                        if len(text) > 30 and not self._is_navigation_text(text):
                            meaningful_paragraphs.append(text)
                    
                    if meaningful_paragraphs:
                        content = " ".join(meaningful_paragraphs)
                        if len(content) > len(best_content):
                            best_content = content
                            best_selector = selector
                            logging.info(f"Content found with {selector}: {len(content)} chars from {len(meaningful_paragraphs)} paragraphs")
            except Exception as e:
                logging.debug(f"Selector {selector} failed: {e}")
                continue
        
        # If no content found with paragraph selectors, try broader selectors
        if len(best_content) < 100:
            broader_selectors = [
                ".story-body-text",
                ".article-body", 
                "[data-module='ArticleBody']",
                "article",
                "main",
                ".content-body",
                ".article-text",
                ".entry-content"
            ]
            
            for selector in broader_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        content = element.text.strip()
                        # Clean up the content
                        cleaned_content = self._clean_article_content(content)
                        if len(cleaned_content) > len(best_content):
                            best_content = cleaned_content
                            best_selector = selector
                            logging.info(f"Broader content found with {selector}: {len(cleaned_content)} chars")
                except Exception as e:
                    logging.debug(f"Broader selector {selector} failed: {e}")
                    continue
        
        # Final content validation and cleaning
        if best_content:
            best_content = self._clean_article_content(best_content)
            logging.info(f"Final content extracted using {best_selector}: {len(best_content)} chars")
        
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
            
    def _is_valid_boston_globe_url(self, url):
        """Check if URL is a valid Boston Globe article URL"""
        valid_domains = [
            'www.bostonglobe.com',
            'bostonglobe.com',
            'apps.bostonglobe.com'
        ]
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc in valid_domains and len(parsed.path) > 1
        except:
            return False
    
    def _is_external_advertising_url(self, url):
        """Check if URL is an external advertising site"""
        advertising_domains = [
            'liadm.com',
            'booking.com',
            'expedia.com',
            'hotels.com',
            'amazon.com',
            'googleadservices.com',
            'doubleclick.net',
            'facebook.com',
            'instagram.com',
            'twitter.com'
        ]
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return any(domain in parsed.netloc for domain in advertising_domains)
        except:
            return False
    
    def _extract_boston_globe_url_from_redirect(self, response):
        """Try to extract Boston Globe URL from redirect response"""
        try:
            # Check response headers for Boston Globe URLs
            if hasattr(response, 'history'):
                for historical_response in response.history:
                    if self._is_valid_boston_globe_url(historical_response.url):
                        return historical_response.url
            
            # Check response content for Boston Globe URLs
            if response.content:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for canonical URLs
                canonical = soup.find('link', {'rel': 'canonical'})
                if canonical and canonical.get('href'):
                    if self._is_valid_boston_globe_url(canonical['href']):
                        return canonical['href']
                
                # Look for meta refresh redirects
                meta_refresh = soup.find('meta', {'http-equiv': 'refresh'})
                if meta_refresh and meta_refresh.get('content'):
                    content = meta_refresh['content']
                    if 'url=' in content:
                        url = content.split('url=')[1].strip()
                        if self._is_valid_boston_globe_url(url):
                            return url
            
            return None
        except Exception as e:
            logging.debug(f"Error extracting Boston Globe URL: {e}")
            return None
    
    def _is_paywall_page(self):
        """Check if current page is a paywall or requires login"""
        try:
            page_source = self.driver.page_source.lower()
            paywall_indicators = [
                'subscribe to continue',
                'sign in to continue',
                'this article is for subscribers',
                'paywall',
                'subscription required',
                'piano-id'
            ]
            
            return any(indicator in page_source for indicator in paywall_indicators)
        except:
            return False
    
    def _handle_paywall(self):
        """Attempt to handle paywall by refreshing or waiting"""
        try:
            # Wait a bit longer for authentication to take effect
            time.sleep(3)
            
            # Try refreshing the page
            self.driver.refresh()
            time.sleep(5)
            
            # Check if paywall is still present
            if self._is_paywall_page():
                # Try clicking any "continue reading" or similar buttons
                continue_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                    "button[class*='continue'], a[class*='continue'], button[class*='unlock'], a[class*='unlock']")
                
                for button in continue_buttons:
                    try:
                        if button.is_displayed() and button.is_enabled():
                            button.click()
                            time.sleep(3)
                            break
                    except:
                        continue
            
            return not self._is_paywall_page()
        except Exception as e:
            logging.error(f"Error handling paywall: {e}")
            return False
    
    def _is_navigation_text(self, text):
        """Check if text is likely navigation/menu content rather than article content"""
        navigation_indicators = [
            'subscribe',
            'sign in',
            'menu',
            'navigation',
            'share this',
            'follow us',
            'newsletter',
            'advertisement',
            'sponsored content',
            'related articles',
            'most popular',
            'trending now'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in navigation_indicators)
    
    def _clean_article_content(self, content):
        """Clean article content by removing navigation and promotional text"""
        if not content:
            return ""
        
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if (len(line) > 20 and 
                not self._is_navigation_text(line) and
                not line.startswith('http') and
                not line.endswith('...more')):
                cleaned_lines.append(line)
        
        return ' '.join(cleaned_lines)
    
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