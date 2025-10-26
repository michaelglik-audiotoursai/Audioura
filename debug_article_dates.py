#!/usr/bin/env python3
"""
Debug script to check article dates from API Security newsletter
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta
import re

def extract_article_date(soup, url):
    """Extract article publication date from webpage"""
    print(f"\n=== EXTRACTING DATE FROM: {url} ===")
    
    try:
        # Common date selectors
        date_selectors = [
            'time[datetime]',
            '.date', '.publish-date', '.article-date',
            '[class*="date"]', '[class*="time"]',
            'meta[property="article:published_time"]',
            'meta[name="date"]'
        ]
        
        for selector in date_selectors:
            elements = soup.select(selector)
            print(f"Selector '{selector}': found {len(elements)} elements")
            
            for element in elements:
                date_text = element.get('datetime') or element.get('content') or element.get_text()
                if date_text:
                    print(f"  Found date text: '{date_text}'")
                    
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y']:
                        try:
                            parsed_date = datetime.strptime(date_text[:19], fmt)
                            days_old = (datetime.now() - parsed_date).days
                            print(f"  Parsed successfully: {parsed_date} ({days_old} days old)")
                            return parsed_date
                        except Exception as e:
                            print(f"  Failed to parse with format {fmt}: {e}")
                            continue
        
        # Look for date patterns in text content
        print("\nLooking for date patterns in page text...")
        page_text = soup.get_text()
        
        # Common date patterns
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # 2025-01-15
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}',  # January 15, 2025
            r'\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}',  # 15 January 2025
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, page_text, re.IGNORECASE)
            if matches:
                print(f"Found date pattern matches: {matches[:3]}")  # Show first 3
        
        # If no date found, use current date
        print("No valid date found, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"Error extracting date: {e}")
        return datetime.now()

def debug_article_dates():
    """Debug article dates from API Security newsletter"""
    
    # Test URLs from our debug output
    test_articles = [
        "https://aseem-shrey.medium.com/manipulating-indias-stock-market-the-gst-portal-data-leak-b5437c817071",
        "https://bobdahacker.com/blog/hacked-biggest-chinese-robot-company",
        "https://cybersecuritynews.com/hashicorp-vault-vulnerability/",
        "https://www.rapid7.com/blog/post/securden-unified-pam-multiple-critical-vulnerabilities-fixed/",
        "https://cybersecuritynews.com/esphome-web-server-authentication-bypass"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    seven_days_ago = datetime.now() - timedelta(days=7)
    print(f"7-day cutoff date: {seven_days_ago}")
    print(f"Current date: {datetime.now()}")
    
    for url in test_articles:
        try:
            print(f"\n{'='*80}")
            print(f"TESTING: {url}")
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"HTTP {response.status_code} - skipping")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            article_date = extract_article_date(soup, url)
            
            days_old = (datetime.now() - article_date).days
            within_7_days = article_date >= seven_days_ago
            
            print(f"\nRESULT:")
            print(f"  Article date: {article_date}")
            print(f"  Days old: {days_old}")
            print(f"  Within 7 days: {within_7_days}")
            
            if not within_7_days:
                print(f"  ❌ WOULD BE FILTERED OUT (too old)")
            else:
                print(f"  ✅ WOULD BE INCLUDED")
                
        except Exception as e:
            print(f"Error processing {url}: {e}")

if __name__ == "__main__":
    debug_article_dates()