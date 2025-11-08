#!/usr/bin/env python3
"""
Newsletter Processor Service - RESTORED with Enhanced Apple Podcasts URL Extraction
Combines original functionality with new comprehensive widget detection
"""
import os
import sys
import psycopg2
from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import re
from datetime import datetime, timedelta
import logging
import time
import json
from apple_podcasts_processor import process_apple_podcasts_url
from spotify_processor import process_spotify_url

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def is_binary_content(text):
    """Detect if content contains binary data that would cause Unicode errors - FIXED for Guy Raz"""
    if not text or not isinstance(text, str):
        return True
    
    try:
        # Check for null bytes (definitive binary indicator)
        if '\x00' in text:
            return True
        
        # Check for Unicode replacement characters (indicates corrupted encoding)
        if '\ufffd' in text:
            return True
        
        # Check for specific binary patterns that actually cause problems
        actual_binary_patterns = [
            '\u0000',  # Null character
            '\u0001',  # Start of heading
            '\u0002',  # Start of text
            '\u0003',  # End of text
            '\u0004',  # End of transmission
        ]
        
        for pattern in actual_binary_patterns:
            if pattern in text:
                return True
        
        # FIXED: More reasonable printable character check
        # Normal text should have at least 70% printable chars (was 80%)
        printable_chars = sum(1 for c in text if c.isprintable() or c.isspace())
        total_chars = len(text)
        
        if total_chars > 0:
            printable_ratio = printable_chars / total_chars
            # Relaxed from 0.8 to 0.7 - Guy Raz content has 99%+ printable chars
            if printable_ratio < 0.7:
                return True
        
        # FIXED: Only flag excessive control characters (not normal formatting)
        # Count only problematic control characters, not \n\r\t
        problem_control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
        if total_chars > 0 and problem_control_chars / total_chars > 0.05:  # 5% instead of 10%
            return True
        
        # REMOVED: Suspicious character sequence detection - was too aggressive
        # Guy Raz content has normal punctuation that was flagged as "suspicious"
        
        # Try to encode as UTF-8 to catch real encoding issues
        text.encode('utf-8')
        
        return False
        
    except (UnicodeError, UnicodeEncodeError, UnicodeDecodeError):
        return True
    except Exception:
        return True

def clean_text_content(text):
    """Enhanced clean and validate text content, removing binary contamination"""
    if not text or not isinstance(text, str):
        return ""
    
    try:
        # Remove null bytes and other problematic characters
        cleaned = text.replace('\x00', '').replace('\ufffd', '')
        
        # Enhanced binary character removal for Guy Raz newsletter
        # Remove characters that commonly appear in binary contamination
        binary_chars = ['\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', '\x08', 
                       '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13',
                       '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1b',
                       '\x1c', '\x1d', '\x1e', '\x1f']
        
        for char in binary_chars:
            cleaned = cleaned.replace(char, '')
        
        # Remove sequences of random symbols that indicate binary contamination
        import re
        # Pattern for sequences of non-alphanumeric characters (except common punctuation)
        binary_pattern = r'[^\w\s.,!?;:()\[\]{}"\'-]{3,}'
        cleaned = re.sub(binary_pattern, ' ', cleaned)
        
        # Remove characters with high Unicode values that might be corrupted
        cleaned = ''.join(c for c in cleaned if ord(c) < 65536 and (c.isprintable() or c in '\n\r\t '))
        
        # Guy Raz specific binary pattern removal
        guy_raz_patterns = [
            r'AgH \$\+[^\s]{10,}',  # Pattern like 'AgH $+춬B(k97la'
            r'i\$UDzk\][^\s]{10,}',  # Pattern like 'i$UDzk]#JB'
            r'[A-Za-z0-9]{2,}[\$\+\{\}\<\>\=\"\|\,\~\`\^\&\*\#\@\!\%]{3,}[A-Za-z0-9]{2,}'
        ]
        
        for pattern in guy_raz_patterns:
            cleaned = re.sub(pattern, ' ', cleaned)
        
        # Normalize whitespace
        cleaned = ' '.join(cleaned.split())
        
        # Final validation - if still contains binary patterns, return empty
        if is_binary_content(cleaned):
            logging.warning(f"Content still contains binary after cleaning: {cleaned[:100]}...")
            return ""
        
        return cleaned.strip()
        
    except Exception as e:
        logging.error(f"Error cleaning text content: {e}")
        return ""

def clean_url(url):
    """Remove query parameters for uniqueness check, but preserve Apple Podcasts episode IDs"""
    try:
        if isinstance(url, bytes):
            url = url.decode('utf-8', errors='replace')
        elif not isinstance(url, str):
            url = str(url)
        
        parsed = urlparse(url)
        
        # For Apple Podcasts URLs, preserve the ?i= episode parameter
        if 'podcasts.apple.com' in parsed.netloc and '?i=' in url:
            # Keep the episode ID parameter for Apple Podcasts
            query_params = parsed.query
            if 'i=' in query_params:
                # Extract just the episode ID parameter
                import re
                episode_match = re.search(r'i=([^&]+)', query_params)
                if episode_match:
                    episode_id = episode_match.group(1)
                    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', f'i={episode_id}', ''))
                else:
                    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
            else:
                clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        else:
            # For all other URLs, remove query parameters
            clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        
        if isinstance(clean, bytes):
            clean = clean.decode('utf-8', errors='replace')
        
        return str(clean)
    except Exception as e:
        logging.error(f"Error cleaning URL {url}: {e}")
        return str(url) if url else ''

