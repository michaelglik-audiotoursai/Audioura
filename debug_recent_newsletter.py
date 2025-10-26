#!/usr/bin/env python3
"""
Debug a recent newsletter to see if it finds more articles
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import re
from datetime import datetime, timedelta

def clean_url(url):
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
        
        print(f"   Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"   Error extracting date from {url}: {e}")
        return datetime.now()

def test_recent_newsletter():
    """Test a very recent newsletter to see if it finds more articles"""
    # Use the most recent newsletter (issue-280) which should have recent external articles
    newsletter_url = "https://apisecurity.io/issue-280-solar-device-ato-attacks-smart-tvs-dumb-apis-password-reset-api-bugs-2025-developer-survey/"
    
    print(f"=== TESTING RECENT NEWSLETTER FOR EXTERNAL ARTICLES ===")
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
        
        print("\n2. LOOKING FOR EXTERNAL ARTICLES...")
        external_articles = []
        
        for link in all_links:
            full_url = urljoin(newsletter_url, link['href'])
            link_text = link.get_text().strip()[:100]
            
            # Look for external domains (not apisecurity.io)
            parsed = urlparse(full_url)
            if parsed.netloc and 'apisecurity.io' not in parsed.netloc.lower():
                # Skip social media
                if any(social in parsed.netloc.lower() for social in ['facebook', 'twitter', 'linkedin']):
                    continue
                
                external_articles.append({
                    'url': full_url,
                    'domain': parsed.netloc,
                    'link_text': link_text
                })
        
        print(f"   Found {len(external_articles)} external articles")
        
        print("\n3. TESTING DATE EXTRACTION ON EXTERNAL ARTICLES...")
        recent_articles = []
        
        for i, article in enumerate(external_articles[:5], 1):  # Test first 5
            print(f"\n   Article {i}: {article['domain']}")
            print(f"   URL: {article['url']}")
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
                        recent_articles.append(article)
                        print(f"   ✅ WOULD BE PROCESSED (within 7 days)")
                    else:
                        print(f"   ❌ TOO OLD (filtered out)")
                else:
                    print(f"   ❌ HTTP {article_response.status_code}")
            except Exception as e:
                print(f"   ❌ ERROR: {e}")
        
        print(f"\n4. SUMMARY:")
        print(f"   Total external articles found: {len(external_articles)}")
        print(f"   Recent articles (≤7 days): {len(recent_articles)}")
        
        if len(recent_articles) == 0:
            print(f"\n⚠️  NO RECENT EXTERNAL ARTICLES FOUND")
            print(f"   This explains why only 1 article (newsletter page) was processed")
            print(f"   The 7-day filtering is working correctly!")
        else:
            print(f"\n✅ RECENT EXTERNAL ARTICLES AVAILABLE")
            print(f"   System should find {len(recent_articles)} + 1 (newsletter) = {len(recent_articles) + 1} articles")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    test_recent_newsletter()