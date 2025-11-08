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
        
        logging.info(f"Processing newsletter: {newsletter_url}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check daily limit
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
        
        # Create newsletter entry
        cursor.execute(
            "INSERT INTO newsletters (url, type) VALUES (%s, %s) RETURNING id",
            (clean_newsletter_url, 'Newsletter')
        )
        newsletter_id = cursor.fetchone()[0]
        conn.commit()
        
        # Fetch and parse newsletter
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(newsletter_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return jsonify({
                "status": "error",
                "message": f"Failed to access newsletter: HTTP {response.status_code}",
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
            
            # Try Substack-specific selectors first
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
                        # Get text content, clean it up
                        text = element.get_text(separator=' ', strip=True)
                        if len(text) > 200:  # Substantial content
                            main_content = text
                            logging.info(f"Found Substack content with selector '{selector}': {len(text)} chars")
                            break
                except Exception as e:
                    logging.debug(f"Selector '{selector}' failed: {e}")
                    continue
            
            # Fallback to generic selectors
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
                            # Get text content, clean it up
                            text = element.get_text(separator=' ', strip=True)
                            if len(text) > 200:  # Substantial content
                                main_content = text
                                logging.info(f"Found generic content with selector '{selector}': {len(text)} chars")
                                break
                    except Exception as e:
                        logging.debug(f"Generic selector '{selector}' failed: {e}")
                        continue
            
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
                logging.info(f"Added MAIN newsletter article: '{clean_title}' ({len(main_content)} chars)")
                logging.info(f"Content preview: {main_content[:200]}...")
            else:
                logging.warning(f"Main newsletter content insufficient: {len(main_content) if main_content else 0} chars")
                
        except Exception as e:
            logging.error(f"Error extracting main newsletter content: {e}")
        
        # 2. LINKED ARTICLES - Extract URLs from all clickable HTML elements
        all_urls = extract_all_clickable_urls(soup, newsletter_url)
        logging.info(f"Found {len(all_urls)} total clickable URLs")
        
        # Filter for article URLs - prioritize podcast URLs
        for url in all_urls:
            if ('podcasts.apple.com' in url and '?i=' in url) or 'open.spotify.com/episode' in url:
                article_urls.append({
                    'url': url,
                    'clean_url': clean_url(url),
                    'title': 'Podcast Episode',
                    'date': datetime.now(),
                    'is_main_article': False
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
                        # Link existing article to newsletter (many-to-many relationship)
                        article_cursor.execute(
                            "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (newsletter_id, existing_article[0])
                        )
                        article_conn.commit()
                        articles_created += 1
                        logging.info(f"✅ LINKED existing article to newsletter: {article['title']} (ID: {existing_article[0]})")
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
                            logging.info(f"Removed likely title duplication from content start")
                    
                    article_content = f"NEWSLETTER: {article['title']}\n\nCONTENT: {content}"
                    logging.info(f"Using pre-extracted main newsletter content: {len(article_content)} bytes")
                    logging.info(f"Final content preview: {article_content[:300]}...")
                    
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
                        logging.info(f"Spotify content preview: {article_content[:200]}...")
                    else:
                        error_msg = spotify_result.get('error', 'Unknown Spotify error')
                        logging.error(f"Spotify FAILED: {error_msg}")
                        failed_articles.append({"url": article['url'], "error": f"Spotify: {error_msg}"})
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
                generic_indicators = ["Your Library", "Sign up to get unlimited", "Couldn't find that podcast"]
                if any(indicator in article_content for indicator in generic_indicators):
                    error_msg = f"REJECTED: Generic/error content detected"
                    logging.error(f"CONTENT VALIDATION FAILED: {error_msg}")
                    failed_articles.append({"url": article['url'], "error": error_msg})
                    continue
                
                logging.info(f"✅ CONTENT VALIDATION PASSED: {content_length} bytes - HIGH QUALITY")
                
                # Create article via orchestrator with transaction safety
                try:
                    logging.info(f"Sending to orchestrator: Title='{article['title']}', Content={len(article_content)} bytes")
                    
                    orchestrator_response = requests.post(
                        'http://news-orchestrator-1:5012/generate-news',
                        json={
                            'article_text': article_content,
                            'request_string': article['title'],
                            'secret_id': user_id,
                            'major_points_count': 4
                        },
                        timeout=180,
                        headers={'Content-Type': 'application/json; charset=utf-8'}
                    )
                    
                    logging.info(f"Orchestrator response: Status={orchestrator_response.status_code}")
                    
                    if orchestrator_response.status_code == 200:
                        result = orchestrator_response.json()
                        article_id = result['article_id']
                        logging.info(f"Orchestrator SUCCESS: Created article_id={article_id}")
                        
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
                        except:
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
                failed_articles.append({"url": article['url'], "error": str(e)[:100]})
                logging.error(f"Error processing article {article['url']}: {e}")
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