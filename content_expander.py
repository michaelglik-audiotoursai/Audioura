#!/usr/bin/env python3
"""
Content Expander Module - Handles expanding truncated content across all platforms
Supports Spotify, newsletters, and any site with "Show more" functionality
"""
import logging
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

class ContentExpander:
    """Universal content expansion for any platform"""
    
    @staticmethod
    def expand_all_content(driver, platform_hint=None):
        """
        Expand all truncated content on the page
        
        Args:
            driver: Selenium WebDriver instance
            platform_hint: Optional hint about the platform (spotify, newsletter, etc.)
        
        Returns:
            int: Number of content sections expanded
        """
        if not driver:
            return 0
        
        expanded_count = 0
        
        # Platform-specific expansion
        if platform_hint == 'spotify':
            expanded_count += ContentExpander._expand_spotify_content(driver)
        elif platform_hint == 'newsletter':
            expanded_count += ContentExpander._expand_newsletter_content(driver)
        
        # Universal expansion patterns
        expanded_count += ContentExpander._expand_universal_content(driver)
        
        if expanded_count > 0:
            logging.info(f"Successfully expanded {expanded_count} content sections")
            time.sleep(2)  # Wait for all content to load
        
        return expanded_count
    
    @staticmethod
    def _expand_spotify_content(driver):
        """Expand Spotify-specific truncated content"""
        spotify_selectors = [
            # Spotify episode description expansion - Updated selectors
            'button[aria-label*="Show more"]',
            'button[aria-label*="show more"]', 
            'button[data-testid*="show-more"]',
            'button[data-testid*="expand"]',
            '[data-testid="show-more-button"]',
            
            # Episode description area
            '[data-testid="episode-description"] button',
            '[class*="episode-description"] button',
            '[class*="description"] button',
            
            # Text-based detection (most reliable)
            'button:contains("Show more")',
            'button:contains("... Show more")',
            'span:contains("Show more")',
            'div:contains("Show more")',
            
            # Fallback patterns
            'button[class*="show"]',
            'button[class*="more"]',
            'button[class*="expand"]'
        ]
        
        return ContentExpander._click_expand_buttons(driver, spotify_selectors, "Spotify")
    
    @staticmethod
    def _expand_newsletter_content(driver):
        """Expand newsletter-specific content"""
        newsletter_selectors = [
            # Newsletter article previews
            'a[href*="Read full story"]',
            'a[href*="read-more"]',
            'a[href*="continue-reading"]',
            
            # Button-style expanders
            'button:has-text("Read more")',
            'button:has-text("Continue reading")',
            'button:has-text("View full article")',
            
            # CSS class patterns
            '.read-more-button',
            '.continue-reading',
            '.expand-article',
            '[class*="read-more"]',
            '[class*="show-more"]'
        ]
        
        return ContentExpander._click_expand_buttons(driver, newsletter_selectors, "Newsletter")
    
    @staticmethod
    def _expand_universal_content(driver):
        """Expand content using universal patterns"""
        universal_selectors = [
            # Common expand button patterns
            'button:has-text("Show more")',
            'button:has-text("Read more")',
            'button:has-text("See more")',
            'button:has-text("View more")',
            'button:has-text("More")',
            'button:has-text("Expand")',
            
            # Link-style expanders
            'a:has-text("Show more")',
            'a:has-text("Read more")',
            'a:has-text("See more")',
            
            # CSS class patterns
            '.show-more',
            '.read-more',
            '.see-more',
            '.expand-button',
            '.more-button',
            '[class*="show-more"]',
            '[class*="read-more"]',
            '[class*="expand"]',
            
            # ARIA labels
            '[aria-label*="show more"]',
            '[aria-label*="read more"]',
            '[aria-label*="expand"]',
            
            # Data attributes
            '[data-action="expand"]',
            '[data-action="show-more"]',
            '[data-toggle="expand"]'
        ]
        
        return ContentExpander._click_expand_buttons(driver, universal_selectors, "Universal")
    
    @staticmethod
    def _click_expand_buttons(driver, selectors, category):
        """Click expand buttons using provided selectors"""
        clicked_count = 0
        
        for selector in selectors:
            try:
                # Handle text-based selectors
                if ':has-text(' in selector or ':contains(' in selector:
                    if ':has-text(' in selector:
                        text_to_find = selector.split(':has-text("')[1].split('")')[0]
                        base_selector = selector.split(':has-text(')[0]
                    else:  # :contains(
                        text_to_find = selector.split(':contains("')[1].split('")')[0]
                        base_selector = selector.split(':contains(')[0]
                    
                    elements = driver.find_elements(By.CSS_SELECTOR, base_selector)
                    for element in elements:
                        try:
                            element_text = element.text.lower()
                            if text_to_find.lower() in element_text:
                                if element.is_displayed() and element.is_enabled():
                                    logging.info(f"{category}: Found expandable element: '{element.text[:50]}...'")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", element)
                                    clicked_count += 1
                                    logging.info(f"{category}: Successfully expanded content")
                                    time.sleep(2)  # Wait for content to load
                        except Exception as e:
                            logging.debug(f"Failed to click {category} element: {e}")
                else:
                    # Regular CSS selector
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                # Check if it's actually an expand button
                                element_text = element.text.lower()
                                if any(keyword in element_text for keyword in ['more', 'expand', 'read', 'show', 'see']):
                                    logging.info(f"{category}: Found expand button: '{element.text[:30]}...' with selector {selector}")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", element)
                                    clicked_count += 1
                                    logging.info(f"{category}: Successfully clicked expand button")
                                    time.sleep(2)  # Wait for content to load
                        except Exception as e:
                            logging.debug(f"Failed to click {category} element with {selector}: {e}")
                            
            except Exception as e:
                logging.debug(f"{category} selector {selector} failed: {e}")
                continue
        
        return clicked_count
    
    @staticmethod
    def get_expanded_content_length(driver):
        """Get the total content length after expansion"""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            return len(body_text)
        except:
            return 0
    
    @staticmethod
    def detect_truncated_content(driver):
        """Detect if content appears to be truncated"""
        truncation_indicators = [
            "... Show more",
            "... Read more", 
            "... See more",
            "Show more",
            "Read more",
            "Continue reading",
            "[Show more]",
            "(more)",
            "See full episode description",
            "View full description"
        ]
        
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            found_indicators = []
            for indicator in truncation_indicators:
                if indicator in page_text:
                    found_indicators.append(indicator)
            
            if found_indicators:
                logging.info(f"Detected truncated content indicators: {found_indicators}")
                return True
            return False
        except Exception as e:
            logging.debug(f"Error detecting truncated content: {e}")
            return False

