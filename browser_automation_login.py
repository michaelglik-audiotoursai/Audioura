#!/usr/bin/env python3
"""
Browser Automation Login Module - Phase 2
Handles authenticated content extraction using stored credentials
"""
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse

def extract_content_with_login(article_url, credentials):
    """Extract article content using stored credentials for authentication"""
    try:
        domain = urlparse(article_url).netloc
        
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            if 'bostonglobe.com' in domain:
                return _extract_boston_globe_with_login(driver, article_url, credentials)
            else:
                return _extract_generic_with_login(driver, article_url, credentials)
        finally:
            driver.quit()
            
    except Exception as e:
        logging.error(f"Login-based extraction failed for {article_url}: {e}")
        return {'success': False, 'error': f'Authentication failed: {str(e)}'}

def _extract_boston_globe_with_login(driver, article_url, credentials):
    """Extract Boston Globe article with login"""
    try:
        driver.get("https://www.bostonglobe.com/login")
        wait = WebDriverWait(driver, 15)
        
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        email_field.send_keys(credentials['username'])
        
        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(credentials['password'])
        
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        time.sleep(5)
        
        driver.get(article_url)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        
        for selector in ['article .article-content', '.story-content', 'article']:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element:
                    content = element.text.strip()
                    if len(content) > 200:
                        return {'success': True, 'title': driver.title, 'content': content, 'url': article_url}
            except:
                continue
        
        raise Exception("Insufficient content extracted after login")
            
    except Exception as e:
        return {'success': False, 'error': f'Boston Globe login failed: {str(e)}'}

def _extract_generic_with_login(driver, article_url, credentials):
    """Generic authenticated content extraction"""
    try:
        driver.get(article_url)
        time.sleep(3)
        
        # Try to find and fill login form
        try:
            email_field = driver.find_element(By.CSS_SELECTOR, 'input[type="email"], input[name="email"]')
            email_field.send_keys(credentials['username'])
            
            password_field = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            password_field.send_keys(credentials['password'])
            
            submit_button = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
            submit_button.click()
            time.sleep(5)
        except:
            pass
        
        # Extract content
        for selector in ['article', 'main', '.article-content', '.story-content']:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element:
                    content = element.text.strip()
                    if len(content) > 200:
                        return {'success': True, 'title': driver.title, 'content': content, 'url': article_url}
            except:
                continue
        
        # Fallback to body text
        content = driver.find_element(By.TAG_NAME, "body").text.strip()
        if len(content) > 100:
            return {'success': True, 'title': driver.title, 'content': content, 'url': article_url}
        
        raise Exception("Insufficient content extracted")
            
    except Exception as e:
        return {'success': False, 'error': f'Generic login failed: {str(e)}'}