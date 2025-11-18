#!/usr/bin/env python3
"""
Boston Globe iframe-based Authentication Handler
Handles Piano/TinyPass iframe authentication system
"""
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

def authenticate_boston_globe_iframe(credentials, article_url=None):
    """
    Enhanced Boston Globe authentication handling iframe-based Piano/TinyPass system
    """
    driver = None
    try:
        # Create enhanced Chrome driver
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logging.info("Starting Boston Globe iframe authentication...")
        
        # Navigate to login page
        driver.get("https://www.bostonglobe.com/login")
        time.sleep(5)
        
        # Save HTML for debugging
        try:
            with open('/tmp/boston_globe_iframe_debug.html', 'w', encoding='utf-8') as f:
                f.write(f"<!-- URL: {driver.current_url} -->\\n")
                f.write(f"<!-- Title: {driver.title} -->\\n")
                f.write(driver.page_source)
            logging.info("Login page HTML saved for debugging")
        except Exception as e:
            logging.warning(f"Could not save debug HTML: {e}")
        
        wait = WebDriverWait(driver, 30)
        
        # Wait for iframe to load
        logging.info("Waiting for Piano iframe to load...")
        iframe_selectors = [
            'iframe[id*="piano-id"]',
            'iframe[src*="auth.bostonglobe.com"]',
            'iframe[src*="piano"]',
            '#login-form iframe'
        ]
        
        iframe_element = None
        for selector in iframe_selectors:
            try:
                iframe_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                logging.info(f"Found iframe with selector: {selector}")
                break
            except TimeoutException:
                continue
        
        if not iframe_element:
            return {'success': False, 'error': 'Piano iframe not found'}
        
        # Switch to iframe
        logging.info("Switching to Piano authentication iframe...")
        driver.switch_to.frame(iframe_element)
        
        # Wait for iframe content to load
        time.sleep(5)
        
        # Save iframe HTML for debugging
        try:
            with open('/tmp/boston_globe_iframe_content.html', 'w', encoding='utf-8') as f:
                f.write(f"<!-- iframe Content -->\\n")
                f.write(driver.page_source)
            logging.info("iframe content HTML saved for debugging")
        except Exception as e:
            logging.warning(f"Could not save iframe HTML: {e}")
        
        # Look for login form elements inside iframe
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[id*="email"]',
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
        
        email_field = None
        password_field = None
        
        # Find email field in iframe
        for selector in email_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        email_field = element
                        logging.info(f"Found email field in iframe: {selector}")
                        break
                if email_field:
                    break
            except Exception as e:
                continue
        
        # Find password field in iframe
        if email_field:
            for selector in password_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            password_field = element
                            logging.info(f"Found password field in iframe: {selector}")
                            break
                    if password_field:
                        break
                except Exception as e:
                    continue
        
        if not email_field or not password_field:
            # Try waiting longer for dynamic content
            logging.info("Login fields not immediately found, waiting for dynamic content...")
            time.sleep(10)
            
            # Try again after waiting
            for selector in email_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            email_field = element
                            logging.info(f"Found email field after wait: {selector}")
                            break
                    if email_field:
                        break
                except Exception as e:
                    continue
            
            if email_field:
                for selector in password_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            if element.is_displayed():
                                password_field = element
                                logging.info(f"Found password field after wait: {selector}")
                                break
                        if password_field:
                            break
                    except Exception as e:
                        continue
        
        if not email_field or not password_field:
            # Save current iframe state for debugging
            try:
                with open('/tmp/boston_globe_iframe_no_fields.html', 'w', encoding='utf-8') as f:
                    f.write(f"<!-- iframe Content - No Fields Found -->\\n")
                    f.write(driver.page_source)
                logging.info("iframe HTML saved - no login fields found")
            except:
                pass
            
            return {
                'success': False, 
                'error': f'Login form not found in iframe - Email: {bool(email_field)}, Password: {bool(password_field)}'
            }
        
        # Fill credentials with human-like timing
        logging.info("Filling credentials in iframe...")
        try:
            email_field.clear()
            time.sleep(0.5)
            for char in credentials['username']:
                email_field.send_keys(char)
                time.sleep(0.05)
            
            time.sleep(1)
            
            password_field.clear()
            time.sleep(0.5)
            for char in credentials['password']:
                password_field.send_keys(char)
                time.sleep(0.05)
            
            time.sleep(1)
            
            # Find submit button in iframe
            submit_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:contains("Sign In")',
                'button:contains("Log In")',
                '.login-button',
                '.submit-button',
                'button[class*="submit"]',
                'button[class*="login"]'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.is_enabled():
                            submit_button = element
                            logging.info(f"Found submit button in iframe: {selector}")
                            break
                    if submit_button:
                        break
                except Exception as e:
                    continue
            
            if not submit_button:
                # Look for any button with login-related text
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    if button.is_displayed() and button.is_enabled():
                        button_text = button.text.lower()
                        if any(word in button_text for word in ["sign", "log", "submit", "continue", "enter"]):
                            submit_button = button
                            logging.info(f"Found submit button by text: '{button.text}'")
                            break
            
            if not submit_button:
                return {'success': False, 'error': 'Submit button not found in iframe'}
            
            # Submit form
            logging.info("Submitting login form in iframe...")
            submit_button.click()
            time.sleep(5)
            
            # Switch back to main content
            driver.switch_to.default_content()
            
            # Wait for potential redirects
            time.sleep(5)
            
            # Check if login was successful
            current_url = driver.current_url
            if '/login' not in current_url:
                logging.info(f"Login successful, redirected to: {current_url}")
                
                # Navigate to target article if provided
                if article_url:
                    logging.info(f"Navigating to target article: {article_url}")
                    driver.get(article_url)
                    time.sleep(3)
                    
                    # Extract content
                    content_selectors = [
                        'article .article-content',
                        '.story-content',
                        '.article-body',
                        'article',
                        'main'
                    ]
                    
                    content = ""
                    for selector in content_selectors:
                        try:
                            element = driver.find_element(By.CSS_SELECTOR, selector)
                            if element:
                                text = element.text.strip()
                                if len(text) > len(content):
                                    content = text
                        except:
                            continue
                    
                    if len(content) > 200:
                        return {
                            'success': True,
                            'content': content,
                            'title': driver.title,
                            'url': article_url
                        }
                    else:
                        return {'success': False, 'error': f'Insufficient content extracted: {len(content)} chars'}
                else:
                    return {'success': True, 'message': 'Login successful'}
            else:
                # Still on login page, check for errors
                try:
                    # Look for error messages
                    error_selectors = ['.error', '.alert', '[class*="error"]', '[class*="alert"]']
                    error_message = ""
                    
                    for selector in error_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                if element.is_displayed() and element.text.strip():
                                    error_message = element.text.strip()
                                    break
                            if error_message:
                                break
                        except:
                            continue
                    
                    if error_message:
                        return {'success': False, 'error': f'Login failed: {error_message}'}
                    else:
                        return {'success': False, 'error': 'Still on login page after submission - credentials may be incorrect'}
                except:
                    return {'success': False, 'error': 'Still on login page after submission'}
                
        except Exception as e:
            return {'success': False, 'error': f'Form submission failed: {str(e)}'}
        
    except Exception as e:
        logging.error(f"Boston Globe iframe authentication failed: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def test_iframe_authentication():
    """Test the iframe authentication system"""
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    test_article = "https://www.bostonglobe.com/2024/11/13/business/"
    
    print("Testing Boston Globe iframe authentication...")
    result = authenticate_boston_globe_iframe(credentials, test_article)
    
    if result['success']:
        print(f"SUCCESS: {result.get('message', 'Authentication successful')}")
        if 'content' in result:
            print(f"Content extracted: {len(result['content'])} characters")
            print(f"Title: {result.get('title', 'N/A')}")
    else:
        print(f"FAILED: {result['error']}")
    
    return result

if __name__ == "__main__":
    test_iframe_authentication()