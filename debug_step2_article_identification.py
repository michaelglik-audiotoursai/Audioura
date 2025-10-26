#!/usr/bin/env python3
"""
Step 2: Test article identification for API Security newsletter issue-280
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
                    print(f"   Found updated date: {date_text}")
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_text[:19], fmt)
                        except:
                            continue
        
        # Look for "Last updated" text patterns in the page content
        page_text = soup.get_text()
        updated_patterns = [
            r'Last updated on ([A-Za-z]+ \d{1,2}, \d{4})',
            r'Updated: ([A-Za-z]+ \d{1,2}, \d{4})',
            r'Modified: ([A-Za-z]+ \d{1,2}, \d{4})'
        ]
        
        for pattern in updated_patterns:
            match = re.search(pattern, page_text)
            if match:
                date_text = match.group(1)
                print(f"   Found updated date in text: {date_text}")
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
                    print(f"   Found publication date: {date_text}")
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_text[:19], fmt)
                        except:
                            continue
        
        # If no date found, use current date
        print(f"   Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"   Error extracting date from {url}: {e}")
        return datetime.now()

def is_article_url(url):
    """Check if URL looks like an article"""
    # Simple article detection for this test
    exclude_patterns = [
        r'\.jpg$', r'\.png$', r'\.pdf$', r'mailto:', r'tel:',
        r'/privacy', r'/terms', r'/contact', r'/advertise',
        r'/login', r'/register', r'/subscribe', r'/unsubscribe'
    ]
    
    for pattern in exclude_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    
    # Check for article patterns
    article_patterns = [
        r'/news/', r'/blog/', r'/post/', r'/article/',
        r'/issue-', r'/report/', r'/analysis/',
        r'-\d{4}-', r'/\d{4}/', r'[a-z]+-[a-z]+-[a-z]+'
    ]
    
    for pattern in article_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    # Check for descriptive slug (3+ words)
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    if path_parts:
        last_part = path_parts[-1]
        word_count = len(last_part.split('-'))
        if word_count >= 3 and len(last_part) >= 20:
            return True
    
    return False

def test_newsletter_article_identification():
    """Test article identification for the API Security newsletter"""
    newsletter_url = "https://apisecurity.io/issue-280-solar-device-ato-attacks-smart-tvs-dumb-apis-password-reset-api-bugs-2025-developer-survey/"
    
    print("=== STEP 2: ARTICLE IDENTIFICATION TEST ===")
    print(f"Newsletter: {newsletter_url}")
    print(f"Today: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"7-day cutoff: {(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}")
    print()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        print("1. FETCHING NEWSLETTER PAGE...")
        response = requests.get(newsletter_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"   ERROR: HTTP {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        all_links = soup.find_all('a', href=True)
        print(f"   Found {len(all_links)} total links")
        
        print("\n2. IDENTIFYING CANDIDATE ARTICLES...")
        candidate_articles = []
        
        for i, link in enumerate(all_links):
            full_url = urljoin(newsletter_url, link['href'])
            clean_full_url = clean_url(full_url)
            link_text = link.get_text().strip()[:100]
            
            if is_article_url(full_url):
                candidate_articles.append({
                    'url': full_url,
                    'clean_url': clean_full_url,
                    'link_text': link_text
                })
        
        print(f"   Found {len(candidate_articles)} candidate articles")
        
        print("\n3. TESTING DATE EXTRACTION AND 7-DAY FILTERING...")
        valid_articles = []
        filtered_articles = []
        
        for i, article in enumerate(candidate_articles, 1):
            print(f"\n   Article {i}: {article['url']}")
            print(f"   Link text: {article['link_text']}")
            
            try:
                article_response = requests.get(article['url'], headers=headers, timeout=5)
                if article_response.status_code == 200:
                    article_soup = BeautifulSoup(article_response.content, 'html.parser')
                    article_date = extract_article_date(article_soup, article['url'])
                    days_old = (datetime.now() - article_date).days
                    
                    print(f"   Date: {article_date.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   Days old: {days_old}")
                    
                    if days_old <= 7:
                        valid_articles.append({
                            'url': article['url'],
                            'title': article_soup.find('title').get_text() if article_soup.find('title') else 'No Title',
                            'date': article_date,
                            'days_old': days_old
                        })
                        print(f"   ✅ PASSES 7-day filter")
                    else:
                        filtered_articles.append({
                            'url': article['url'],
                            'days_old': days_old
                        })
                        print(f"   ❌ FILTERED OUT (too old)")
                else:
                    print(f"   ❌ HTTP {article_response.status_code}")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
        
        print(f"\n4. FINAL RESULTS:")
        print(f"   Total links found: {len(all_links)}")
        print(f"   Candidate articles: {len(candidate_articles)}")
        print(f"   Articles passing 7-day filter: {len(valid_articles)}")
        print(f"   Articles filtered out: {len(filtered_articles)}")
        
        if valid_articles:
            print(f"\n5. ARTICLES THAT WOULD BE PROCESSED:")
            for i, article in enumerate(valid_articles, 1):
                print(f"   {i}. {article['title'][:80]}...")
                print(f"      URL: {article['url']}")
                print(f"      Date: {article['date'].strftime('%Y-%m-%d')} ({article['days_old']} days old)")
                print()
        else:
            print(f"\n5. NO ARTICLES WOULD BE PROCESSED (all filtered out or none found)")
        
        if filtered_articles:
            print(f"6. ARTICLES FILTERED OUT (>7 days old):")
            for i, article in enumerate(filtered_articles[:5], 1):  # Show first 5
                print(f"   {i}. {article['url']} ({article['days_old']} days old)")
        
        print(f"\n=== MANUAL VERIFICATION NEEDED ===")
        print(f"Please check the newsletter page in your browser:")
        print(f"{newsletter_url}")
        print(f"Verify that the {len(valid_articles)} articles identified are correct.")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    test_newsletter_article_identification()