def expand_content_for_platform(driver, url):
    """
    Main function to expand content based on URL platform
    
    Args:
        driver: Selenium WebDriver instance
        url: URL to determine platform-specific expansion
    
    Returns:
        dict: Expansion results with before/after content lengths
    """
    if not driver:
        return {"error": "No driver provided"}
    
    # Get initial content length
    initial_length = ContentExpander.get_expanded_content_length(driver)
    
    # Detect platform
    platform_hint = None
    if 'spotify.com' in url:
        platform_hint = 'spotify'
    elif any(domain in url for domain in ['substack.com', 'mailchi.mp', 'newsletter']):
        platform_hint = 'newsletter'
    
    # Check if content appears truncated
    is_truncated = ContentExpander.detect_truncated_content(driver)
    
    # Expand content (try multiple times if needed)
    expanded_count = 0
    max_attempts = 3
    
    for attempt in range(max_attempts):
        attempt_count = ContentExpander.expand_all_content(driver, platform_hint)
        expanded_count += attempt_count
        
        if attempt_count == 0:
            break  # No more content to expand
        
        logging.info(f"Expansion attempt {attempt + 1}: {attempt_count} sections expanded")
        time.sleep(1)  # Wait between attempts
    
    # Get final content length
    final_length = ContentExpander.get_expanded_content_length(driver)
    
    return {
        "success": True,
        "platform": platform_hint or "unknown",
        "initial_length": initial_length,
        "final_length": final_length,
        "content_expanded": final_length > initial_length,
        "expansion_count": expanded_count,
        "was_truncated": is_truncated,
        "improvement": final_length - initial_length
    }