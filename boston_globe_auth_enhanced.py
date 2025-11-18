#!/usr/bin/env python3
"""
Enhanced Boston Globe Authentication Module
Handles complex JavaScript-heavy login system with third-party authentication
"""
import logging
import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import urlparse, parse_qs

class BostonGlobeAuthenticator:
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        """Setup detailed logging for authentication debugging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
    def create_enhanced_driver(self):
        """Create Chrome driver with enhanced stealth and anti-bot features"""
        chrome_options = Options()
        
        # Enhanced stealth options
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Realistic browser simulation
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        
        # Anti-detection features
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("detach", True)
        
        # Additional stealth preferences
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "media_stream": 2,
            },
            "profile.managed_default_content_settings": {
                "images": 2
            }
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        driver = webdriver.Chrome(options=chrome_options)
        
        # Execute stealth scripts
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
        
        return driver
        
    def wait_for_dynamic_content(self, driver, timeout=30):
        """Wait for JavaScript to load dynamic content"""
        try:
            # Wait for basic page load
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Wait for potential AJAX requests
            time.sleep(2)
            
            # Wait for any loading indicators to disappear
            try:
                WebDriverWait(driver, 5).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".loading, .spinner, [data-loading]"))
                )
            except TimeoutException:
                pass  # No loading indicators found
                
            return True
        except TimeoutException:
            self.logger.warning(f"Timeout waiting for dynamic content after {timeout}s")
            return False
            
    def find_login_form_elements(self, driver):
        """Find login form elements using multiple strategies"""
        self.logger.info("Searching for login form elements...")
        
        # Strategy 1: Standard form elements
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[id*="email"]',
            'input[id*="username"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Email"]'
        ]
        
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="password"]',
            'input[placeholder*="password"]',
            'input[placeholder*="Password"]'
        ]
        
        # Try to find email field
        email_field = None
        for selector in email_selectors:
            try:
                email_field = driver.find_element(By.CSS_SELECTOR, selector)
                if email_field.is_displayed():
                    self.logger.info(f"Found email field with selector: {selector}")
                    break
            except NoSuchElementException:
                continue
                
        # Try to find password field
        password_field = None
        for selector in password_selectors:
            try:
                password_field = driver.find_element(By.CSS_SELECTOR, selector)
                if password_field.is_displayed():
                    self.logger.info(f"Found password field with selector: {selector}")
                    break
            except NoSuchElementException:
                continue
        
        # Strategy 2: Look for forms and inputs within them
        if not email_field or not password_field:
            try:
                forms = driver.find_elements(By.TAG_NAME, "form")
                for form in forms:
                    inputs = form.find_elements(By.TAG_NAME, "input")
                    for input_elem in inputs:
                        input_type = input_elem.get_attribute("type")
                        input_name = input_elem.get_attribute("name")
                        input_id = input_elem.get_attribute("id")
                        
                        if not email_field and (input_type == "email" or "email" in str(input_name).lower() or "email" in str(input_id).lower()):
                            email_field = input_elem
                            self.logger.info(f"Found email field in form: {input_name or input_id}")
                            
                        if not password_field and input_type == "password":
                            password_field = input_elem
                            self.logger.info(f"Found password field in form: {input_name or input_id}")
            except Exception as e:
                self.logger.warning(f"Error searching forms: {e}")
        
        # Strategy 3: Look in iframes
        if not email_field or not password_field:
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        
                        if not email_field:
                            for selector in email_selectors:
                                try:
                                    email_field = driver.find_element(By.CSS_SELECTOR, selector)
                                    if email_field.is_displayed():
                                        self.logger.info(f"Found email field in iframe: {selector}")
                                        break
                                except NoSuchElementException:
                                    continue
                                    
                        if not password_field:
                            for selector in password_selectors:
                                try:
                                    password_field = driver.find_element(By.CSS_SELECTOR, selector)
                                    if password_field.is_displayed():
                                        self.logger.info(f"Found password field in iframe: {selector}")
                                        break
                                except NoSuchElementException:
                                    continue
                                    
                        if email_field and password_field:
                            break
                            
                    except Exception as e:
                        self.logger.warning(f"Error checking iframe: {e}")
                    finally:
                        driver.switch_to.default_content()
            except Exception as e:
                self.logger.warning(f"Error searching iframes: {e}")
        
        return email_field, password_field
        
    def find_submit_button(self, driver, email_field=None):
        """Find submit button using multiple strategies"""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:contains("Sign In")',
            'button:contains("Log In")',
            'button:contains("Login")',
            '[data-testid*="submit"]',
            '[data-testid*="login"]',
            '.login-button',
            '.submit-button'
        ]
        
        # Try direct selectors
        for selector in submit_selectors:
            try:
                button = driver.find_element(By.CSS_SELECTOR, selector)
                if button.is_displayed() and button.is_enabled():
                    self.logger.info(f"Found submit button: {selector}")
                    return button
            except NoSuchElementException:
                continue
        
        # Look for buttons near the email field
        if email_field:
            try:
                form = email_field.find_element(By.XPATH, "./ancestor::form")
                buttons = form.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    if button.is_displayed() and button.is_enabled():
                        button_text = button.text.lower()
                        if any(word in button_text for word in ["sign", "log", "submit", "continue"]):
                            self.logger.info(f"Found submit button by text: {button.text}")
                            return button
            except Exception as e:
                self.logger.warning(f"Error finding button near email field: {e}")
        
        # Look for any clickable button
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                if button.is_displayed() and button.is_enabled():
                    button_text = button.text.lower()
                    if any(word in button_text for word in ["sign", "log", "submit", "continue"]):
                        self.logger.info(f"Found potential submit button: {button.text}")
                        return button
        except Exception as e:
            self.logger.warning(f"Error finding buttons: {e}")
            
        return None
        
    def handle_third_party_auth(self, driver, credentials, max_redirects=5):
        """Handle third-party authentication redirects"""
        redirect_count = 0
        
        while redirect_count < max_redirects:
            current_url = driver.current_url
            self.logger.info(f"Current URL: {current_url}")
            
            # Check if we're on a third-party auth domain
            if any(domain in current_url for domain in ['auth.bostonglobe.com', 'tinypass.com', 'piano.io']):
                self.logger.info(f"Detected third-party auth domain: {current_url}")
                
                # Wait for page to load
                self.wait_for_dynamic_content(driver, timeout=15)
                
                # Try to find and fill login form
                email_field, password_field = self.find_login_form_elements(driver)
                
                if email_field and password_field:
                    try:
                        # Clear and fill email
                        email_field.clear()
                        time.sleep(0.5)
                        email_field.send_keys(credentials['username'])
                        time.sleep(1)
                        
                        # Clear and fill password
                        password_field.clear()
                        time.sleep(0.5)
                        password_field.send_keys(credentials['password'])\n                        time.sleep(1)
                        
                        # Find and click submit button
                        submit_button = self.find_submit_button(driver, email_field)
                        if submit_button:
                            self.logger.info("Clicking submit button...")
                            submit_button.click()
                            time.sleep(3)
                            
                            # Wait for potential redirect
                            try:
                                WebDriverWait(driver, 10).until(
                                    lambda d: d.current_url != current_url
                                )
                                redirect_count += 1
                                continue
                            except TimeoutException:
                                self.logger.warning("No redirect detected after login attempt")
                                break
                        else:
                            self.logger.error("Could not find submit button")
                            break
                            
                    except Exception as e:
                        self.logger.error(f"Error filling login form: {e}")
                        break
                else:
                    self.logger.error("Could not find login form elements")
                    break
            else:
                # Not on third-party auth domain, check if we're back on Boston Globe
                if 'bostonglobe.com' in current_url and '/login' not in current_url:
                    self.logger.info("Successfully returned to Boston Globe after authentication")
                    return True
                break
                
        self.logger.warning(f"Third-party auth handling completed after {redirect_count} redirects")
        return redirect_count > 0
        
    def authenticate_boston_globe(self, credentials, target_article_url=None):
        """
        Authenticate with Boston Globe using enhanced browser automation
        Returns: (success, driver, error_message)
        """
        driver = None
        try:
            driver = self.create_enhanced_driver()
            self.logger.info("Starting Boston Globe authentication...")
            
            # Navigate to login page
            login_url = "https://www.bostonglobe.com/login"
            self.logger.info(f"Navigating to: {login_url}")
            driver.get(login_url)
            
            # Wait for page to load and JavaScript to execute
            self.wait_for_dynamic_content(driver, timeout=30)
            
            # Debug: Save page source for analysis
            try:
                page_source = driver.page_source
                self.logger.info(f"Page loaded, source length: {len(page_source)} chars")
                
                # Check for common login indicators
                if 'email' in page_source.lower() or 'password' in page_source.lower():
                    self.logger.info("Login form elements detected in page source")
                else:
                    self.logger.warning("No obvious login form elements in page source")
                    
            except Exception as e:
                self.logger.warning(f"Could not analyze page source: {e}")
            
            # Try multiple authentication strategies
            success = False
            
            # Strategy 1: Direct form filling
            self.logger.info("Attempting Strategy 1: Direct form filling")
            email_field, password_field = self.find_login_form_elements(driver)
            
            if email_field and password_field:
                try:
                    # Fill credentials with human-like timing
                    self.logger.info("Filling login credentials...")
                    email_field.clear()
                    time.sleep(0.5)
                    for char in credentials['username']:
                        email_field.send_keys(char)
                        time.sleep(0.05)  # Human-like typing
                    
                    time.sleep(1)
                    
                    password_field.clear()
                    time.sleep(0.5)
                    for char in credentials['password']:
                        password_field.send_keys(char)
                        time.sleep(0.05)  # Human-like typing
                    
                    time.sleep(1)
                    
                    # Find and click submit
                    submit_button = self.find_submit_button(driver, email_field)
                    if submit_button:
                        self.logger.info("Submitting login form...")
                        submit_button.click()
                        time.sleep(5)
                        
                        # Check for successful login or redirects
                        current_url = driver.current_url
                        if '/login' not in current_url or 'auth.' in current_url:
                            success = True
                            self.logger.info(f"Login form submitted, redirected to: {current_url}")
                        else:
                            self.logger.warning("Still on login page after form submission")
                    else:
                        self.logger.error("Could not find submit button")
                        
                except Exception as e:
                    self.logger.error(f"Error in direct form filling: {e}")
            else:
                self.logger.warning("Could not find login form elements for direct filling")
            
            # Strategy 2: Handle third-party authentication
            if not success or any(domain in driver.current_url for domain in ['auth.', 'tinypass.', 'piano.']):
                self.logger.info("Attempting Strategy 2: Third-party authentication handling")
                success = self.handle_third_party_auth(driver, credentials)
            
            # Strategy 3: JavaScript execution for dynamic forms
            if not success:
                self.logger.info("Attempting Strategy 3: JavaScript form interaction")
                try:
                    # Try to trigger form loading with JavaScript
                    driver.execute_script("""
                        // Try to find and trigger login form
                        var emailInputs = document.querySelectorAll('input[type="email"], input[name="email"]');
                        var passwordInputs = document.querySelectorAll('input[type="password"]');
                        
                        if (emailInputs.length > 0 && passwordInputs.length > 0) {
                            emailInputs[0].value = arguments[0];
                            passwordInputs[0].value = arguments[1];
                            
                            // Trigger events
                            emailInputs[0].dispatchEvent(new Event('input', {bubbles: true}));
                            passwordInputs[0].dispatchEvent(new Event('input', {bubbles: true}));
                            
                            // Try to find and click submit
                            var submitButtons = document.querySelectorAll('button[type="submit"], input[type="submit"]');
                            if (submitButtons.length > 0) {
                                submitButtons[0].click();
                                return 'form_submitted';
                            }
                        }
                        return 'no_form_found';
                    """, credentials['username'], credentials['password'])
                    
                    time.sleep(5)
                    
                    if '/login' not in driver.current_url:
                        success = True
                        self.logger.info("JavaScript form submission successful")
                    
                except Exception as e:
                    self.logger.error(f"Error in JavaScript form interaction: {e}")
            
            # Final verification
            if success:
                # If we have a target article, try to navigate to it
                if target_article_url:
                    self.logger.info(f"Navigating to target article: {target_article_url}")
                    driver.get(target_article_url)
                    self.wait_for_dynamic_content(driver, timeout=15)
                
                self.logger.info("Boston Globe authentication completed successfully")
                return True, driver, None
            else:
                error_msg = "All authentication strategies failed"
                self.logger.error(error_msg)
                return False, driver, error_msg
                
        except Exception as e:
            error_msg = f"Boston Globe authentication failed: {str(e)}"
            self.logger.error(error_msg)
            return False, driver, error_msg
            
    def extract_article_content(self, driver, article_url):
        """Extract article content from authenticated session"""
        try:
            # Navigate to article if not already there
            if driver.current_url != article_url:
                self.logger.info(f"Navigating to article: {article_url}")
                driver.get(article_url)
                self.wait_for_dynamic_content(driver, timeout=15)
            
            # Try multiple content selectors
            content_selectors = [
                'article .article-content',
                '.story-content',
                '.article-body',
                '[data-testid="article-content"]',
                '.paywall-content',
                '.premium-content',
                'article p',
                'main article',
                'article'
            ]
            
            best_content = ""
            for selector in content_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            content = element.text.strip()
                            if len(content) > len(best_content):
                                best_content = content
                                self.logger.info(f"Found content with selector '{selector}': {len(content)} chars")
                except Exception as e:
                    continue
            
            # If no good content found, try getting all text
            if len(best_content) < 200:
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    # Filter out navigation and footer content
                    lines = body_text.split('\n')
                    article_lines = []
                    for line in lines:
                        line = line.strip()
                        if len(line) > 50 and not any(skip in line.lower() for skip in 
                            ['subscribe', 'newsletter', 'menu', 'navigation', 'footer', 'advertisement']):
                            article_lines.append(line)
                    
                    if article_lines:
                        best_content = '\n'.join(article_lines)
                        self.logger.info(f"Extracted filtered body content: {len(best_content)} chars")
                except Exception as e:
                    self.logger.warning(f"Error extracting body content: {e}")
            
            if len(best_content) > 200:
                self.logger.info(f"Successfully extracted article content: {len(best_content)} characters")
                return {
                    'success': True,
                    'content': best_content,
                    'title': driver.title,
                    'url': article_url
                }
            else:
                error_msg = f"Insufficient content extracted: {len(best_content)} characters"
                self.logger.error(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'content': best_content
                }
                
        except Exception as e:
            error_msg = f"Error extracting article content: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
            
    def authenticate_and_extract(self, article_url, credentials):
        """
        Complete workflow: authenticate and extract article content
        Returns: dict with success, content, title, url, or error
        """
        driver = None
        try:
            # Authenticate
            auth_success, driver, auth_error = self.authenticate_boston_globe(credentials, article_url)
            
            if not auth_success:
                if driver:
                    driver.quit()
                return {
                    'success': False,
                    'error': f'Authentication failed: {auth_error}'
                }
            
            # Extract content
            result = self.extract_article_content(driver, article_url)
            
            return result
            
        except Exception as e:
            error_msg = f"Complete workflow failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

# Test function for debugging
def test_boston_globe_auth():
    """Test function for Boston Globe authentication"""
    authenticator = BostonGlobeAuthenticator()
    
    # Test credentials
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    # Test article URL
    test_url = "https://www.bostonglobe.com/2024/11/13/business/test-article"
    
    print("Testing Boston Globe authentication...")
    result = authenticator.authenticate_and_extract(test_url, credentials)
    
    if result['success']:
        print(f"SUCCESS: Extracted {len(result['content'])} characters")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Content preview: {result['content'][:200]}...")
    else:
        print(f"FAILED: {result['error']}")
    
    return result

if __name__ == "__main__":
    test_boston_globe_auth()