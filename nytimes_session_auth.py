#!/usr/bin/env python3
"""
New York Times Session-Aware Authentication Module
Based on Boston Globe authentication template
Handles NYTimes subscription login and premium content extraction
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

class NYTimesAuthenticator:
    def __init__(self):
        self.session = requests.Session()
        self.driver = None
        self.logged_in = False
        
    def setup_chrome_driver(self):
        """Setup Chrome driver with stealth options for NYTimes"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # NYTimes-specific stealth options
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Additional anti-detection measures
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_argument('--disable-javascript')  # Enable if needed for login
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Execute script to remove webdriver property
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return self.driver
    
    def login_to_nytimes(self, username, password):
        """
        Login to New York Times using credentials
        NYTimes uses different login flow than Boston Globe
        """
        try:
            if not self.driver:
                self.setup_chrome_driver()
            
            logging.info("Starting NYTimes login process...")
            
            # Navigate to NYTimes login page
            login_url = "https://myaccount.nytimes.com/auth/login"
            self.driver.get(login_url)
            
            # Wait for page to load
            time.sleep(3)
            
            # Strategy 1: Standard login form
            success = self._try_standard_login(username, password)
            if success:
                return True
                
            # Strategy 2: Alternative selectors
            success = self._try_alternative_login(username, password)
            if success:
                return True
                
            # Strategy 3: JavaScript-based login
            success = self._try_javascript_login(username, password)
            if success:
                return True
                
            logging.error("All NYTimes login strategies failed")
            return False
            
        except Exception as e:
            logging.error(f"NYTimes login error: {str(e)}")
            return False
    
    def _try_standard_login(self, username, password):
        """Try standard NYTimes login form"""
        try:
            # Wait for email field
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            
            # Enter email
            email_field.clear()
            self._human_type(email_field, username)
            
            # Continue button
            continue_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            continue_btn.click()
            
            time.sleep(2)
            
            # Wait for password field
            password_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "password"))
            )
            
            # Enter password
            password_field.clear()
            self._human_type(password_field, password)
            
            # Login button
            login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_btn.click()
            
            # Wait for login completion
            time.sleep(5)
            
            # Check if login successful
            if "myaccount.nytimes.com" not in self.driver.current_url:
                logging.info("NYTimes standard login successful")
                self.logged_in = True
                return True
                
        except Exception as e:
            logging.warning(f"Standard NYTimes login failed: {str(e)}")
            
        return False
    
    def _try_alternative_login(self, username, password):
        """Try alternative NYTimes login selectors"""
        try:
            # Alternative email selectors
            email_selectors = [
                "input[name='email']",
                "input[type='email']",
                ".login-email input",
                "#login-email"
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except NoSuchElementException:
                    continue
            
            if not email_field:
                return False
                
            email_field.clear()
            self._human_type(email_field, username)
            
            # Try to find continue/next button
            continue_selectors = [
                "button[data-testid='continue-btn']",
                ".login-continue-btn",
                "button:contains('Continue')",
                "input[type='submit']"
            ]
            
            for selector in continue_selectors:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    break
                except NoSuchElementException:
                    continue
            
            time.sleep(2)
            
            # Alternative password selectors
            password_selectors = [
                "input[name='password']",
                "input[type='password']",
                ".login-password input",
                "#login-password"
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue
            
            if not password_field:
                return False
                
            password_field.clear()
            self._human_type(password_field, password)
            
            # Submit login
            login_selectors = [
                "button[data-testid='login-btn']",
                ".login-submit-btn",
                "button[type='submit']",
                "input[type='submit']"
            ]
            
            for selector in login_selectors:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    btn.click()
                    break
                except NoSuchElementException:
                    continue
            
            time.sleep(5)
            
            # Check success
            if self._check_login_success():
                logging.info("NYTimes alternative login successful")
                self.logged_in = True
                return True
                
        except Exception as e:
            logging.warning(f"Alternative NYTimes login failed: {str(e)}")
            
        return False
    
    def _try_javascript_login(self, username, password):
        """Try JavaScript-based NYTimes login"""
        try:
            # Execute JavaScript to fill and submit form
            js_script = f"""
            // Find email field
            var emailField = document.querySelector('#email') || 
                           document.querySelector('input[name="email"]') ||
                           document.querySelector('input[type="email"]');
            
            if (emailField) {{
                emailField.value = '{username}';
                emailField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                
                // Find and click continue
                var continueBtn = document.querySelector('button[type="submit"]') ||
                                document.querySelector('.login-continue-btn');
                if (continueBtn) {{
                    continueBtn.click();
                }}
            }}
            
            // Wait and fill password
            setTimeout(function() {{
                var passwordField = document.querySelector('#password') ||
                                  document.querySelector('input[name="password"]') ||
                                  document.querySelector('input[type="password"]');
                
                if (passwordField) {{
                    passwordField.value = '{password}';
                    passwordField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    
                    // Submit login
                    var loginBtn = document.querySelector('button[type="submit"]') ||
                                 document.querySelector('.login-submit-btn');
                    if (loginBtn) {{
                        loginBtn.click();
                    }}
                }}
            }}, 2000);
            """
            
            self.driver.execute_script(js_script)
            time.sleep(8)
            
            if self._check_login_success():
                logging.info("NYTimes JavaScript login successful")
                self.logged_in = True
                return True
                
        except Exception as e:
            logging.warning(f"JavaScript NYTimes login failed: {str(e)}")
            
        return False
    
    def _check_login_success(self):
        """Check if NYTimes login was successful"""
        try:
            # Check URL change
            current_url = self.driver.current_url
            if "myaccount.nytimes.com" in current_url and "login" not in current_url:
                return True
                
            # Check for user account elements
            user_indicators = [
                ".user-menu",
                ".account-menu",
                "[data-testid='user-menu']",
                ".nyt-user-menu"
            ]
            
            for selector in user_indicators:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        return True
                except NoSuchElementException:
                    continue
                    
            # Check for login error messages
            error_selectors = [
                ".error-message",
                ".login-error",
                "[data-testid='error-message']"
            ]
            
            for selector in error_selectors:
                try:
                    error = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if error and error.is_displayed():
                        logging.error(f"NYTimes login error: {error.text}")
                        return False
                except NoSuchElementException:
                    continue
                    
        except Exception as e:
            logging.warning(f"Login success check failed: {str(e)}")
            
        return False
    
    def _human_type(self, element, text):
        """Type text with human-like delays"""
        for char in text:
            element.send_keys(char)
            time.sleep(0.05 + (time.time() % 0.1))  # Random delay 0.05-0.15s
    
    def extract_premium_article(self, article_url):
        """
        Extract premium NYTimes article content after authentication
        """
        try:
            if not self.logged_in:
                logging.error("Must be logged in to extract premium content")
                return None
                
            logging.info(f"Extracting NYTimes premium article: {article_url}")
            
            # Navigate to article
            self.driver.get(article_url)
            time.sleep(3)
            
            # NYTimes article content selectors
            content_selectors = [
                ".StoryBodyCompanionColumn div[data-module='ArticleBody'] p",
                ".css-53u6y8 p",  # NYTimes article paragraphs
                "[data-module='ArticleBody'] p",
                ".story-body p",
                ".article-body p"
            ]
            
            content_parts = []
            
            for selector in content_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for element in elements:
                            text = element.text.strip()
                            if text and len(text) > 20:  # Filter out short elements
                                content_parts.append(text)
                        break
                except Exception as e:
                    logging.warning(f"Selector {selector} failed: {str(e)}")
                    continue
            
            if content_parts:
                full_content = "\n\n".join(content_parts)
                logging.info(f"Extracted {len(full_content)} characters from NYTimes article")
                return full_content
            else:
                logging.warning("No content extracted from NYTimes article")
                return None
                
        except Exception as e:
            logging.error(f"NYTimes article extraction error: {str(e)}")
            return None
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logging.warning(f"Driver cleanup error: {str(e)}")
        
        if self.session:
            try:
                self.session.close()
            except Exception as e:
                logging.warning(f"Session cleanup error: {str(e)}")

# Test function
def test_nytimes_authentication():
    """Test NYTimes authentication with sample credentials"""
    auth = NYTimesAuthenticator()
    
    try:
        # Test credentials (replace with real ones for testing)
        test_username = "test@example.com"
        test_password = "test_password"
        
        success = auth.login_to_nytimes(test_username, test_password)
        
        if success:
            print("✅ NYTimes authentication successful")
            
            # Test article extraction
            test_article = "https://www.nytimes.com/2025/11/13/business/sample-article.html"
            content = auth.extract_premium_article(test_article)
            
            if content:
                print(f"✅ Article extraction successful: {len(content)} characters")
            else:
                print("❌ Article extraction failed")
        else:
            print("❌ NYTimes authentication failed")
            
    finally:
        auth.cleanup()

if __name__ == "__main__":
    test_nytimes_authentication()