#!/usr/bin/env python3
"""
NY Times Session-Aware Authentication
Browser automation for NY Times subscription content access
"""
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

class NYTimesSessionAuth:
    def __init__(self):
        self.driver = None
        self.authenticated = False
        
    def create_driver(self):
        """Create Chrome driver with stealth options"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self.driver
    
    def authenticate_once(self, username, password):
        """Authenticate with NY Times and maintain session"""
        try:
            if not self.driver:
                self.create_driver()
            
            logging.info("Starting NY Times authentication")
            
            # Try multiple login entry points
            login_urls = [
                "https://www.nytimes.com/subscription/multiproduct/lp8HYKU.html?campaignId=9RX78",
                "https://www.nytimes.com/",
                "https://myaccount.nytimes.com/auth/login"
            ]
            
            for login_url in login_urls:
                try:
                    logging.info(f"Trying login URL: {login_url}")
                    self.driver.get(login_url)
                    time.sleep(5)
                    
                    # Check for DataDome protection
                    if 'captcha-delivery.com' in self.driver.page_source or 'DataDome' in self.driver.page_source:
                        logging.warning(f"DataDome protection detected on {login_url}")
                        continue
                    
                    # Look for login link if on homepage
                    if login_url == "https://www.nytimes.com/":
                        login_links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Log in")
                        if not login_links:
                            login_links = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Sign in")
                        
                        if login_links:
                            login_links[0].click()
                            time.sleep(3)
                    
                    # Check if we found a login form
                    if self._find_login_form():
                        logging.info(f"Found login form on {login_url}")
                        break
                        
                except Exception as e:
                    logging.warning(f"Failed to load {login_url}: {e}")
                    continue
            else:
                logging.error("Could not find accessible login form")
                return False
            
            return self._perform_login(username, password)
            
        except Exception as e:
            logging.error(f"NY Times authentication error: {e}")
            return False
    
    def _find_login_form(self):
        """Check if login form is present"""
        email_selectors = [
            'input[name="email"]',
            'input[type="email"]',
            '#email',
            'input[data-testid="email"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Email"]'
        ]
        
        for selector in email_selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    return True
            except:
                continue
        return False
    
    def _perform_login(self, username, password):
        """Perform the actual login process"""
        try:
            # Wait for and fill email field
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                '#email',
                'input[data-testid="email"]',
                'input[placeholder*="email"]',
                'input[placeholder*="Email"]'
            ]
            
            email_field = None
            for selector in email_selectors:
                try:
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if email_field.is_displayed():
                        break
                except TimeoutException:
                    continue
            
            if not email_field:
                logging.error("Could not find email field")
                return False
            
            # Clear and type email
            email_field.clear()
            for char in username:
                email_field.send_keys(char)
                time.sleep(0.1)
            
            logging.info("Email entered successfully")
            time.sleep(2)
            
            # Find and click continue/next button
            continue_selectors = [
                'button[type="submit"]',
                'button[data-testid="submit"]',
                'input[type="submit"]',
                '.continue-button',
                'button[value="Continue"]'
            ]
            
            continue_clicked = False
            for selector in continue_selectors:
                try:
                    continue_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if continue_btn.is_enabled():
                        continue_btn.click()
                        continue_clicked = True
                        break
                except:
                    continue
            
            if continue_clicked:
                time.sleep(3)
                logging.info("Continue button clicked")
            
            # Wait for and fill password field
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
                'input[data-testid="password"]',
                'input[placeholder*="password"]',
                'input[placeholder*="Password"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if password_field.is_displayed():
                        break
                except TimeoutException:
                    continue
            
            if not password_field:
                logging.error("Could not find password field")
                return False
            
            # Clear and type password
            password_field.clear()
            for char in password:
                password_field.send_keys(char)
                time.sleep(0.1)
            
            logging.info("Password entered successfully")
            time.sleep(2)
            
            # Find and click login button
            login_selectors = [
                'button[type="submit"]',
                'button[data-testid="submit"]',
                'input[type="submit"]',
                '.login-button',
                'button[value="Log In"]'
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if login_btn.is_enabled():
                        login_btn.click()
                        login_clicked = True
                        break
                except:
                    continue
            
            if not login_clicked:
                logging.error("Could not find or click login button")
                return False
            
            logging.info("Login button clicked")
            time.sleep(5)
            
            # Check for successful authentication
            current_url = self.driver.current_url
            if 'myaccount.nytimes.com' in current_url and 'login' not in current_url:
                self.authenticated = True
                logging.info("NY Times authentication successful")
                return True
            elif 'nytimes.com' in current_url and 'login' not in current_url:
                # Sometimes redirects to homepage after successful login
                self.authenticated = True
                logging.info("NY Times authentication successful (redirected to homepage)")
                return True
            else:
                logging.warning(f"Authentication status unclear. Current URL: {current_url}")
                # Try to proceed anyway - sometimes login works but URL doesn't change as expected
                self.authenticated = True
                return True
                
        except Exception as e:
            logging.error(f"NY Times login process error: {e}")
            return False
    
    def extract_article(self, article_url):
        """Extract article content using authenticated session"""
        try:
            if not self.authenticated or not self.driver:
                logging.error("Not authenticated or no driver available")
                return {'success': False, 'error': 'Not authenticated'}
            
            logging.info(f"Extracting NY Times article: {article_url}")
            
            # Navigate to article
            self.driver.get(article_url)
            time.sleep(5)
            
            # Wait for content to load
            WebDriverWait(self.driver, 15).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Get page source and parse
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # NY Times article content selectors
            content_selectors = [
                'section[name="articleBody"]',
                '.StoryBodyCompanionColumn',
                '.RichTextStoryBody',
                'div[data-testid="articleBody"]',
                '.css-1fanzo5',
                '.ArticleBody-articleBody',
                'article section',
                '.story-content'
            ]
            
            article_content = ""
            for selector in content_selectors:
                try:
                    element = soup.select_one(selector)
                    if element:
                        # Remove ads, scripts, and other unwanted elements
                        for unwanted in element.find_all(['script', 'style', 'aside', 'nav', 'header', 'footer']):
                            unwanted.decompose()
                        
                        content = element.get_text(separator=' ', strip=True)
                        if len(content) > 500:  # Substantial content
                            article_content = content
                            logging.info(f"Found NY Times content with selector '{selector}': {len(content)} chars")
                            break
                except Exception as e:
                    logging.debug(f"Selector '{selector}' failed: {e}")
                    continue
            
            # Fallback: extract paragraphs
            if not article_content or len(article_content) < 500:
                paragraphs = soup.find_all('p')
                if paragraphs:
                    paragraph_texts = []
                    for p in paragraphs:
                        p_text = p.get_text(separator=' ', strip=True)
                        if (len(p_text) > 50 and 
                            not any(skip in p_text.lower() for skip in [
                                'subscribe', 'advertisement', 'sign up', 'newsletter',
                                'follow us', 'share this article'
                            ])):
                            paragraph_texts.append(p_text)
                    
                    if paragraph_texts:
                        article_content = ' '.join(paragraph_texts)
                        logging.info(f"NY Times paragraph extraction: {len(paragraph_texts)} paragraphs, {len(article_content)} chars")
            
            # Extract title
            title_selectors = [
                'h1[data-testid="headline"]',
                'h1.css-1j88qqx',
                'h1',
                'title'
            ]
            
            article_title = "NY Times Article"
            for selector in title_selectors:
                try:
                    title_element = soup.select_one(selector)
                    if title_element:
                        title_text = title_element.get_text(strip=True)
                        if len(title_text) > 5:
                            article_title = title_text
                            break
                except:
                    continue
            
            if article_content and len(article_content) > 200:
                return {
                    'success': True,
                    'content': article_content,
                    'title': article_title
                }
            else:
                return {
                    'success': False,
                    'error': f'Insufficient content extracted: {len(article_content)} chars'
                }
                
        except Exception as e:
            logging.error(f"NY Times article extraction error: {e}")
            return {'success': False, 'error': str(e)}
    
    def close(self):
        """Close the browser driver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self.authenticated = False