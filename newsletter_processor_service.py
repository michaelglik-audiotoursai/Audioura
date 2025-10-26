#!/usr/bin/env python3
"""
Newsletter Processor Service - Processes newsletter URLs and creates audio editions
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

def clean_url(url):
    """Remove query parameters for uniqueness check"""
    parsed = urlparse(url)
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return clean

def detect_newsletter_type(content, url):
    """AI-detect newsletter type from content and URL"""
    content_lower = content.lower()
    url_lower = url.lower()
    
    # Keywords for each category
    categories = {
        'News and Politics': ['politics', 'election', 'government', 'policy', 'congress', 'senate', 'president', 'news', 'breaking'],
        'Business and Investment': ['business', 'finance', 'investment', 'stock', 'market', 'economy', 'startup', 'venture', 'trading'],
        'Technology': ['tech', 'software', 'ai', 'artificial intelligence', 'programming', 'developer', 'startup', 'innovation'],
        'Lifestyle and Entertainment': ['lifestyle', 'entertainment', 'celebrity', 'fashion', 'travel', 'food', 'health', 'fitness'],
        'Education and Learning': ['education', 'learning', 'course', 'tutorial', 'academic', 'research', 'study', 'university']
    }
    
    scores = {}
    for category, keywords in categories.items():
        score = sum(1 for keyword in keywords if keyword in content_lower or keyword in url_lower)
        scores[category] = score
    
    # Return category with highest score, default to 'Others'
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return 'Others'

def extract_article_date(soup, url):
    """Extract article publication date from webpage, prioritizing updated dates"""
    try:
        # First, look for updated/modified dates (higher priority)
        updated_selectors = [
            'meta[property="article:modified_time"]',
            'meta[name="article:modified_time"]',
            '[class*="updated"]', '[class*="modified"]',
            'time[class*="updated"]', 'time[class*="modified"]'
        ]
        
        for selector in updated_selectors:
            element = soup.select_one(selector)
            if element:
                date_text = element.get('datetime') or element.get('content') or element.get_text()
                if date_text:
                    logging.info(f"Found updated date: {date_text}")
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_text[:19], fmt)
                        except:
                            continue
        
        # Look for "Last updated" text patterns in the page content
        page_text = soup.get_text()
        import re
        updated_patterns = [
            r'Last updated on ([A-Za-z]+ \d{1,2}, \d{4})',
            r'Updated: ([A-Za-z]+ \d{1,2}, \d{4})',
            r'Modified: ([A-Za-z]+ \d{1,2}, \d{4})'
        ]
        
        for pattern in updated_patterns:
            match = re.search(pattern, page_text)
            if match:
                date_text = match.group(1)
                logging.info(f"Found updated date in text: {date_text}")
                for fmt in ['%b %d, %Y', '%B %d, %Y']:
                    try:
                        return datetime.strptime(date_text, fmt)
                    except:
                        continue
        
        # Fallback to original publication date selectors
        date_selectors = [
            'time[datetime]',
            '.date', '.publish-date', '.article-date',
            '[class*="date"]', '[class*="time"]',
            'meta[property="article:published_time"]',
            'meta[name="date"]'
        ]
        
        for selector in date_selectors:
            element = soup.select_one(selector)
            if element:
                date_text = element.get('datetime') or element.get('content') or element.get_text()
                if date_text:
                    logging.info(f"Found publication date: {date_text}")
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_text[:19], fmt)
                        except:
                            continue
        
        # If no date found, use current date
        logging.warning(f"Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        logging.error(f"Error extracting date from {url}: {e}")
        return datetime.now()

def is_section_page(url):
    """Filter out section/index pages with high confidence"""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    
    # Root section patterns
    section_patterns = [
        r'/news/local/?$', r'/news/national/?$', r'/news/sports/?$',
        r'/videos/?$', r'/watch/?$', r'/live/?$',
        r'/account/?$', r'/profile/?$', r'/settings/?$',
        r'/search/?$', r'\?s=', r'/results/?$',
        r'/category/?$', r'/tag/?$', r'/tags/?$',
        r'/author/?$', r'/authors/?$',
        r'/archive/?$', r'/archives/?$',
        r'/feed/?$', r'/rss/?$',
        r'/sitemap/?$', r'/index/?$'
    ]
    
    for pattern in section_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    # Team/topic index pages (ending with team/topic name only)
    path_parts = [p for p in path.split('/') if p]
    if len(path_parts) >= 3:
        last_part = path_parts[-1]
        # If last part is a single word (team/topic) without descriptive slug
        if (len(last_part.split('-')) <= 2 and 
            not re.search(r'\d{4,}', last_part) and  # No article IDs
            len(last_part) < 20):  # Short names, not descriptive slugs
            return True
    
    return False

def has_article_slug(url):
    """Check if URL has descriptive article slug"""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    path_parts = [p for p in path.split('/') if p]
    
    if not path_parts:
        return False
    
    last_part = path_parts[-1]
    
    # Strong article indicators
    if re.search(r'\d{6,}', last_part):  # Contains article ID
        return True
    
    # Descriptive slug patterns (3+ words connected by hyphens)
    word_count = len(last_part.split('-'))
    if word_count >= 3 and len(last_part) >= 20:
        return True
    
    # Date-based URLs
    if re.search(r'\d{4}/\d{2}/\d{2}', path):
        return True
    
    return False

def is_article_url(url):
    """Two-stage article detection: filter sections, then check for article patterns"""
    logging.info(f"Checking if article URL: {url}")
    
    # Stage 1: Filter out obvious section pages
    if is_section_page(url):
        logging.info(f"Excluded URL {url} - section/index page")
        return False
    
    # Enhanced exclusions for non-news content
    exclude_patterns = [
        r'\.jpg$', r'\.png$', r'\.pdf$', r'mailto:', r'tel:',
        r'/privacy', r'/terms', r'/contact', r'/advertise',
        r'/login', r'/register', r'/subscribe', r'/unsubscribe',
        # Social media share links (exclude completely)
        r'facebook\.com/sharer', r'twitter\.com/share', r'linkedin\.com/shareArticle',
        r't\.co/', r'bit\.ly/', r'tinyurl\.com/',
        # Hotel/restaurant/business exclusions
        r'/culinary/', r'/dining/', r'/restaurant/', r'/menu/',
        r'/rooms?/', r'/suites?/', r'/amenities/', r'/spa/',
        r'/weddings?/', r'/events?/', r'/meetings?/', r'/conference/',
        r'/booking/', r'/reservation/', r'/gallery/', r'/photos/',
        # Social media and non-news
        r'/social-media/', r'/facebook/', r'/twitter/', r'/instagram/',
        r'/foundation/', r'/charity/', r'/donate/', r'/volunteer/',
        # Weather/closings (not news articles)
        r'/weather/', r'/closings?/', r'/delays?/', r'/storm/'
    ]
    
    for pattern in exclude_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            logging.info(f"Excluded URL {url} - matches pattern: {pattern}")
            return False
    
    # Check domain - exclude non-news domains
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Exclude hotel/restaurant/business domains
    business_domains = [
        'hotel.com', 'restaurant.com', 'booking.com', 'expedia.com',
        'marriott.com', 'hilton.com', 'hyatt.com', 'ihg.com',
        'cancer.org', 'redcross.org', 'charity.org'
    ]
    
    for business_domain in business_domains:
        if business_domain in domain:
            logging.info(f"Excluded URL {url} - business domain: {business_domain}")
            return False
    
    # Stage 2: Check for article slug patterns
    if has_article_slug(url):
        logging.info(f"Article URL {url} - has descriptive slug")
        return True
    
    # Enhanced article patterns for news sites
    article_patterns = [
        r'/news/', r'/local/', r'/breaking/', r'/politics/',
        r'/sports/', r'/business/', r'/technology/', r'/health/',
        r'/article/', r'/story/', r'/post/', r'/blog/',
        r'/press-release/', r'/report/', r'/analysis/',
        # Date-based news URLs
        r'/\d{4}/\d{2}/', r'/\d{4}-\d{2}-\d{2}/',
        # News-specific patterns
        r'/headlines/', r'/updates/', r'/alerts/'
    ]
    
    for pattern in article_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            logging.info(f"Article URL {url} - matches pattern: {pattern}")
            return True
    
    logging.info(f"Not article URL: {url}")
    return False

def refine_articles_with_openai(candidate_urls):
    """Use OpenAI to refine article detection for ambiguous URLs"""
    if not candidate_urls or len(candidate_urls) == 0:
        return []
    
    try:
        # Prepare URLs for OpenAI analysis
        url_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(candidate_urls)])
        
        prompt = f"""Analyze these URLs and identify which ones are likely to be individual news articles (not section pages, category pages, or navigation pages).

