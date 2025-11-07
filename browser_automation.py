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
        """Extract Spotify episode content using browser automation with Show More expansion"""
        if not self.driver:
            return {"error": "Browser not initialized"}
        
        try:
            logging.info(f"Loading Spotify URL with browser: {spotify_url}")
            self.driver.get(spotify_url)
            
            # Wait for page to load and content to appear
            time.sleep(5)
            
            # Try to expand "Show more" buttons to get full content
            self._expand_show_more_buttons()
            
            # Wait for expanded content to load
            time.sleep(2)
            
            # Extract all text content using getText() equivalent
            try:
                full_text = self.driver.find_element(By.TAG_NAME, "body").text
                logging.info(f"Extracted full page text: {len(full_text)} characters")
                
                # Save text content for analysis
                episode_id = spotify_url.split('/episode/')[-1].split('?')[0]
                text_filename = f"/app/spotify_text_{episode_id}.txt"
                with open(text_filename, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                logging.info(f"Saved text content to {text_filename}")
                
                # Check if we got rich episode content (not just login page)
                if "Episode Description" in full_text and len(full_text) > 3000:
                    logging.info("Rich episode content detected - extracting detailed information")
                    
                    # Extract episode title from page title
                    page_title = self.driver.title
                    if " - " in page_title and "Podcast on Spotify" in page_title:
                        episode_title = page_title.split(" - ")[0].strip()
                    else:
                        episode_title = "Spotify Episode"
                    
                    # Extract episode description and details from full text
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                    
                    # Find episode description section
                    description_start = -1
                    for i, line in enumerate(lines):
                        if "Episode Description" in line:
                            description_start = i + 1
                            break
                    
                    episode_description = ""
                    if description_start > 0 and description_start < len(lines):
                        # Collect description lines until we hit a section break
                        desc_lines = []
                        for i in range(description_start, min(description_start + 20, len(lines))):
                            line = lines[i]
                            if line in ["See all episodes", "More episodes like this", "Show all"]:
                                break
                            if len(line) > 20:  # Only substantial content
                                desc_lines.append(line)
                        episode_description = " ".join(desc_lines)
                    
                    # If no description found, extract from the main content area
                    if not episode_description:
                        # Look for substantial content blocks
                        substantial_lines = [line for line in lines if len(line) > 100]
                        if substantial_lines:
                            episode_description = substantial_lines[0]
                    
                    logging.info(f"Extracted rich content: Title='{episode_title}', Description={len(episode_description)} chars")
                    
                    return {
                        "success": True,
                        "title": episode_title,
                        "description": episode_description,
                        "content": f"EPISODE_TITLE: {episode_title}\n\nEPISODE_DESCRIPTION: {episode_description}",
                        "full_text_length": len(full_text),
                        "content_type": "rich_episode_content"
                    }
                
            except Exception as e:
                logging.error(f"Failed to extract text content: {e}")
                full_text = ""
            
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
            
            # Extract title using getText()
            for selector in title_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element and element.text.strip():
                        title = element.text.strip()
                        logging.info(f"Found title with selector '{selector}': {title[:50]}...")
                        break
                except:
                    continue
            
            # Extract description using getText()
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
            
            # If no description found, extract from full text
            if not description and full_text:
                # Look for substantial text blocks in full text
                lines = [line.strip() for line in full_text.split('\n') if len(line.strip()) > 100]
                if lines:
                    description = lines[0]
                    logging.info(f"Extracted description from full text: {len(description)} chars")
            
            # Clean title
            clean_title = title.replace(' | Podcast on Spotify', '').replace(' - Spotify', '').strip()
            if clean_title == "Spotify – Web Player":
                clean_title = "Spotify Episode"
            
            # Format content
            content = f"EPISODE_TITLE: {clean_title}\n\nEPISODE_DESCRIPTION: {description}"
            
            logging.info(f"Browser extraction result: Title='{clean_title}', Description={len(description)} chars")
            logging.info(f"Full text length: {len(full_text)} chars")
            
            return {
                "success": True,
                "title": clean_title,
                "description": description,
                "content": content,
                "full_text_length": len(full_text)
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
    
    def _expand_show_more_buttons(self):
        """Click all 'Show more', 'Read more', 'See more' buttons to expand content"""
        if not self.driver:
            return
        
        # Common selectors for expandable content buttons
        expand_selectors = [
            # Spotify specific
            'button[aria-label*="Show more"]',
            'button[aria-label*="show more"]', 
            'button:contains("Show more")',
            'button:contains("... Show more")',
            '[data-testid*="show-more"]',
            '[data-testid*="expand"]',
            
            # Generic expand buttons
            'button:contains("Read more")',
            'button:contains("See more")',
            'button:contains("View more")',
            'button:contains("More")',
            'a:contains("Show more")',
            'a:contains("Read more")',
            
            # CSS class patterns
            '.show-more',
            '.read-more', 
            '.expand-button',
            '.more-button',
            '[class*="show-more"]',
            '[class*="read-more"]',
            '[class*="expand"]'
        ]
        
        buttons_clicked = 0
        
        for selector in expand_selectors:
            try:
                # Handle :contains() pseudo-selector manually
                if ':contains(' in selector:
                    text_to_find = selector.split(':contains("')[1].split('")')[0]
                    base_selector = selector.split(':contains(')[0]
                    
                    elements = self.driver.find_elements(By.CSS_SELECTOR, base_selector)
                    for element in elements:
                        if text_to_find.lower() in element.text.lower():
                            try:
                                self.driver.execute_script("arguments[0].click();", element)
                                buttons_clicked += 1
                                logging.info(f"Clicked expand button: {element.text[:30]}...")
                                time.sleep(1)  # Wait for content to expand
                            except Exception as e:
                                logging.debug(f"Failed to click element: {e}")
                else:
                    # Regular CSS selector
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                self.driver.execute_script("arguments[0].click();", element)
                                buttons_clicked += 1
                                logging.info(f"Clicked expand button with selector: {selector}")
                                time.sleep(1)  # Wait for content to expand
                        except Exception as e:
                            logging.debug(f"Failed to click element with selector {selector}: {e}")
                            
            except Exception as e:
                logging.debug(f"Selector {selector} not found or failed: {e}")
                continue
        
        if buttons_clicked > 0:
            logging.info(f"Successfully expanded {buttons_clicked} content sections")
            time.sleep(2)  # Additional wait for all content to load
        else:
            logging.info("No expandable content buttons found")
    
    def _expand_newsletter_content(self):
        """Expand newsletter-specific content like article previews"""
        if not self.driver:
            return
        
        # Newsletter-specific expand patterns
        newsletter_selectors = [
            # MailChimp
            'a[href*="Read full story"]',
            'a:contains("Read full story")',
            'a:contains("Continue reading")',
            
            # Substack
            'a:contains("Read more")',
            '.read-more-link',
            
            # General newsletter patterns
            'a:contains("View full article")',
            'a:contains("Read complete story")',
            '[class*="read-more"]',
            '[class*="continue-reading"]'
        ]
        
        for selector in newsletter_selectors:
            try:
                if ':contains(' in selector:
                    text_to_find = selector.split(':contains("')[1].split('")')[0]
                    base_selector = selector.split(':contains(')[0]
                    
                    elements = self.driver.find_elements(By.CSS_SELECTOR, base_selector)
                    for element in elements:
                        if text_to_find.lower() in element.text.lower():
                            logging.info(f"Found newsletter expand link: {element.text}")
                            # Don't click - just log for pattern recognition
                else:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        logging.info(f"Found newsletter expand element: {element.get_attribute('href') or element.text}")
                        
            except Exception as e:
                logging.debug(f"Newsletter selector {selector} failed: {e}")
    
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

def extract_full_newsletter_with_browser(url):
    """Extract full HTML structure for pattern detection while bypassing protection"""
    browser = get_browser()
    
    if not browser.driver:
        return {"error": "Browser not initialized"}
    
    try:
        # Enhanced Chrome options for stealth
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Create new driver for protected sites
        temp_driver = webdriver.Chrome(options=chrome_options)
        temp_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logging.info(f"Loading newsletter URL with browser: {url}")
        temp_driver.get(url)
        
        # Wait for content to load
        time.sleep(5)
        
        # Get full HTML source
        html_content = temp_driver.page_source
        page_title = temp_driver.title
        
        # Clean up temporary driver
        temp_driver.quit()
        
        return {
            "success": True,
            "title": page_title,
            "html_content": html_content,
            "content_type": "full_html"
        }
            
    except Exception as e:
        logging.error(f"Full HTML extraction error for {url}: {e}")
        return {"error": f"HTML extraction failed: {str(e)}"}

def extract_newsletter_content_with_browser(url):
    """Universal newsletter content extraction for any technology including Quora"""
    browser = get_browser()
    
    if not browser.driver:
        return {"error": "Browser not initialized"}
    
    try:
        # Enhanced Chrome options for stealth
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Create new driver with enhanced options for protected sites
        if 'quora.com' in url or 'medium.com' in url:
            temp_driver = webdriver.Chrome(options=chrome_options)
            temp_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            driver = temp_driver
        else:
            driver = browser.driver
        
        logging.info(f"Loading newsletter URL with browser: {url}")
        driver.get(url)
        
        # Wait for content to load
        time.sleep(5)
        
        # Extract full text content
        full_text = driver.find_element(By.TAG_NAME, "body").text
        page_title = driver.title
        
        # Detect content type and extract accordingly
        if 'spotify.com' in url:
            result = browser.extract_spotify_content(url)
        elif 'quora.com' in url:
            result = extract_quora_content(driver, url)
        elif 'podcasts.apple.com' in url:
            result = {
                "success": True,
                "title": page_title,
                "content": f"PODCAST_TITLE: {page_title}\n\nPODCAST_CONTENT: {full_text[:1000]}",
                "content_type": "apple_podcasts"
            }
        else:
            # Generic newsletter/article content
            lines = [line.strip() for line in full_text.split('\n') if len(line.strip()) > 50]
            substantial_content = ' '.join(lines[:10])  # First 10 substantial lines
            
            result = {
                "success": True,
                "title": page_title,
                "content": f"ARTICLE_TITLE: {page_title}\n\nARTICLE_CONTENT: {substantial_content}",
                "content_type": "generic_article",
                "full_text_length": len(full_text)
            }
        
        # Clean up temporary driver
        if 'quora.com' in url or 'medium.com' in url:
            temp_driver.quit()
        
        return result
            
    except Exception as e:
        logging.error(f"Universal browser extraction error for {url}: {e}")
        return {"error": f"Browser extraction failed: {str(e)}"}

def extract_quora_content(driver, url):
    """Extract content from Quora pages"""
    try:
        # Wait for Quora content to load
        WebDriverWait(driver, 10).until(
            EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".q-text")),
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='answer_content']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".spacing_log_answer_content"))
            )
        )
        
        # Extract title
        title = "Quora Content"
        try:
            title_selectors = [
                "h1",
                ".q-text.qu-dynamicFontSize--xlarge",
                "[data-testid='question_title']"
            ]
            for selector in title_selectors:
                title_elem = driver.find_element(By.CSS_SELECTOR, selector)
                if title_elem and title_elem.text.strip():
                    title = title_elem.text.strip()
                    break
        except:
            pass
        
        # Extract content
        content_parts = []
        content_selectors = [
            ".q-text",
            "[data-testid='answer_content']",
            ".spacing_log_answer_content",
            ".q-box.qu-pt--medium"
        ]
        
        for selector in content_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements[:5]:  # Limit to first 5 elements
                    text = elem.text.strip()
                    if len(text) > 50 and text not in content_parts:
                        content_parts.append(text)
            except:
                continue
        
        content = "\n\n".join(content_parts)
        
        if len(content) < 100:
            # Fallback: get all text content
            content = driver.find_element(By.TAG_NAME, "body").text
        
        return {
            'success': True,
            'title': title,
            'content': content,
            'url': url
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Quora extraction failed: {str(e)}',
            'url': url
        }

def test_spotify_text_extraction(spotify_url):
    """Test function to extract and analyze Spotify text content"""
    browser = get_browser()
    result = browser.extract_spotify_content(spotify_url)
    
    if result.get('success'):
        print(f"✅ Text extraction successful!")
        print(f"Title: {result['title']}")
        print(f"Description length: {len(result['description'])} chars")
        print(f"Full text length: {result.get('full_text_length', 0)} chars")
        print(f"Content preview: {result['content'][:200]}...")
    else:
        print(f"❌ Text extraction failed: {result.get('error')}")
    
    return result