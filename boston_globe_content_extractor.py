#!/usr/bin/env python3
"""
Boston Globe Content Extractor
Enhanced content extraction after successful authentication
"""

import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from boston_globe_enhanced_auth import BostonGlobeEnhancedAuth

class BostonGlobeContentExtractor(BostonGlobeEnhancedAuth):
    
    def _extract_article_content(self):
        """Enhanced article content extraction"""
        try:
            # Wait for content to load
            time.sleep(5)
            
            logging.info("Starting enhanced content extraction")
            
            # First, try to find the main article container
            article_containers = [
                "article",
                "[data-module='ArticleBody']",
                ".article-content",
                ".story-content", 
                ".entry-content",
                ".article-body",
                ".story-body",
                ".content-body",
                ".post-content",
                "main",
                ".main-content"
            ]
            
            best_content = ""
            
            for container_selector in article_containers:
                try:
                    containers = self.driver.find_elements(By.CSS_SELECTOR, container_selector)
                    for container in containers:
                        # Extract text from paragraphs within this container
                        paragraphs = container.find_elements(By.TAG_NAME, "p")
                        container_text = " ".join([p.text.strip() for p in paragraphs if p.text.strip()])
                        
                        if len(container_text) > len(best_content):
                            best_content = container_text
                            logging.info(f"Better content found in {container_selector}: {len(container_text)} chars")
                            
                except Exception as e:
                    logging.debug(f"Container {container_selector} failed: {e}")
                    continue
                    
            # If still no good content, try specific Boston Globe selectors
            if len(best_content) < 200:
                bg_selectors = [
                    ".story-body-text",
                    ".article-text",
                    ".story-text",
                    "[data-testid='article-body']",
                    ".paywall-content",
                    ".subscriber-content"
                ]
                
                for selector in bg_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            text = element.get_attribute('textContent') or element.text
                            if text and len(text) > len(best_content):
                                best_content = text.strip()
                                logging.info(f"Boston Globe content found with {selector}: {len(best_content)} chars")
                    except Exception as e:
                        logging.debug(f"BG selector {selector} failed: {e}")
                        continue
                        
            # If still insufficient, try to scroll and wait for dynamic content
            if len(best_content) < 200:
                logging.info("Trying dynamic content loading")
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(3)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
                
                # Try again with all paragraphs
                all_paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                paragraph_texts = []
                
                for p in all_paragraphs:
                    text = p.text.strip()
                    if text and len(text) > 20:  # Filter out short navigation text
                        # Skip common navigation/footer text
                        skip_phrases = [
                            "digital access",
                            "home delivery", 
                            "gift subscriptions",
                            "log in",
                            "manage my account",
                            "customer service",
                            "privacy policy",
                            "terms of service",
                            "advertise",
                            "newsletters",
                            "staff list"
                        ]
                        
                        if not any(phrase in text.lower() for phrase in skip_phrases):
                            paragraph_texts.append(text)
                            
                if paragraph_texts:
                    best_content = " ".join(paragraph_texts)
                    logging.info(f"Dynamic content extraction: {len(best_content)} chars")
                    
            # Final attempt: look for any substantial text blocks
            if len(best_content) < 200:
                logging.info("Final attempt: looking for any substantial text")
                all_elements = self.driver.find_elements(By.XPATH, "//*[string-length(normalize-space(text())) > 50]")
                
                for element in all_elements:
                    text = element.text.strip()
                    if len(text) > len(best_content) and len(text) > 100:
                        # Check if it's not navigation text
                        if not any(nav in text.lower() for nav in ["subscribe", "log in", "digital access", "home delivery"]):
                            best_content = text
                            logging.info(f"Substantial text found: {len(best_content)} chars")
                            
            # Save debug information
            if len(best_content) < 200:
                debug_file = "/tmp/boston_globe_content_debug.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                logging.info(f"Saved debug HTML to {debug_file}")
                
                # Also save current URL for debugging
                logging.info(f"Current URL: {self.driver.current_url}")
                logging.info(f"Page title: {self.driver.title}")
                
            return best_content.strip()
            
        except Exception as e:
            logging.error(f"Enhanced content extraction error: {str(e)}")
            return ""

def test_enhanced_extraction():
    """Test the enhanced content extraction"""
    extractor = BostonGlobeContentExtractor()
    
    # Test credentials
    username = "glikfamily@gmail.com"
    password = "Eight2Four"
    test_url = "https://www.bostonglobe.com/2024/11/13/business/"
    
    print("Testing Enhanced Boston Globe Content Extraction")
    print(f"URL: {test_url}")
    
    result = extractor.authenticate_and_extract(test_url, username, password)
    
    print(f"\nResult: {result['success']}")
    
    if result["success"]:
        content = result['content']
        print(f"Content length: {len(content)} characters")
        print(f"Content preview (first 300 chars):")
        print(content[:300])
        print("\n" + "="*50)
        print(f"Content preview (last 300 chars):")
        print(content[-300:])
    else:
        print(f"Error: {result['error']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_enhanced_extraction()