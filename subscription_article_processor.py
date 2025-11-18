#!/usr/bin/env python3
"""
Subscription Article Processor - Phase 2
Handles credential-aware article processing with browser automation
"""
import logging
import requests
from urllib.parse import urlparse
from browser_automation import extract_content_with_login
from subscription_detector import SubscriptionDetector

class SubscriptionArticleProcessor:
    def __init__(self):
        self.subscription_detector = SubscriptionDetector()
        
    def get_user_credentials(self, user_id, domain):
        """Get stored credentials for user and domain"""
        try:
            import psycopg2
            import os
            
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                database=os.getenv('DB_NAME', 'audiotours'),
                user=os.getenv('DB_USER', 'admin'),
                password=os.getenv('DB_PASSWORD', 'password123'),
                port=os.getenv('DB_PORT', '5433')
            )
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT decrypted_username, decrypted_password 
                FROM user_subscription_credentials 
                WHERE device_id = %s AND domain = %s
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, domain))
            
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if result:
                return {
                    'username': result[0],
                    'password': result[1]
                }
            return None
            
        except Exception as e:
            logging.error(f"Error getting user credentials: {e}")
            return None
    
    def process_article_with_subscription(self, article_url, article_content, user_id):
        """
        Process article with subscription awareness
        Returns: (processed_content, subscription_required, subscription_domain)
        """
        try:
            # Check if subscription is required
            is_subscription_required, subscription_domain = self.subscription_detector.detect_subscription_requirement(
                article_url, article_content
            )
            
            if not is_subscription_required:
                # No subscription needed, return original content
                return article_content, False, None
            
            # Subscription required - check if user has credentials
            credentials = self.get_user_credentials(user_id, subscription_domain)
            
            if not credentials:
                # No credentials available - return original content with subscription flag
                logging.info(f"No credentials found for {subscription_domain}, marking as subscription required")
                return article_content, True, subscription_domain
            
            # Try to extract content with credentials
            try:
                authenticated_content = self.extract_with_credentials(article_url, credentials)
                if authenticated_content and len(authenticated_content) > len(article_content):
                    # Successfully extracted premium content
                    logging.info(f"Successfully extracted premium content with credentials for {subscription_domain}")
                    # Still mark as subscription_required for statistics, but content is accessible
                    return authenticated_content, True, subscription_domain
                else:
                    # Credentials didn't help, return original
                    logging.warning(f"Credentials for {subscription_domain} didn't improve content extraction")
                    return article_content, True, subscription_domain
                    
            except Exception as auth_error:
                logging.error(f"Authentication failed for {subscription_domain}: {auth_error}")
                # Authentication failed, return original content
                return article_content, True, subscription_domain
                
        except Exception as e:
            logging.error(f"Error in subscription processing: {e}")
            # On error, return original content without subscription requirement
            return article_content, False, None
    
    def extract_with_credentials(self, article_url, credentials):
        """Extract article content using stored credentials"""
        try:
            domain = urlparse(article_url).netloc
            
            # Use browser automation for authenticated content extraction
            if 'bostonglobe.com' in domain:
                return self.extract_boston_globe_with_login(article_url, credentials)
            else:
                # Generic authenticated extraction
                return self.extract_generic_with_login(article_url, credentials)
                
        except Exception as e:
            logging.error(f"Error extracting with credentials: {e}")
            raise
    
    def extract_boston_globe_with_login(self, article_url, credentials):
        """Extract Boston Globe article with enhanced authentication"""
        try:
            from boston_globe_auth_enhanced import BostonGlobeAuthenticator
            
            authenticator = BostonGlobeAuthenticator()
            result = authenticator.authenticate_and_extract(article_url, credentials)
            
            if result['success']:
                logging.info(f"Boston Globe enhanced authentication successful: {len(result['content'])} chars")
                return result['content']
            else:
                error_msg = result.get('error', 'Unknown authentication error')
                logging.error(f"Boston Globe enhanced authentication failed: {error_msg}")
                raise Exception(error_msg)
                
        except ImportError:
            logging.warning("Enhanced Boston Globe authenticator not available, falling back to basic method")
            # Fallback to basic authentication if enhanced module not available
            return self._extract_boston_globe_basic(article_url, credentials)
        except Exception as e:
            logging.error(f"Boston Globe enhanced authentication failed: {e}")
            raise
            
    def _extract_boston_globe_basic(self, article_url, credentials):
        """Basic Boston Globe authentication fallback"""
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.chrome.options import Options
            
            # Setup Chrome with stealth options
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
                # Navigate to Boston Globe login
                driver.get("https://www.bostonglobe.com/login")
                
                # Wait for login form
                wait = WebDriverWait(driver, 10)
                
                # Enter credentials
                email_field = wait.until(EC.presence_of_element_located((By.NAME, "email")))
                email_field.send_keys(credentials['username'])
                
                password_field = driver.find_element(By.NAME, "password")
                password_field.send_keys(credentials['password'])
                
                # Submit login
                login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                login_button.click()
                
                # Wait for login to complete
                wait.until(EC.url_changes("https://www.bostonglobe.com/login"))
                
                # Navigate to article
                driver.get(article_url)
                
                # Wait for article content to load
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "article")))
                
                # Extract article content
                article_selectors = [
                    'article .article-content',
                    '.story-content',
                    '.article-body',
                    'article'
                ]
                
                content = ""
                for selector in article_selectors:
                    try:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        if element:
                            content = element.text
                            if len(content) > 200:
                                break
                    except:
                        continue
                
                if content and len(content) > 200:
                    logging.info(f"Boston Globe basic authentication successful: {len(content)} chars")
                    return content
                else:
                    raise Exception("Insufficient content extracted after login")
                    
            finally:
                driver.quit()
                
        except Exception as e:
            logging.error(f"Boston Globe basic authentication failed: {e}")
            raise
    
    def extract_generic_with_login(self, article_url, credentials):
        """Generic authenticated content extraction"""
        try:
            # Use browser automation with login
            result = extract_content_with_login(article_url, credentials)
            
            if result.get('success'):
                return result['content']
            else:
                raise Exception(result.get('error', 'Generic authentication failed'))
                
        except Exception as e:
            logging.error(f"Generic authenticated extraction failed: {e}")
            raise
    
    def reprocess_articles_with_credentials(self, user_id, domain, newsletter_id=None):
        """
        Reprocess all subscription articles for a domain with new credentials
        Returns count of successfully reprocessed articles
        """
        try:
            import psycopg2
            import os
            
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                database=os.getenv('DB_NAME', 'audiotours'),
                user=os.getenv('DB_USER', 'admin'),
                password=os.getenv('DB_PASSWORD', 'password123'),
                port=os.getenv('DB_PORT', '5433')
            )
            cursor = conn.cursor()
            
            # Find subscription articles for this domain/user
            if newsletter_id:
                # Reprocess only articles from specific newsletter
                cursor.execute("""
                    SELECT ar.article_id, ar.url, ar.request_string
                    FROM article_requests ar
                    JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
                    WHERE nal.newsletters_id = %s 
                    AND ar.subscription_required = true 
                    AND ar.subscription_domain = %s
                """, (newsletter_id, domain))
            else:
                # Reprocess all articles for this domain
                cursor.execute("""
                    SELECT article_id, url, request_string
                    FROM article_requests
                    WHERE subscription_required = true 
                    AND subscription_domain = %s
                """, (domain,))
            
            articles_to_reprocess = cursor.fetchall()
            logging.info(f"Found {len(articles_to_reprocess)} articles to reprocess for {domain}")
            
            reprocessed_count = 0
            credentials = self.get_user_credentials(user_id, domain)
            
            if not credentials:
                logging.error(f"No credentials found for {domain}")
                cursor.close()
                conn.close()
                return 0
            
            for article_id, article_url, article_title in articles_to_reprocess:
                try:
                    # Extract premium content with credentials
                    premium_content = self.extract_with_credentials(article_url, credentials)
                    
                    if premium_content and len(premium_content) > 200:
                        # Create new audio edition via orchestrator
                        payload = {
                            'article_text': f"PREMIUM ARTICLE: {article_title}\n\nCONTENT: {premium_content}",
                            'request_string': article_title,
                            'secret_id': user_id,
                            'major_points_count': 4
                        }
                        
                        orchestrator_response = requests.post(
                            'http://news-orchestrator-1:5012/generate-news',
                            json=payload,
                            timeout=180,
                            headers={'Content-Type': 'application/json; charset=utf-8'}
                        )
                        
                        if orchestrator_response.status_code == 200:
                            # Update article with new content (keep subscription_required=true for statistics)
                            cursor.execute("""
                                UPDATE article_requests 
                                SET article_text = %s, status = 'finished'
                                WHERE article_id = %s
                            """, (premium_content, article_id))
                            
                            reprocessed_count += 1
                            logging.info(f"Successfully reprocessed article {article_id}")
                        else:
                            logging.error(f"Orchestrator failed for article {article_id}")
                    else:
                        logging.warning(f"Insufficient premium content for article {article_id}")
                        
                except Exception as e:
                    logging.error(f"Failed to reprocess article {article_id}: {e}")
                    continue
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logging.info(f"Reprocessed {reprocessed_count}/{len(articles_to_reprocess)} articles for {domain}")
            return reprocessed_count
            
        except Exception as e:
            logging.error(f"Error reprocessing articles: {e}")
            return 0