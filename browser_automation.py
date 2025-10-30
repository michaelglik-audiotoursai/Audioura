#!/usr/bin/env python3
"""
Browser Automation Module - Handles dynamic content extraction using Selenium
Supports Spotify and other JavaScript-heavy sites
"""
import logging
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

class BrowserAutomation:
    def __init__(self):
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """Setup headless Chrome driver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            logging.info("Browser automation initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize browser: {e}")
            self.driver = None
    
    def extract_spotify_content(self, spotify_url):
        """Extract Spotify episode content using browser automation"""
        if not self.driver:
            return {"error": "Browser not initialized"}
        
        try:
            logging.info(f"Loading Spotify URL with browser: {spotify_url}")
            self.driver.get(spotify_url)
            
            # Wait for page to load and content to appear
            time.sleep(5)
            
            # Try multiple selectors for episode title and description
            title_selectors = [
                'h1[data-testid="entity-title"]',
                'h1[class*="title"]',
                'h1',
                '[data-testid="episode-title"]'
            ]
            
            description_selectors = [
                '[data-testid="episode-description"]',
                '[class*="description"]',
                '[data-testid="entity-description"]',
                'div[class*="episode"] p',
                'div[class*="description"] span'
            ]
            
            title = "Spotify Episode"
            description = ""
            
            # Extract title
            for selector in title_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element and element.text.strip():
                        title = element.text.strip()
                        logging.info(f"Found title with selector '{selector}': {title[:50]}...")
                        break
                except:
                    continue
            
            # Extract description
            for selector in description_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 50:  # Only substantial descriptions
                            description = text
                            logging.info(f"Found description with selector '{selector}': {len(text)} chars")
                            break
                    if description:
                        break
                except:
                    continue
            
            # If no description found, try getting all text content
            if not description:
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    # Look for substantial text blocks
                    paragraphs = [p.strip() for p in body_text.split('\n') if len(p.strip()) > 100]
                    if paragraphs:
                        description = paragraphs[0]
                        logging.info(f"Extracted description from body text: {len(description)} chars")
                except:
                    pass
            
            # Clean title
            clean_title = title.replace(' | Podcast on Spotify', '').replace(' - Spotify', '').strip()
            if clean_title == "Spotify – Web Player":
                clean_title = "Spotify Episode"
            
            # Format content
            content = f"EPISODE_TITLE: {clean_title}\n\nEPISODE_DESCRIPTION: {description}"
            
            logging.info(f"Browser extraction result: Title='{clean_title}', Description={len(description)} chars")
            
            return {
                "success": True,
                "title": clean_title,
                "description": description,
                "content": content
            }
            
        except Exception as e:
            logging.error(f"Browser automation error for {spotify_url}: {e}")
            return {"error": f"Browser automation failed: {str(e)}"}
    
    def extract_dynamic_content(self, url):
        """Generic dynamic content extraction for any URL"""
        if not self.driver:
            return {"error": "Browser not initialized"}
        
        try:
            logging.info(f"Loading URL with browser: {url}")
            self.driver.get(url)
            time.sleep(3)
            
            # Extract title
            try:
                title = self.driver.title
            except:
                title = "Article"
            
            # Extract main content
            content_selectors = [
                'article',
                'main',
                '[role="main"]',
                '.content',
                '.article-content',
                '.post-content'
            ]
            
            content = ""
            for selector in content_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        content = element.text.strip()
                        if len(content) > 200:
                            break
                except:
                    continue
            
            # Fallback to body text
            if not content or len(content) < 200:
                try:
                    content = self.driver.find_element(By.TAG_NAME, "body").text.strip()
                except:
                    content = ""
            
            return {
                "success": True,
                "title": title,
                "content": content
            }
            
        except Exception as e:
            logging.error(f"Dynamic content extraction error for {url}: {e}")
            return {"error": f"Dynamic extraction failed: {str(e)}"}
    
    def close(self):
        """Close browser driver"""
        if self.driver:
            try:
                self.driver.quit()
                logging.info("Browser automation closed")
            except:
                pass

# Global browser instance
_browser = None

def get_browser():
    """Get or create browser instance"""
    global _browser
    if _browser is None:
        _browser = BrowserAutomation()
    return _browser

def extract_spotify_with_browser(spotify_url):
    """Extract Spotify content using browser automation"""
    browser = get_browser()
    return browser.extract_spotify_content(spotify_url)

def extract_dynamic_content(url):
    """Extract dynamic content from any URL"""
    browser = get_browser()
    return browser.extract_dynamic_content(url)