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
    """Remove query parameters for uniqueness check"""
    try:
        if isinstance(url, bytes):
            url = url.decode('utf-8', errors='replace')
        elif not isinstance(url, str):
            url = str(url)
        
        parsed = urlparse(url)
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
        
        # ENHANCED: Extract URLs from all clickable HTML elements
        all_urls = extract_all_clickable_urls(soup, newsletter_url)
        logging.info(f"Found {len(all_urls)} total clickable URLs")
        
        # Filter for article URLs - prioritize podcast URLs
        article_urls = []
        for url in all_urls:
            if ('podcasts.apple.com' in url and '?i=' in url) or 'open.spotify.com/episode' in url:
                article_urls.append({
                    'url': url,
                    'clean_url': clean_url(url),
                    'title': 'Podcast Episode',
                    'date': datetime.now()
                })
        
        # Limit articles
        article_urls = article_urls[:max_articles]
        logging.info(f"Processing {len(article_urls)} articles")
        
        articles_created = 0
        failed_articles = []
        
        for i, article in enumerate(article_urls, 1):
            try:
                logging.info(f"Processing article {i}/{len(article_urls)}: {article['url']}")
                
                # UNIVERSAL DUPLICATE CHECK
                cursor.execute("SELECT article_id FROM article_requests WHERE url = %s", (article['clean_url'],))
                existing_article = cursor.fetchone()
                
                if existing_article:
                    # Link existing article to newsletter
                    cursor.execute(
                        "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (newsletter_id, existing_article[0])
                    )
                    conn.commit()
                    articles_created += 1
                    logging.info(f"Linked existing article to newsletter: {article['title']}")
                    continue
                
                # Process new article
                article_content = ""
                
                if 'podcasts.apple.com' in article['url']:
                    apple_result = process_apple_podcasts_url(article['url'])
                    if apple_result.get('success'):
                        article_content = apple_result['content']
                        article['title'] = apple_result['title']
                    else:
                        failed_articles.append({"url": article['url'], "error": "Apple Podcasts processing failed"})
                        continue
                        
                elif 'open.spotify.com/episode' in article['url']:
                    spotify_result = process_spotify_url(article['url'])
                    if spotify_result.get('success'):
                        article_content = spotify_result['content']
                        article['title'] = spotify_result['title']
                    else:
                        failed_articles.append({"url": article['url'], "error": "Spotify processing failed"})
                        continue
                
                if not article_content:
                    failed_articles.append({"url": article['url'], "error": "No content extracted"})
                    continue
                
                # Create article via orchestrator
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
                
                if orchestrator_response.status_code == 200:
                    result = orchestrator_response.json()
                    article_id = result['article_id']
                    
                    # Update with URL and link to newsletter
                    cursor.execute(
                        "UPDATE article_requests SET url = %s WHERE article_id = %s",
                        (article['clean_url'], article_id)
                    )
                    cursor.execute(
                        "INSERT INTO newsletters_article_link (newsletters_id, article_requests_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (newsletter_id, article_id)
                    )
                    conn.commit()
                    articles_created += 1
                    logging.info(f"Successfully created article {article_id}")
                else:
                    failed_articles.append({"url": article['url'], "error": f"Orchestrator failed: {orchestrator_response.status_code}"})
                    
            except Exception as e:
                failed_articles.append({"url": article['url'], "error": str(e)[:100]})
                logging.error(f"Error processing article {article['url']}: {e}")
        
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
        
        conn.commit()
        cursor.close()
        conn.close()
        
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