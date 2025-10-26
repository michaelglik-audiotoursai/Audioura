#!/usr/bin/env python3
"""
Debug script for newsletter crawling
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import re
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

def clean_url(url):
    """Remove query parameters for uniqueness check"""
    parsed = urlparse(url)
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return clean

def is_section_page(url):
    """Filter out section/index pages with high confidence"""
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    
    # Root section patterns
    section_patterns = [
        r'/news/local/?$', r'/news/national/?$', r'/news/sports/?$',
        r'/videos/?$', r'/watch/?$', r'/live/?$',
        r'/account/?$', r'/profile/?$', r'/settings/?$',
        r'/search/?$', r'\\?s=', r'/results/?$',
        r'/category/?$', r'/tag/?$', r'/tags/?$',
        r'/author/?$', r'/authors/?$',
        r'/archive/?$', r'/archives/?$',
        r'/feed/?$', r'/rss/?$',
        r'/sitemap/?$', r'/index/?$'
    ]
    
    for pattern in section_patterns:
        if re.search(pattern, url, re.IGNORECASE):
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
    if re.search(r'\\d{6,}', last_part):  # Contains article ID
        return True
    
    # Descriptive slug patterns (3+ words connected by hyphens)
    word_count = len(last_part.split('-'))
    if word_count >= 3 and len(last_part) >= 20:
        return True
    
    # Date-based URLs
    if re.search(r'\\d{4}/\\d{2}/\\d{2}', path):
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
        r'\\.jpg$', r'\\.png$', r'\\.pdf$', r'mailto:', r'tel:',
        r'/privacy', r'/terms', r'/contact', r'/advertise',
        r'/login', r'/register', r'/subscribe', r'/unsubscribe',
    ]
    
    for pattern in exclude_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            logging.info(f"Excluded URL {url} - matches pattern: {pattern}")
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
        r'/issue-', r'/edition-',  # Newsletter specific patterns
        # Date-based news URLs
        r'/\\d{4}/\\d{2}/', r'/\\d{4}-\\d{2}-\\d{2}/',
        # News-specific patterns
        r'/headlines/', r'/updates/', r'/alerts/'
    ]
    
    for pattern in article_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            logging.info(f"Article URL {url} - matches pattern: {pattern}")
            return True
    
    logging.info(f"Not article URL: {url}")
    return False

def debug_newsletter_crawl(url):
    """Debug the newsletter crawling process"""
    print(f"\\n=== DEBUGGING NEWSLETTER CRAWL FOR: {url} ===\\n")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        print(f"1. Fetching main page: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"   ERROR: Cannot access page")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract all links
        all_links = soup.find_all('a', href=True)
        print(f"2. Found {len(all_links)} total links")
        
        # Analyze links
        candidate_urls = []
        non_article_urls = []
        
        for i, link in enumerate(all_links):
            full_url = urljoin(url, link['href'])
            clean_full_url = clean_url(full_url)
            
            print(f"\\n   Link {i+1}: {full_url}")
            print(f"   Clean: {clean_full_url}")
            print(f"   Text: {link.get_text().strip()[:100]}")
            
            if is_article_url(full_url):
                candidate_urls.append(full_url)
                print(f"   -> CANDIDATE ARTICLE")
            else:
                non_article_urls.append(full_url)
                print(f"   -> NOT ARTICLE")
        
        print(f"\\n3. SUMMARY:")
        print(f"   Total links: {len(all_links)}")
        print(f"   Candidate articles: {len(candidate_urls)}")
        print(f"   Non-articles: {len(non_article_urls)}")
        
        print(f"\\n4. CANDIDATE ARTICLES:")
        for i, candidate in enumerate(candidate_urls):
            print(f"   {i+1}. {candidate}")
        
        # Check if the main URL itself is being treated as an article
        print(f"\\n5. MAIN URL ANALYSIS:")
        print(f"   URL: {url}")
        print(f"   Is article URL: {is_article_url(url)}")
        print(f"   Has article slug: {has_article_slug(url)}")
        print(f"   Is section page: {is_section_page(url)}")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    # Debug the API Security newsletter
    api_security_url = "https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/"
    debug_newsletter_crawl(api_security_url)