URLs to analyze:
{url_list}

Return only the numbers of URLs that are likely individual articles, separated by commas. For example: 1,3,5

Look for:
- Descriptive slugs with multiple words
- Article IDs or dates
- Specific story titles in the URL

Avoid:
- Section roots (/news/, /sports/)
- Category pages
- Navigation pages
- Search results"""
        
        # Simple OpenAI API call (requires OPENAI_API_KEY environment variable)
        openai_response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {os.getenv("OPENAI_API_KEY")}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 100,
                'temperature': 0.1
            },
            timeout=10
        )
        
        if openai_response.status_code == 200:
            result = openai_response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            # Parse the response (expecting comma-separated numbers)
            try:
                selected_indices = [int(x.strip()) - 1 for x in content.split(',') if x.strip().isdigit()]
                refined_urls = [candidate_urls[i] for i in selected_indices if 0 <= i < len(candidate_urls)]
                logging.info(f"OpenAI refined {len(candidate_urls)} URLs to {len(refined_urls)} articles")
                return refined_urls
            except:
                logging.warning(f"Could not parse OpenAI response: {content}")
                return candidate_urls[:5]  # Fallback: take first 5
        else:
            logging.warning(f"OpenAI API error: {openai_response.status_code}")
            return candidate_urls[:5]  # Fallback
            
    except Exception as e:
        logging.error(f"OpenAI refinement error: {e}")
        return candidate_urls[:5]  # Fallback

def calculate_content_similarity(text1, text2):
    """Calculate similarity between two text contents (simple word-based)"""
    if not text1 or not text2:
        return 0.0
    
    # Simple word-based similarity
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    return intersection / union if union > 0 else 0.0

def crawl_newsletter_links(url, max_depth=2, max_articles=10):
    """Crawl newsletter URL and find article links"""
    logging.info(f"Starting crawl_newsletter_links for {url}")
    visited = set()
    article_urls = []
    processed_clean_urls = set()  # Track unique articles
    article_contents = []  # Track content for similarity detection
    
    pages_to_crawl = [(url, 0)]  # (url, depth) pairs
    
    while pages_to_crawl and len(processed_clean_urls) < max_articles:
        page_url, depth = pages_to_crawl.pop(0)  # Breadth-first (FIFO)
        
        if depth > max_depth or len(article_urls) >= max_articles or page_url in visited:
            continue
            
        visited.add(page_url)
        logging.info(f"Crawling {page_url} at depth {depth}")
        
        try:
            logging.info(f"Requesting {page_url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            response = requests.get(page_url, headers=headers, timeout=10)
            logging.info(f"Response status: {response.status_code}")
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code} - Website blocked access"
                logging.info(f"Skipping {page_url} - {error_msg}")
                if depth == 0:  # Main page failed
                    return {'error': error_msg}
                return None
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract all links
            all_links = soup.find_all('a', href=True)
            logging.info(f"Found {len(all_links)} total links on {page_url}")
            
            # Collect candidate URLs for processing
            candidate_urls = []
            non_article_urls = []
            
            for link in all_links:
                full_url = urljoin(page_url, link['href'])
                clean_full_url = clean_url(full_url)
                
                if clean_full_url in visited or len(article_urls) >= max_articles:
                    continue
                
                if is_article_url(full_url):
                    candidate_urls.append(full_url)
                elif depth < max_depth:
                    non_article_urls.append(full_url)
            
            logging.info(f"Found {len(candidate_urls)} candidate articles for refinement")
            
            # Use OpenAI to refine article selection if we have candidates
            if candidate_urls and len(candidate_urls) > 5:
                refined_urls = refine_articles_with_openai(candidate_urls[:20])  # Limit to 20 for API
                candidate_urls = refined_urls
                logging.info(f"OpenAI refined to {len(candidate_urls)} articles")
            
            # Process the refined article candidates
            for full_url in candidate_urls:
                if len(article_urls) >= max_articles:
                    break
                    
                clean_full_url = clean_url(full_url)
                if clean_full_url in visited or clean_full_url in processed_clean_urls:
                    continue
                
                try:
                    article_response = requests.get(full_url, headers=headers, timeout=5)
                    if article_response.status_code == 200:
                        article_soup = BeautifulSoup(article_response.content, 'html.parser')
                        article_date = extract_article_date(article_soup, full_url)
                        
                        # Apply 7-day date filtering for news articles
                        days_old = (datetime.now() - article_date).days
                        logging.info(f"Article {full_url} is {days_old} days old")
                        
                        if days_old <= 7:
                            # Check for content similarity with existing articles
                            article_text = article_soup.get_text()[:2000]  # First 2000 chars for comparison
                            is_duplicate = False
                            
                            for existing_content in article_contents:
                                similarity = calculate_content_similarity(article_text, existing_content)
                                if similarity > 0.8:  # 80% similarity threshold
                                    logging.info(f"Skipped article: {full_url} (80%+ similar to existing article)")
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                article_urls.append({
                                    'url': full_url,
                                    'clean_url': clean_full_url,
                                    'title': article_soup.find('title').get_text() if article_soup.find('title') else 'Article',
                                    'date': article_date
                                })
                                processed_clean_urls.add(clean_full_url)  # Track unique articles
                                article_contents.append(article_text)  # Track content for similarity
                                logging.info(f"Added article: {full_url} (published {days_old} days ago)")
                        else:
                            logging.info(f"Skipped article: {full_url} (too old: {days_old} days)")
                except Exception as e:
                    logging.error(f"Error checking article {full_url}: {e}")
                
                time.sleep(0.5)  # Rate limiting
            
            # Add non-article URLs to crawl queue for deeper search
            for url in non_article_urls:
                pages_to_crawl.append((url, depth + 1))
                
        except Exception as e:
            error_msg = f"Connection failed: {str(e)[:100]}"
            logging.error(f"Error crawling {page_url}: {e}")
            if depth == 0:  # Main page failed
                return {'error': error_msg}
    
    # Always return a list, never None
    return article_urls if article_urls else []

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "newsletter_processor"})

@app.route('/newsletters', methods=['GET'])
def get_newsletters():
    """Get all newsletters from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT n.id, n.url, n.type, n.created_at 
            FROM newsletters n
            JOIN newsletters_article_link nal ON n.id = nal.newsletters_id
            JOIN article_requests ar ON nal.article_requests_id = ar.article_id
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE ar.status = 'finished'
            ORDER BY n.created_at DESC
        """)
        
        newsletters = []
        for row in cursor.fetchall():
            # Extract domain name from URL for display
            url = row[1]
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain_name = parsed.netloc.replace('www.', '')
                display_name = f"{domain_name} ({row[2] or 'Newsletter'})"
            except:
                display_name = url
            
            newsletters.append({
                'id': row[0],
                'url': row[1],
                'name': display_name,
                'created_at': row[3].isoformat() if row[3] else None,
                'type': row[2] or 'Others'
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "newsletters": newsletters
        })
        
    except Exception as e:
        logging.error(f"Error getting newsletters: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_newsletter_articles', methods=['POST'])
def get_newsletter_articles():
    """Get already processed articles from newsletter"""
    try:
        data = request.get_json()
        newsletter_url = data.get('newsletter_url')
        
        logging.info(f"Getting processed articles for newsletter: {newsletter_url}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Enhanced URL matching with fuzzy search
        clean_newsletter_url = clean_url(newsletter_url)
        
        # Try multiple matching strategies
        newsletter_record = None
        
        # Get the most recent newsletter with articles for this URL
        clean_newsletter_url = clean_url(newsletter_url)
        
        # Find the most recent newsletter that has articles
        cursor.execute("""
            SELECT n.id 
            FROM newsletters n
            JOIN newsletters_article_link nal ON n.id = nal.newsletters_id
            WHERE n.url = %s OR n.url = %s
            GROUP BY n.id
            ORDER BY n.created_at DESC
            LIMIT 1
        """, (clean_newsletter_url, newsletter_url))
        newsletter_record = cursor.fetchone()
        
        if not newsletter_record:
            logging.info(f"Newsletter not found for URL: {newsletter_url} (clean: {clean_newsletter_url})")
            return jsonify({"error": "Newsletter not found"}), 404
        
        newsletter_id = newsletter_record[0]
        
        # Get only articles that have audio generated (finished status + audio exists)
        cursor.execute("""
            SELECT ar.article_id, ar.request_string, ar.url, ar.created_at, ar.status, ar.article_type
            FROM article_requests ar
            JOIN newsletters_article_link nal ON ar.article_id = nal.article_requests_id
            JOIN news_audios na ON ar.article_id = na.article_id
            WHERE nal.newsletters_id = %s AND ar.status = 'finished'
            ORDER BY ar.created_at DESC
        """, (newsletter_id,))
        
        # Fetch results first
        rows = cursor.fetchall()
        
        # Clean up articles without audio (remove orphaned links)
        cursor.execute("""
            DELETE FROM newsletters_article_link 
            WHERE newsletters_id = %s 
            AND article_requests_id NOT IN (
                SELECT ar.article_id 
                FROM article_requests ar 
                JOIN news_audios na ON ar.article_id = na.article_id 
                WHERE ar.status = 'finished'
            )
        """, (newsletter_id,))
        
        # If newsletter has no articles with audio, delete the newsletter
        if len(rows) == 0:
            cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
            logging.info(f"Deleted empty newsletter {newsletter_id}")
        
        conn.commit()
        
        articles = []
        for row in rows:
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
        logging.error(f"Error getting newsletter articles: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/add_selected_articles', methods=['POST'])
def add_selected_articles():
    """Add selected articles to user's Listen page (saved_news)"""
    try:
        data = request.get_json()
        selected_articles = data.get('selected_articles', [])
        user_id = data.get('user_id', 'default_user')
        
        logging.info(f"Adding {len(selected_articles)} selected articles to Listen page")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        articles_added = 0
        
        for article in selected_articles:
            try:
                article_id = article['article_id']
                
                # Check if article has audio generated (status = 'finished')
                cursor.execute(
                    "SELECT status FROM article_requests WHERE article_id = %s",
                    (article_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    logging.warning(f"Article {article_id} not found")
                    continue
                
                if result[0] != 'finished':
                    logging.warning(f"Article {article_id} not finished processing (status: {result[0]})")
                    continue
                
                # Check if audio exists in news_audios
                cursor.execute(
                    "SELECT article_name FROM news_audios WHERE article_id = %s",
                    (article_id,)
                )
                audio_result = cursor.fetchone()
                
                if audio_result:
                    articles_added += 1
                    logging.info(f"Article {article_id} ({article['title']}) is ready for Listen page")
                else:
                    logging.warning(f"Article {article_id} has no audio generated yet")
                
            except Exception as e:
                logging.error(f"Error checking article {article.get('article_id', 'Unknown')}: {e}")
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "articles_added": articles_added,
            "message": f"{articles_added} articles are available in your Listen page"
        })
        
    except Exception as e:
        logging.error(f"Error adding selected articles: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_articles_for_listen', methods=['POST'])
def get_articles_for_listen():
    """Get article data needed for Listen page"""
    try:
        data = request.get_json()
        article_ids = data.get('article_ids', [])
        
        logging.info(f"Getting Listen page data for {len(article_ids)} articles")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        articles = []
        
        for article_id in article_ids:
            try:
                # Get article info
                cursor.execute(
                    "SELECT request_string, status FROM article_requests WHERE article_id = %s",
                    (article_id,)
                )
                article_result = cursor.fetchone()
                
                if not article_result:
                    logging.warning(f"Article {article_id} not found")
                    continue
                
                title, status = article_result
                
                if status != 'finished':
                    logging.warning(f"Article {article_id} not finished (status: {status})")
                    continue
                
                # Get audio data
                cursor.execute(
                    "SELECT news_article FROM news_audios WHERE article_id = %s",
                    (article_id,)
                )
                audio_result = cursor.fetchone()
                
                if not audio_result:
                    logging.warning(f"No audio found for article {article_id}")
                    continue
                
                # Create temporary file path (mobile app will download the audio)
                import tempfile
                import os
                temp_dir = tempfile.gettempdir()
                article_path = os.path.join(temp_dir, f"article_{article_id}")
                
                # Save audio data to temporary location
                os.makedirs(article_path, exist_ok=True)
                
                # Write the ZIP file
                zip_path = os.path.join(article_path, "index.html")
                with open(zip_path, 'wb') as f:
                    f.write(audio_result[0])
                
                articles.append({
                    'article_id': article_id,
                    'title': title,
                    'path': article_path,
                    'status': status
                })
                
                logging.info(f"Prepared article {article_id}: {title}")
                
            except Exception as e:
                logging.error(f"Error preparing article {article_id}: {e}")
                continue
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "articles": articles
        })
        
    except Exception as e:
        logging.error(f"Error getting articles for listen: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/newsletters_v2', methods=['GET'])
def get_newsletters_v2():
    """Get all newsletters with dates and article counts - NEW VERSION"""
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
                from urllib.parse import urlparse
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
    """Get articles by newsletter ID - NEW VERSION"""
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

@app.route('/cleanup_empty_newsletters', methods=['POST'])
def cleanup_empty_newsletters():
    """Remove newsletters that have no articles associated with them"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Find newsletters with no articles
        cursor.execute("""
            SELECT n.id, n.url, n.created_at 
            FROM newsletters n
            LEFT JOIN newsletters_article_link nal ON n.id = nal.newsletters_id
            WHERE nal.newsletters_id IS NULL
        """)
        
        empty_newsletters = cursor.fetchall()
        
        if empty_newsletters:
            # Delete empty newsletters
            newsletter_ids = [row[0] for row in empty_newsletters]
            cursor.execute(
                "DELETE FROM newsletters WHERE id = ANY(%s)",
                (newsletter_ids,)
            )
            
            logging.info(f"Deleted {len(empty_newsletters)} empty newsletters")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({
                "status": "success",
                "deleted_count": len(empty_newsletters),
                "message": f"Deleted {len(empty_newsletters)} newsletters with no articles"
            })
        else:
            cursor.close()
            conn.close()
            
            return jsonify({
                "status": "success",
                "deleted_count": 0,
                "message": "No empty newsletters found"
            })
            
    except Exception as e:
        logging.error(f"Error cleaning up empty newsletters: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/process_newsletter', methods=['POST'])
def process_newsletter():
    try:
        data = request.get_json()
        newsletter_url = data.get('newsletter_url')
        user_id = data.get('user_id')
        max_articles = data.get('max_articles', 10)
        max_depth = data.get('max_depth', 2)
        
        logging.info(f"Processing newsletter: {newsletter_url}")
        
        # Clean URL for database storage
        clean_newsletter_url = clean_url(newsletter_url)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if newsletter was processed today
        today = datetime.now().date()
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
        
        # Fetch newsletter content to detect type
        response = requests.get(newsletter_url, timeout=10)
        content = response.text
        newsletter_type = detect_newsletter_type(content, newsletter_url)
        
        # Insert new newsletter edition (allow multiple entries for different days)
        cursor.execute(
            "INSERT INTO newsletters (url, type) VALUES (%s, %s) RETURNING id",
            (clean_newsletter_url, newsletter_type)
        )
        newsletter_id = cursor.fetchone()[0]
        logging.info(f"Created new newsletter edition {newsletter_id} with type {newsletter_type}")
        conn.commit()  # Commit immediately to ensure newsletter is saved
        
        # Always crawl for article links first
        crawl_result = crawl_newsletter_links(newsletter_url, max_depth, max_articles)
        logging.info(f"Crawl result type: {type(crawl_result)}, content: {crawl_result}")
        
        # If crawling failed or found few articles, also process the newsletter page itself
        if crawl_result is None:
            crawl_result = []
        
        # Always add the newsletter page itself as an article (contains valuable content)
        if not isinstance(crawl_result, dict):
            logging.info(f"Adding newsletter page as primary article")
            newsletter_article = {
                'url': newsletter_url,
                'clean_url': clean_url(newsletter_url),
                'title': 'Newsletter Summary',
                'date': datetime.now()
            }
            crawl_result.insert(0, newsletter_article)  # Add at beginning
            logging.info(f"Added newsletter page as article, total articles: {len(crawl_result)}")
        elif isinstance(crawl_result, dict) and 'error' in crawl_result:
            logging.info(f"Crawl failed with error, processing newsletter page as single article")
            # Add the newsletter page itself as an article when crawling fails
            newsletter_article = {
                'url': newsletter_url,
                'clean_url': clean_url(newsletter_url),
                'title': 'Newsletter Summary',
                'date': datetime.now()
            }
            crawl_result = [newsletter_article]  # Replace error dict with article list
            logging.info(f"Added newsletter page as single article due to crawl failure")
        
        if isinstance(crawl_result, dict) and 'error' in crawl_result:
            # Crawling failed
            error_response = {
                "status": "error",
                "message": f"Failed to access newsletter: {crawl_result['error']}",
                "articles_found": 0,
                "articles_created": 0
            }
            logging.info(f"Returning error response: {error_response}")
            return jsonify(error_response)
        
        # Handle None result from crawler
        if crawl_result is None:
            crawl_result = []
            logging.warning("Crawler returned None, using empty list")
        
        article_links = crawl_result
        logging.info(f"Found {len(article_links)} articles")
        
        articles_created = 0
        failed_articles = []
        
        logging.info(f"Starting to process {len(article_links)} articles from crawler")
        for i, article in enumerate(article_links, 1):
            logging.info(f"Processing article {i}/{len(article_links)}: {article['url']}")
            try:
                # Check if article URL already exists (clean URL before '?' parameters)
                cursor.execute("SELECT article_id FROM article_requests WHERE url = %s", (article['clean_url'],))
                existing_article = cursor.fetchone()
                
                if existing_article:
                    # Link existing article to newsletter
                    cursor.execute(
                        "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (newsletter_id, existing_article[0])
                    )
                    logging.info(f"Linked existing article {existing_article[0]} to newsletter (URL: {article['clean_url']})")
                    logging.info(f"Article already exists in database: {article['title']}")
                else:
                    logging.info(f"Processing new article: {article['url']} (clean: {article['clean_url']})")
                    logging.info(f"Article title: {article['title']}")
                    logging.info(f"Article date: {article['date']}")
                    logging.info(f"Days old: {(datetime.now() - article['date']).days}")
                    
                    # Fetch article content
                    try:
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                        article_response = requests.get(article['url'], headers=headers, timeout=10)
                        if article_response.status_code != 200:
                            logging.error(f"Failed to fetch article content: HTTP {article_response.status_code}")
                            continue
                        
                        # Extract clean text from HTML
                        logging.info(f"Extracting text from HTML content ({len(article_response.text)} chars)")
                        article_soup = BeautifulSoup(article_response.content, 'html.parser')
                        
                        # Remove script and style elements
                        for script in article_soup(["script", "style", "nav", "header", "footer", "aside"]):
                            script.decompose()
                        
                        # Try to find main content area
                        main_content = None
                        for selector in ['article', 'main', '.content', '.post', '.entry', '[role="main"]']:
                            main_content = article_soup.select_one(selector)
                            if main_content:
                                break
                        
                        # If no main content found, use body
                        if not main_content:
                            main_content = article_soup.find('body') or article_soup
                        
                        # Extract clean text
                        article_content = main_content.get_text(separator=' ', strip=True)
                        logging.info(f"Text extraction result: First 200 chars: {article_content[:200]}...")
                        
                        # Clean up extra whitespace
                        import re
                        article_content = re.sub(r'\s+', ' ', article_content).strip()
                        
                        logging.info(f"Extracted clean text: {len(article_content)} characters")
                        
                        # Truncate to 50K characters for cost optimization
                        original_length = len(article_content)
                        if original_length > 50000:
                            article_content = article_content[:50000] + "\n\nLimit of 50,000 characters per article is reached. Please contact support to upgrade your plan to remove/increase your limit."
                            logging.info(f"Article truncated from {original_length} to {len(article_content)} characters")
                        else:
                            logging.info(f"Final clean article content: {len(article_content)} characters")
                    except Exception as e:
                        logging.error(f"Error fetching article content for {article['url']}: {e}")
                        failed_articles.append({"url": article['url'], "error": f"Content fetch error: {str(e)[:100]}"})
                        continue
                    # Call news orchestrator with rate limiting
                    logging.info(f"Creating article for: {article['url']}")
                    
                    # No delay needed with Polly TTS (higher rate limits)
                    # Using Polly TTS for faster processing
                    
                    orchestrator_response = requests.post(
                        'http://news-orchestrator-1:5012/generate-news',
                        json={
                            'article_text': article_content,
                            'request_string': article['title'],
                            'secret_id': user_id,
                            'major_points_count': 4
                        },
                        timeout=180  # Increased timeout for TTS processing
                    )
                    
                    if orchestrator_response.status_code == 200:
                        result = orchestrator_response.json()
                        article_id = result['article_id']
                        logging.info(f"Orchestrator created article: {article_id}")
                        
                        # Update article_requests with URL immediately
                        cursor.execute(
                            "UPDATE article_requests SET url = %s WHERE article_id = %s",
                            (article['clean_url'], article_id)
                        )
                        conn.commit()  # Commit immediately to ensure URL is saved
                        logging.info(f"Updated article_requests with URL: {article['clean_url']}")
                        
                        # Link article to newsletter (avoid duplicates)
                        cursor.execute(
                            "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (newsletter_id, article_id)
                        )
                        logging.info(f"Linked article {article_id} to newsletter {newsletter_id}")
                        
                        articles_created += 1
                        logging.info(f"Successfully created article {article_id} for {article['url']}")
                    else:
                        error_msg = f"Failed to create article: {orchestrator_response.status_code}"
                        failed_articles.append({"url": article['url'], "error": error_msg})
                        logging.error(f"Orchestrator failed for {article['url']}: {orchestrator_response.status_code} - {orchestrator_response.text}")
                
            except Exception as e:
                error_msg = f"Processing error: {str(e)[:100]}"
                failed_articles.append({"url": article['url'], "error": error_msg})
                logging.error(f"Error processing article {article['url']}: {e}")
                logging.error(f"Article details - Title: {article.get('title', 'N/A')}, Date: {article.get('date', 'N/A')}, Clean URL: {article.get('clean_url', 'N/A')}")
                continue
        
        # Clean up newsletter if no articles were created
        if articles_created == 0:
            logging.info(f"No articles created for newsletter {newsletter_id}, deleting newsletter entry")
            # Delete the newsletter and any links
            cursor.execute("DELETE FROM newsletters_article_link WHERE newsletters_id = %s", (newsletter_id,))
            cursor.execute("DELETE FROM newsletters WHERE id = %s", (newsletter_id,))
            conn.commit()
            logging.info(f"Deleted empty newsletter {newsletter_id} and its links")
            
            cursor.close()
            conn.close()
            
            # Determine the main error reason
            error_message = "No articles found or created from newsletter."
            if failed_articles:
                # Check for common error patterns
                first_error = str(failed_articles[0]).lower()
                if "403" in first_error or "blocked access" in first_error:
                    error_message = "Website blocked access (HTTP 403). This website doesn't allow automated access."
                elif "connection" in first_error or "timeout" in first_error:
                    error_message = "Connection failed. Website may be down or blocking requests."
                elif "404" in first_error:
                    error_message = "Website not found (HTTP 404). Please check the URL."
                else:
                    error_message = f"Processing failed: {failed_articles[0]}"
            
            return jsonify({
                "status": "error",
                "message": error_message,
                "articles_found": len(article_links),
                "articles_created": 0,
                "articles_failed": len(failed_articles),
                "failed_articles": failed_articles[:3]
            })
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Create summary message
        summary_msg = f"Newsletter processed: {articles_created}/{len(article_links)} articles created"
        if failed_articles:
            summary_msg += f", {len(failed_articles)} failed"
        
        return jsonify({
            "status": "success",
            "newsletter_id": newsletter_id,
            "articles_found": len(article_links),
            "articles_created": articles_created,
            "articles_failed": len(failed_articles),
            "failed_articles": failed_articles[:3],  # Show first 3 failures
            "message": summary_msg
        })
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error processing newsletter: {error_msg}")
        
        # Handle specific error types with user-friendly messages
        if "duplicate key value violates unique constraint" in error_msg:
            return jsonify({
                "status": "error",
                "message": "Newsletter was already processed recently. Please wait a few minutes before trying again.",
                "error_type": "duplicate_processing"
            }), 400
        elif "403" in error_msg or "blocked access" in error_msg:
            return jsonify({
                "status": "error", 
                "message": "Website blocked access (HTTP 403). This website doesn't allow automated access.",
                "error_type": "access_blocked"
            }), 400
        else:
            return jsonify({
                "status": "error",
                "message": f"Processing failed: {error_msg}",
                "error_type": "general_error"
            }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5017, debug=True)