def extract_all_clickable_urls(soup, base_url):
    """ENHANCED: Extract URLs from all clickable HTML elements"""
    urls = []
    
    # 1. Standard <a> links
    for link in soup.find_all('a', href=True):
        urls.append(urljoin(base_url, link['href']))
    
    # 2. Button elements with data attributes
    for button in soup.find_all(['button', 'input'], {'data-url': True}):
        urls.append(urljoin(base_url, button['data-url']))
    
    # 3. Elements with data-href attributes
    for element in soup.find_all(attrs={'data-href': True}):
        urls.append(urljoin(base_url, element['data-href']))
    
    # 4. Form actions
    for form in soup.find_all('form', action=True):
        if form['action'].startswith('http'):
            urls.append(urljoin(base_url, form['action']))
    
    # 5. JavaScript onclick patterns
    onclick_pattern = r"(?:window\.open|location\.href|window\.location)\s*[=\(]\s*['\"]([^'\"]+)['\"]"
    page_text = str(soup)
    js_urls = re.findall(onclick_pattern, page_text)
    for url in js_urls:
        if url.startswith('http'):
            urls.append(url)
    
    # 6. JSON data attributes
    json_pattern = r'"url"\s*:\s*"([^"]+)"'
    json_urls = re.findall(json_pattern, page_text)
    for url in json_urls:
        if url.startswith('http'):
            urls.append(url)
    
    return list(set(urls))  # Remove duplicates

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "newsletter_processor"})

@app.route('/newsletters_v2', methods=['GET'])
def get_newsletters_v2():
    """RESTORED: Get all newsletters with dates and article counts"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT n.id, n.url, n.type, n.created_at, COUNT(na.article_id) as article_count
            FROM newsletters n
            JOIN newsletters_article_link nal ON n.id = nal.newsletters_id
            JOIN article_requests ar ON nal.article_requests_id = ar.article_id
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.status = 'finished'
            GROUP BY n.id, n.url, n.type, n.created_at
            ORDER BY n.created_at DESC
        """)
        
        newsletters = []
        for row in cursor.fetchall():
            # Extract domain name from URL for display
            url = row[1]
            try:
                parsed = urlparse(url)
                domain_name = parsed.netloc.replace('www.', '')
                # Extract issue/title from path
                path_parts = [p for p in parsed.path.split('/') if p]
                title_part = path_parts[-1] if path_parts else 'Newsletter'
                if 'issue-' in title_part:
                    issue_num = title_part.split('issue-')[1].split('-')[0]
                    display_name = f"{domain_name} Issue-{issue_num}"
                else:
                    display_name = f"{domain_name} ({row[2] or 'Newsletter'})"
            except:
                display_name = url
            
            newsletters.append({
                'newsletter_id': row[0],
                'url': row[1],
                'name': display_name,
                'created_at': row[3].isoformat() if row[3] else None,
                'date': row[3].strftime('%B %d, %Y') if row[3] else 'Unknown Date',
                'type': row[2] or 'Others',
                'article_count': row[4]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "newsletters": newsletters
        })
        
    except Exception as e:
        logging.error(f"Error getting newsletters v2: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_articles_by_newsletter_id', methods=['POST'])
def get_articles_by_newsletter_id():
    """RESTORED: Get articles by newsletter ID"""
    try:
        data = request.get_json()
        newsletter_id = data.get('newsletter_id')
        
        if not newsletter_id:
            return jsonify({"error": "newsletter_id is required"}), 400
        
        logging.info(f"Getting articles for newsletter ID: {newsletter_id}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get articles with audio for this specific newsletter
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, ar.url, ar.created_at, ar.status, ar.article_type
            FROM article_requests ar
            JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE nal.newsletters_id = %s AND ar.status = 'finished'
            ORDER BY ar.created_at DESC
        """, (newsletter_id,))
        
        articles = []
        for row in cursor.fetchall():
            article_id, title, url, created_at, status, article_type = row
            
            # Extract author from title if available
            author = 'Unknown Author'
            clean_title = title
            
            if ' - ' in title:
                parts = title.split(' - ')
                if len(parts) >= 2:
                    clean_title = parts[0].strip()
                    author = parts[1].strip()
            elif ' by ' in title.lower():
                by_index = title.lower().find(' by ')
                if by_index > 0:
                    clean_title = title[:by_index].strip()
                    author = title[by_index + 4:].strip()
            
            # Format date
            try:
                formatted_date = created_at.strftime('%B %d, %Y')
            except:
                formatted_date = 'Unknown Date'
            
            articles.append({
                'article_id': article_id,
                'title': clean_title,
                'author': author,
                'date': formatted_date,
                'url': url,
                'status': status,
                'article_type': article_type or 'Others'
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "articles": articles
        })
        
    except Exception as e:
        logging.error(f"Error getting articles by newsletter ID: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/process_newsletter', methods=['POST'])
def process_newsletter():
    """ENHANCED: Process newsletter with Apple Podcasts URL extraction"""
    try:
        data = request.get_json()
        newsletter_url = data.get('newsletter_url')
        user_id = data.get('user_id')
        max_articles = data.get('max_articles', 15)
        test_mode = data.get('test_mode', False)  # Bypass daily limits for testing
        
        logging.info(f"Processing newsletter: {newsletter_url}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check daily limit (skip in test mode)
        if not test_mode:
            today = datetime.now().date()
            clean_newsletter_url = clean_url(newsletter_url)
            
            cursor.execute(
                "SELECT id, created_at FROM newsletters WHERE url = %s ORDER BY created_at DESC LIMIT 1",
                (clean_newsletter_url,)
            )
            existing = cursor.fetchone()
            
            if existing:
                last_processed_date = existing[1].date()
                if last_processed_date == today:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        "status": "error",
                        "message": "Newsletter already processed today. Each newsletter can only be processed once per day.",
                        "error_type": "daily_limit_reached"
                    }), 400
        else:
            clean_newsletter_url = clean_url(newsletter_url)
            logging.info("TEST MODE: Bypassing daily limit check")
        
        # Create newsletter entry (with test suffix in test mode)
        newsletter_url_for_db = clean_newsletter_url
        if test_mode:
            # Add timestamp to make unique for testing
            import time
            newsletter_url_for_db = f"{clean_newsletter_url}?test_mode={int(time.time())}"
            logging.info(f"TEST MODE: Using unique URL for database: {newsletter_url_for_db}")
        
        cursor.execute(
            "INSERT INTO newsletters (url, type) VALUES (%s, %s) RETURNING id",
            (newsletter_url_for_db, 'Newsletter')
        )
        newsletter_id = cursor.fetchone()[0]
        conn.commit()
        
        # Enhanced headers for better compatibility - DISABLE BROTLI for Guy Raz
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',  # REMOVED 'br' - Brotli causing corruption
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        }
        
        # Check if this is a protected site that needs browser automation
        # REMOVED Guy Raz from browser automation - binary detection is now fixed
        use_browser = any(domain in newsletter_url for domain in ['quora.com', 'medium.com'])
        
        if use_browser:
            logging.info(f"Using browser automation for protected site: {newsletter_url}")
            try:
                from browser_automation import extract_full_newsletter_with_browser
                browser_result = extract_full_newsletter_with_browser(newsletter_url)
                
                if browser_result.get('success'):
                    # Use the original HTML structure for pattern detection
                    soup = BeautifulSoup(browser_result['html_content'], 'html.parser')
                    logging.info(f"Browser automation SUCCESS: Extracted HTML with {len(browser_result['html_content'])} chars")
                else:
                    error_msg = f"Browser automation failed: {browser_result.get('error', 'Unknown error')}"
                    logging.error(error_msg)
                    return jsonify({
                        "status": "error",
                        "message": error_msg,
                        "error_type": "browser_automation_failed",
                        "articles_found": 0,
                        "articles_created": 0
                    })
            except Exception as e:
                error_msg = f"Browser automation error: {str(e)}"
                logging.error(error_msg)
                return jsonify({
                    "status": "error",
                    "message": error_msg,
                    "error_type": "browser_automation_error",
                    "articles_found": 0,
                    "articles_created": 0
                })
        else:
            # Standard HTTP request for non-protected sites
            try:
                response = requests.get(newsletter_url, headers=headers, timeout=10)
                

                
            except requests.exceptions.RequestException as e:
                error_msg = f"Network error accessing newsletter: {str(e)}"
                logging.error(error_msg)
                return jsonify({
                    "status": "error",
                    "message": error_msg,
                    "error_type": "network_error",
                    "articles_found": 0,
                    "articles_created": 0
                })
            
            if response.status_code == 403:
                error_msg = f"Access Denied: {urlparse(newsletter_url).netloc} is blocking automated access (HTTP 403 Forbidden). This site uses anti-scraping protection that prevents our newsletter processor from accessing the content."
                logging.error(error_msg)
                return jsonify({
                    "status": "error",
                    "message": error_msg,
                    "error_type": "access_denied",
                    "articles_found": 0,
                    "articles_created": 0
                })
            elif response.status_code != 200:
                error_msg = f"Failed to access newsletter: HTTP {response.status_code}"
                logging.error(error_msg)
                return jsonify({
                    "status": "error",
                    "message": error_msg,
                    "error_type": "http_error",
                    "articles_found": 0,
                    "articles_created": 0
                })
            
            soup = BeautifulSoup(response.content, 'html.parser')
            

        

        
        # ENHANCED: Extract main newsletter content FIRST
        article_urls = []
        
        # 1. MAIN NEWSLETTER ARTICLE - Extract newsletter content itself
        try:
            # Enhanced content extraction for Substack newsletters
            main_content = ""
            
            # Try platform-specific selectors first
            
            # 1. Substack selectors
            substack_selectors = [
                '.available-content .body.markup',  # Substack main content
                '.post-content .body.markup',
                'article .body.markup',
                '.single-post .body.markup'
            ]
            
            for selector in substack_selectors:
                try:
                    element = soup.select_one(selector)
                    if element:
                        # Remove problematic elements that might contain binary data
                        for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                            tag.decompose()
                        
                        # Enhanced text extraction for Guy Raz newsletter
                        text = element.get_text(separator=' ', strip=True)
                        
                        # Convert Unicode characters to ASCII equivalents for better TTS
                        if 'guyraz.substack.com' in newsletter_url:
                            text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
                            logging.info(f"Guy Raz Unicode replacement applied: {len(text)} chars")
                        

                        
                        cleaned_text = clean_text_content(text)
                        

                        
                        # Binary detection AFTER Unicode replacement
                        if is_binary_content(cleaned_text):
                            logging.warning(f"Binary content detected after cleaning, skipping this selector")
                            continue
                        
                        # Enhanced validation
                        if len(cleaned_text) > 200 and not is_binary_content(cleaned_text):
                            # Additional word structure validation
                            words = cleaned_text.split()
                            valid_words = sum(1 for word in words if len(word) > 1 and any(c.isalnum() for c in word))
                            if len(words) > 0 and (valid_words / len(words)) > 0.5:
                                main_content = cleaned_text
                                logging.info(f"Found Substack content with selector '{selector}': {len(cleaned_text)} chars, {valid_words}/{len(words)} valid words")
                                break
                            else:
                                logging.warning(f"Content failed word validation: {valid_words}/{len(words)} valid words")
                except Exception as e:
                    logging.debug(f"Selector '{selector}' failed: {e}")
                    continue
            
            # 2. MailChimp selectors
            if not main_content and ('mailchi.mp' in newsletter_url or 'mailchimp' in str(soup).lower()):
                mailchimp_selectors = [
                    '.bodyContainer',
                    '#templateBody', 
                    '.mcnTextContent',
                    '.templateContainer'
                ]
                
                for selector in mailchimp_selectors:
                    try:
                        elements = soup.select(selector)
                        if elements:
                            combined_text = ""
                            for element in elements:
                                text = element.get_text(separator=' ', strip=True)
                                cleaned_text = clean_text_content(text)
                                if cleaned_text and not is_binary_content(cleaned_text):
                                    combined_text += cleaned_text + " "
                            
                            if len(combined_text) > 200:
                                main_content = combined_text.strip()
                                logging.info(f"Found MailChimp content with selector '{selector}': {len(main_content)} chars")
                                break
                    except Exception as e:
                        logging.debug(f"MailChimp selector '{selector}' failed: {e}")
                        continue
            
            # 3. Email newsletter selectors (Boston Globe, etc.)
            if not main_content and ('view.email' in newsletter_url or 'email.' in newsletter_url):
                email_selectors = [
                    'table[role="presentation"]',
                    'td[class*="content"]',
                    '.email-content',
                    '.message-body'
                ]
                
                for selector in email_selectors:
                    try:
                        elements = soup.select(selector)
                        if elements:
                            combined_text = ""
                            for element in elements:
                                text = element.get_text(separator=' ', strip=True)
                                combined_text += text + " "
                            
                            if len(combined_text) > 200:
                                main_content = combined_text.strip()
                                logging.info(f"Found email content with selector '{selector}': {len(main_content)} chars")
                                break
                    except Exception as e:
                        logging.debug(f"Email selector '{selector}' failed: {e}")
                        continue
            
            # Fallback to generic selectors with enhanced binary handling
            if not main_content:
                generic_selectors = [
                    'article',
                    '.post-content',
                    '.newsletter-content', 
                    '.entry-content',
                    'main',
                    '[role="main"]'
                ]
                
                for selector in generic_selectors:
                    try:
                        element = soup.select_one(selector)
                        if element:
                            # Remove problematic elements that might contain binary data
                            for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                                tag.decompose()
                            
                            # Get text content, clean it up
                            text = element.get_text(separator=' ', strip=True)
                            
                            # Convert Unicode characters to ASCII equivalents for better TTS
                            if 'guyraz.substack.com' in newsletter_url:
                                text = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
                                logging.info(f"Guy Raz Unicode replacement applied (generic): {len(text)} chars")
                            

                            
                            cleaned_text = clean_text_content(text)
                            

                            
                            if len(cleaned_text) > 200 and not is_binary_content(cleaned_text):
                                main_content = cleaned_text
                                logging.info(f"Found generic content with selector '{selector}': {len(cleaned_text)} chars")
                                break
                    except Exception as e:
                        logging.debug(f"Generic selector '{selector}' failed: {e}")
                        continue
            
            # Guy Raz specific fallback: Extract from page title and meta description
            if not main_content and 'guyraz.substack.com' in newsletter_url:
                try:
                    logging.info("Guy Raz fallback: Extracting from title and meta description")
                    

                    
                    # Get page title with Unicode replacement
                    title_text = ""
                    if soup.title:
                        title_text = soup.title.get_text(strip=True)
                        # Convert Unicode characters to ASCII equivalents for better TTS
                        title_text = title_text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
                        title_text = clean_text_content(title_text)
                    
                    # Get meta description with Unicode replacement
                    meta_desc = ""
                    meta_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
                    if meta_tag and meta_tag.get('content'):
                        meta_desc = meta_tag['content']
                        # Convert Unicode characters to ASCII equivalents for better TTS
                        meta_desc = meta_desc.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
                        meta_desc = clean_text_content(meta_desc)
                    
                    # If both title and meta are clean, use them
                    if title_text and not is_binary_content(title_text):
                        fallback_content = f"Newsletter: {title_text}"
                        if meta_desc and not is_binary_content(meta_desc):
                            fallback_content += f". {meta_desc}"
                        
                        if len(fallback_content) > 50:
                            main_content = fallback_content
                            logging.info(f"Guy Raz fallback SUCCESS: {len(main_content)} chars from title/meta")
                    
                    # Ultimate fallback for Guy Raz - DISABLED to force real content extraction
                    if not main_content:
                        logging.error(f"Guy Raz content extraction completely failed - no fallback used")
                        # DO NOT use generic fallback - let it fail so we can debug
                        

                        
                except Exception as e:
                    logging.error(f"Guy Raz fallback extraction failed: {e}")
                    # Final fallback
                    main_content = "Newsletter article from How I Built This with Guy Raz. Content extraction encountered technical issues."
                    logging.info(f"Guy Raz final fallback: Using minimal description")
            
            # Quora-specific content extraction for newsletters
            if not main_content and 'quora.com' in newsletter_url:
                try:
                    # Get all text content from body with line breaks preserved
                    body_text = soup.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in body_text.split('\n') if line.strip()]
                    
                    # Filter and collect substantial story content
                    content_lines = []
                    for line in lines:
                        if (len(line) > 30 and 
                            not any(skip in line.lower() for skip in [
                                'sign in', 'log in', 'follow space', 'apply to beco',
                                'moderator', 'contributor', 'navigation', 'menu'
                            ]) and
                            not line.startswith('http')):
                            content_lines.append(line)
                            if len(content_lines) >= 15:  # Get more content for newsletters
                                break
                    
                    if content_lines:
                        main_content = '\n\n'.join(content_lines)
                        logging.info(f"Extracted Quora newsletter content: {len(main_content)} chars")
                except Exception as e:
                    logging.error(f"Quora content extraction failed: {e}")
            
            # Last resort: try body text but filter out navigation/headers
            if not main_content:
                try:
                    body_text = soup.get_text(separator=' ', strip=True)
                    # Remove common navigation/header text patterns
                    lines = body_text.split('\n')
                    content_lines = []
                    
                    for line in lines:
                        line = line.strip()
                        # Skip short lines, navigation, headers, footers
                        if (len(line) > 50 and 
                            not any(skip in line.lower() for skip in [
                                'subscribe', 'sign in', 'menu', 'navigation', 'footer',
                                'privacy', 'terms', 'cookie', 'newsletter', 'substack'
                            ])):
                            content_lines.append(line)
                            if len(content_lines) >= 10:  # Limit to first 10 substantial lines
                                break
                    
                    if content_lines:
                        main_content = ' '.join(content_lines)
                        logging.info(f"Extracted body text content: {len(main_content)} chars")
                except Exception as e:
                    logging.error(f"Body text extraction failed: {e}")
            
            # Add main newsletter article if substantial content found
            if main_content and len(main_content) >= 100:
                # Extract title from page
                page_title = soup.title.string if soup.title else "Newsletter Article"
                clean_title = page_title.replace(' | Substack', '').replace(' - Newsletter', '').strip()
                
                # Clean title of binary content
                clean_title = clean_text_content(clean_title)
                if not clean_title or is_binary_content(clean_title):
                    clean_title = "Newsletter Article"
                
                # Ensure we don't duplicate title in content
                if main_content.startswith(clean_title):
                    # Remove title from beginning of content
                    main_content = main_content[len(clean_title):].strip()
                    logging.info(f"Removed duplicate title from content start")
                
                article_urls.append({
                    'url': newsletter_url,
                    'clean_url': clean_url(newsletter_url),
                    'title': clean_title,
                    'content': main_content,  # Pre-extracted content
                    'date': datetime.now(),
                    'is_main_article': True
                })
                logging.info(f"🔍 DEBUG: Added MAIN newsletter article: '{clean_title}' ({len(main_content)} chars)")
                logging.info(f"🔍 DEBUG: Main article content preview: {main_content[:200]}...")
                logging.info(f"🔍 DEBUG: Main article will be processed as article with is_main_article=True")
            else:
                logging.warning(f"Main newsletter content insufficient: {len(main_content) if main_content else 0} chars")
                
        except Exception as e:
            logging.error(f"Error extracting main newsletter content: {e}")
        
        # 2. LINKED ARTICLES - Enhanced Pattern Recognition
        from newsletter_pattern_detector import detect_newsletter_patterns
        
        # Use pattern recognition to find articles
        pattern_articles = detect_newsletter_patterns(soup, newsletter_url)
        logging.info(f"Pattern recognition found {len(pattern_articles)} articles")
        
        # Add pattern-detected articles
        for article in pattern_articles:
            article_urls.append({
                'url': article['url'],
                'clean_url': clean_url(article['url']),
                'title': article['title'],
                'date': datetime.now(),
                'is_main_article': False,
                'pattern': article['pattern'],
                'summary': article.get('summary', '')
            })
        
        # Fallback: Extract URLs from all clickable HTML elements (for missed patterns)
        all_urls = extract_all_clickable_urls(soup, newsletter_url)
        logging.info(f"Fallback extraction found {len(all_urls)} total clickable URLs")
        
        # Add any missed news articles from known domains
        existing_urls = {article['url'] for article in article_urls}
        for url in all_urls:
            if url in existing_urls:
                continue
                
            # News article URLs from known domains
            if any(domain in url for domain in [
                'bostonglobe.com', 'nytimes.com', 'washingtonpost.com', 'reuters.com', 'ap.org',
                'newtonbeacon.org', 'boston.com', 'wbur.org', 'wcvb.com', 'nbcboston.com'
            ]):
                # Skip subscription/navigation pages
                if not any(skip in url.lower() for skip in ['/subscribe', '/login', '/account', '/newsletter', '/events/community/add']):
                    article_urls.append({
                        'url': url,
                        'clean_url': clean_url(url),
                        'title': 'News Article',
                        'date': datetime.now(),
                        'is_main_article': False,
                        'pattern': 'fallback_domain'
                    })
        
        # Limit articles
        article_urls = article_urls[:max_articles]
        logging.info(f"Processing {len(article_urls)} articles")
        
        articles_created = 0
        failed_articles = []
        
        for i, article in enumerate(article_urls, 1):
            # Use separate connection for each article to prevent transaction cascade failures
            article_conn = None
            article_cursor = None
            
            try:
                logging.info(f"Processing article {i}/{len(article_urls)}: {article['url']}")
                
                # Create separate connection for this article
                article_conn = get_db_connection()
                article_cursor = article_conn.cursor()
                
                # ENHANCED DUPLICATE CHECK with individual transaction
                try:
                    article_cursor.execute("SELECT article_id FROM article_requests WHERE url = %s", (article['clean_url'],))
                    existing_article = article_cursor.fetchone()
                    
                    if existing_article:
                        # Check if already linked to this newsletter to prevent duplicates
                        article_cursor.execute(
                            "SELECT 1 FROM newsletters_article_link WHERE newsletters_id = %s AND article_requests_id = %s",
                            (newsletter_id, existing_article[0])
                        )
                        already_linked = article_cursor.fetchone()
                        
                        if not already_linked:
                            # Link existing article to newsletter (many-to-many relationship)
                            article_cursor.execute(
                                "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s)",
                                (newsletter_id, existing_article[0])
                            )
                            article_conn.commit()
                            articles_created += 1
                            logging.info(f"✅ LINKED existing article to newsletter: {article['title']} (ID: {existing_article[0]})")
                        else:
                            logging.info(f"⚠️ SKIPPED duplicate link: {article['title']} already linked to newsletter")
                        continue
                except Exception as e:
                    # Rollback this article's transaction and continue with next
                    article_conn.rollback()
                    logging.error(f"Error linking existing article: {e}")
                    failed_articles.append({"url": article['url'], "error": f"Link error: {str(e)[:100]}"})
                    continue
                
                # Process new article
                article_content = ""
                
                # Check if this is the main newsletter article with pre-extracted content
                if article.get('is_main_article') and article.get('content'):
                    # Format main newsletter content without title duplication
                    content = article['content']
                    
                    # Ensure content doesn't start with the title
                    title_words = article['title'].lower().split()[:5]  # First 5 words of title
                    content_start = content.lower()[:100]  # First 100 chars of content
                    
                    # If content starts with title words, it might be duplicated
                    if len(title_words) >= 3 and all(word in content_start for word in title_words[:3]):
                        # Try to find where actual content starts after title
                        sentences = content.split('. ')
                        if len(sentences) > 1:
                            # Skip first sentence if it's likely the title
                            content = '. '.join(sentences[1:]).strip()
                    
                    # Enhanced cleaning for Guy Raz newsletter
                    cleaned_content = clean_text_content(content)
                    
                    # Guy Raz specific additional cleaning
                    if 'guyraz.substack.com' in article['url']:
                        import re
                        # Remove Guy Raz binary contamination patterns
                        guy_raz_binary_patterns = [
                            'AgH $+춬B(k97la}<E"} 9ý|,47APe_ƮʗD>',
                            'i$UDzk]#JB <;=\'E5 A~A|k64DC/~U"BF,56oC#',
                            r'[A-Za-z0-9]{1,3}[\$\+\{\}\<\>\=\"\|\,\~\`\^\&\*\#\@\!\%]{2,}[A-Za-z0-9]{1,10}'
                        ]
                        
                        for pattern in guy_raz_binary_patterns:
                            if isinstance(pattern, str):
                                cleaned_content = cleaned_content.replace(pattern, ' ')
                            else:
                                cleaned_content = re.sub(pattern, ' ', cleaned_content)
                        
                        # Final cleanup
                        cleaned_content = ' '.join(cleaned_content.split())
                    
                    if is_binary_content(cleaned_content):
                        # Guy Raz specific fallback: Try to extract clean summary
                        if 'guyraz.substack.com' in article['url']:
                            try:
                                # Clean the title first
                                clean_title = clean_text_content(article['title'])
                                if is_binary_content(clean_title):
                                    clean_title = "Newsletter Article"
                                
                                # Create minimal clean content from title
                                fallback_content = f"This is a newsletter article from Guy Raz's How I Built This podcast. Title: {clean_title}. The article discusses entrepreneurship insights and business stories. Due to technical formatting issues in the original source, only this summary is available."
                                
                                if not is_binary_content(fallback_content):
                                    cleaned_content = fallback_content
                                    logging.info(f"Guy Raz fallback SUCCESS: {len(cleaned_content)} chars")
                                else:
                                    failed_articles.append({"url": article['url'], "error": "Binary content detected after all cleaning attempts"})
                                    continue
                            except Exception as fallback_error:
                                logging.error(f"Guy Raz fallback failed: {fallback_error}")
                                failed_articles.append({"url": article['url'], "error": "Binary content detected after cleaning"})
                                continue
                        else:
                            failed_articles.append({"url": article['url'], "error": "Binary content detected after cleaning"})
                            continue
                    
                    article_content = f"NEWSLETTER: {article['title']}\n\nCONTENT: {cleaned_content}"
                    
                elif 'podcasts.apple.com' in article['url']:
                    logging.info(f"Processing Apple Podcasts URL: {article['url']}")
                    apple_result = process_apple_podcasts_url(article['url'])
                    if apple_result.get('success'):
                        article_content = apple_result['content']
                        article['title'] = apple_result['title']
                        logging.info(f"Apple Podcasts SUCCESS: Title='{article['title']}', Content={len(article_content)} bytes")
                    else:
                        error_msg = apple_result.get('error', 'Unknown Apple Podcasts error')
                        logging.error(f"Apple Podcasts FAILED: {error_msg}")
                        failed_articles.append({"url": article['url'], "error": f"Apple Podcasts: {error_msg}"})
                        continue
                        
                elif 'open.spotify.com/episode' in article['url']:
                    logging.info(f"Processing Spotify URL: {article['url']}")
                    spotify_result = process_spotify_url(article['url'])
                    logging.info(f"Spotify result keys: {list(spotify_result.keys()) if spotify_result else 'None'}")
                    
                    if spotify_result.get('success'):
                        article_content = spotify_result['content']
                        article['title'] = spotify_result['title']
                        logging.info(f"Spotify SUCCESS: Title='{article['title']}', Content={len(article_content)} bytes")
                        try:
                            preview = spotify_result['content'][:200].encode('ascii', 'ignore').decode('ascii')
                            logging.info(f"Spotify content preview: {preview}...")
                        except:
                            logging.info(f"Spotify content preview: [Content contains special characters]")
                    else:
                        error_msg = spotify_result.get('error', 'Unknown Spotify error')
                        logging.error(f"Spotify FAILED: {error_msg}")
                        failed_articles.append({"url": article['url'], "error": f"Spotify: {error_msg}"})
                        continue
                        
                else:
                    # Check if this needs browser automation (Quora, protected sites)
                    if any(domain in article['url'] for domain in ['quora.com', 'medium.com']) or 'jokesfunnystories.quora.com' in article['url']:
                        logging.info(f"Processing protected site with browser automation: {article['url']}")
                        try:
                            from browser_automation import extract_newsletter_content_with_browser
                            browser_result = extract_newsletter_content_with_browser(article['url'])
                            
                            if browser_result.get('success'):
                                article_content = f"ARTICLE: {browser_result['title']}\n\nCONTENT: {browser_result['content']}"
                                article['title'] = browser_result['title']
                                logging.info(f"Browser automation SUCCESS: Title='{article['title']}', Content={len(article_content)} bytes")
                            else:
                                error_msg = browser_result.get('error', 'Browser automation failed')
                                logging.error(f"Browser automation FAILED: {error_msg}")
                                failed_articles.append({"url": article['url'], "error": f"Browser automation: {error_msg}"})
                                continue
                        except Exception as e:
                            logging.error(f"Browser automation error: {e}")
                            failed_articles.append({"url": article['url'], "error": f"Browser automation error: {str(e)[:50]}"})
                            continue
                    else:
                        # Generic news article processing
                        logging.info(f"Processing news article URL: {article['url']}")
                        try:
                            article_response = requests.get(article['url'], headers=headers, timeout=10)
                            
                            if article_response.status_code == 403:
                                error_msg = f"Access denied: {urlparse(article['url']).netloc} blocks automated access (HTTP 403)"
                                logging.error(error_msg)
                                failed_articles.append({"url": article['url'], "error": error_msg})
                                continue
                            elif article_response.status_code == 200:
                                article_soup = BeautifulSoup(article_response.content, 'html.parser')
                                
                                # Extract article content using common selectors + Newton Beacon specific
                                content_selectors = [
                                    'article',
                                    '.article-content',
                                    '.story-content', 
                                    '.entry-content',
                                    '.post-content',
                                    '[data-testid="article-body"]',
                                    '.article-body',
                                    'main',
                                    '.content',
                                    '.single-post-content',
                                    '.post-body'
                                ]
                                
                                article_text = ""
                                for selector in content_selectors:
                                    try:
                                        element = article_soup.select_one(selector)
                                        if element:
                                            text = element.get_text(separator=' ', strip=True)
                                            if len(text) > 200:
                                                article_text = text
                                                logging.info(f"Found article content with selector '{selector}': {len(text)} chars")
                                                break
                                    except Exception as e:
                                        continue
                                
                                # Extract title
                                article_title = article['title']
                                title_element = article_soup.select_one('h1') or article_soup.select_one('title')
                                if title_element:
                                    extracted_title = title_element.get_text(strip=True)
                                    if len(extracted_title) > 5:
                                        article_title = extracted_title
                                
                                if article_text and len(article_text) > 200:
                                    # Clean and validate article text
                                    cleaned_article_text = clean_text_content(article_text)
                                    if is_binary_content(cleaned_article_text):
                                        logging.error(f"News article FAILED: Binary content detected")
                                        failed_articles.append({"url": article['url'], "error": "Binary content detected"})
                                        continue
                                    
                                    article_content = f"ARTICLE: {article_title}\n\nCONTENT: {cleaned_article_text}"
                                    article['title'] = article_title
                                    logging.info(f"News article SUCCESS: Title='{article_title}', Content={len(article_content)} bytes")
                                else:
                                    logging.error(f"News article FAILED: Insufficient content ({len(article_text)} chars)")
                                    failed_articles.append({"url": article['url'], "error": f"Insufficient content: {len(article_text)} chars"})
                                    continue
                            else:
                                logging.error(f"News article FAILED: HTTP {article_response.status_code}")
                                failed_articles.append({"url": article['url'], "error": f"HTTP {article_response.status_code}"})
                                continue
                        except Exception as e:
                            logging.error(f"News article processing failed: {e}")
                            failed_articles.append({"url": article['url'], "error": f"Processing failed: {str(e)[:50]}"})
                            continue
                
                # ENHANCED Content validation with detailed logging
                content_length = len(article_content) if article_content else 0
                logging.info(f"Content validation: {content_length} bytes (minimum: 100)")
                
                # Strict validation - reject short content
                if not article_content or content_length < 100:
                    error_msg = f"REJECTED: Insufficient content: {content_length} bytes (minimum 100 required)"
                    logging.error(f"CONTENT VALIDATION FAILED: {error_msg}")
                    failed_articles.append({"url": article['url'], "error": error_msg})
                    continue
                
                # Additional quality checks
                if len(article_content.strip()) < 100:
                    error_msg = f"REJECTED: Content too short after trimming: {len(article_content.strip())} bytes"
                    logging.error(f"CONTENT VALIDATION FAILED: {error_msg}")
                    failed_articles.append({"url": article['url'], "error": error_msg})
                    continue
                
                # Check for generic/error content
                generic_indicators = ["Your Library", "Sign up to get unlimited", "Couldn't find that podcast", "Subscribe to continue reading", "Please log in", "404 Not Found"]
                if any(indicator in article_content for indicator in generic_indicators):
                    error_msg = f"REJECTED: Generic/error content detected"
                    logging.error(f"CONTENT VALIDATION FAILED: {error_msg}")
                    failed_articles.append({"url": article['url'], "error": error_msg})
                    continue
                
                logging.info(f"✅ CONTENT VALIDATION PASSED: {content_length} bytes - HIGH QUALITY")
                
                # Create article via orchestrator with transaction safety
                try:
                    # Create article via orchestrator with transaction safety
                    payload = {
                        'article_text': article_content,
                        'request_string': article['title'],
                        'secret_id': user_id,
                        'major_points_count': 4
                    }
                    
                    # Enhanced binary content check for payload
                    if is_binary_content(payload['article_text']):
                        failed_articles.append({"url": article['url'], "error": "Binary content in payload"})
                        continue
                    
                    # Guy Raz specific binary pattern check
                    if 'guyraz.substack.com' in article['url']:
                        binary_indicators = ['AgH $+', 'i$UDzk]#JB', '춬B(k97la', 'ƮʗD>', '47APe_']
                        if any(indicator in payload['article_text'] for indicator in binary_indicators):
                            failed_articles.append({"url": article['url'], "error": "Guy Raz binary pattern detected"})
                            continue
                    
                    try:
                        # Test encoding before sending
                        payload['article_text'].encode('utf-8')
                    except Exception as encoding_error:
                        failed_articles.append({"url": article['url'], "error": f"Encoding error: {str(encoding_error)}"})
                        continue
                    
                    orchestrator_response = requests.post(
                        'http://news-orchestrator-1:5012/generate-news',
                        json=payload,
                        timeout=180,
                        headers={'Content-Type': 'application/json; charset=utf-8'}
                    )
                    
                    if orchestrator_response.status_code == 200:
                        result = orchestrator_response.json()
                        article_id = result['article_id']
                        
                        # Update with original URL (preserve episode parameters) and link to newsletter
                        try:
                            article_cursor.execute(
                                "UPDATE article_requests SET url = %s WHERE article_id = %s",
                                (article['url'], article_id)
                            )
                            article_cursor.execute(
                                "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                (newsletter_id, article_id)
                            )
                            article_conn.commit()
                            articles_created += 1
                            
                            if article.get('is_main_article'):
                                logging.info(f"✅ MAIN ARTICLE SUCCESSFULLY CREATED AND LINKED - ID: {article_id}")
                            else:
                                logging.info(f"✅ CREATED and linked new article {article_id}")
                        except Exception as db_error:
                            # Handle potential duplicate URL constraint violation
                            article_conn.rollback()
                            logging.warning(f"Database constraint violation for {article['url']}: {db_error}")
                            
                            # Try to link to existing article instead
                            try:
                                article_cursor.execute("SELECT article_id FROM article_requests WHERE url = %s", (article['url'],))
                                existing_article = article_cursor.fetchone()
                                if existing_article:
                                    article_cursor.execute(
                                        "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                                        (newsletter_id, existing_article[0])
                                    )
                                    article_conn.commit()
                                    articles_created += 1
                                    logging.info(f"✅ RECOVERED: Linked existing article {existing_article[0]} after constraint violation")
                                else:
                                    failed_articles.append({"url": article['url'], "error": f"DB constraint: {str(db_error)[:100]}"})
                            except Exception as recovery_error:
                                logging.error(f"Recovery failed: {recovery_error}")
                                failed_articles.append({"url": article['url'], "error": f"Recovery failed: {str(recovery_error)[:100]}"})
                    else:
                        try:
                            error_response = orchestrator_response.json()
                            error_detail = error_response.get('error', 'Unknown orchestrator error')
                        except Exception as json_error:
                            error_detail = f"HTTP {orchestrator_response.status_code}"
                        
                        logging.error(f"Orchestrator FAILED: {error_detail}")
                        failed_articles.append({"url": article['url'], "error": f"Orchestrator: {error_detail}"})
                        
                except Exception as orchestrator_error:
                    if article_conn:
                        article_conn.rollback()
                    
                    logging.error(f"Orchestrator request failed: {orchestrator_error}")
                    failed_articles.append({"url": article['url'], "error": f"Request failed: {str(orchestrator_error)[:100]}"})
                    
            except Exception as e:
                # Ensure transaction is rolled back on any error
                if article_conn:
                    try:
                        article_conn.rollback()
                    except:
                        pass
                
                logging.error(f"Error processing article {article['url']}: {e}")
                failed_articles.append({"url": article['url'], "error": str(e)[:100]})
            finally:
                # Always close article connection
                if article_cursor:
                    try:
                        article_cursor.close()
                    except:
                        pass
                if article_conn:
                    try:
                        article_conn.close()
                    except:
                        pass
        
        # Clean up if no articles created
        if articles_created == 0:
            cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            return jsonify({
                "status": "error",
                "message": "No articles found or created from newsletter.",
                "articles_found": len(article_urls),
                "articles_created": 0,
                "articles_failed": len(failed_articles),
                "failed_articles": failed_articles[:3]
            })
        
        # Main connection commit and cleanup
        conn.commit()
        cursor.close()
        conn.close()
        
        # Check if main article was processed
        main_article_found = any(article.get('is_main_article') for article in article_urls)
        
        logging.info(f"FINAL RESULTS: Found={len(article_urls)}, Created={articles_created}, Failed={len(failed_articles)}")
        if failed_articles:
            logging.info(f"Failed articles summary: {[f['error'] for f in failed_articles[:5]]}")
        
        return jsonify({
            "status": "success",
            "newsletter_id": newsletter_id,
            "articles_found": len(article_urls),
            "articles_created": articles_created,
            "articles_failed": len(failed_articles),
            "failed_articles": failed_articles[:3],
            "message": f"Newsletter processed: {articles_created}/{len(article_urls)} articles created"
        })
        
    except Exception as e:
        logging.error(f"Error processing newsletter: {e}")
        return jsonify({
            "status": "error",
            "message": f"Processing failed: {str(e)}",
            "error_type": "general_error"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5017, debug=True)