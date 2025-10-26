#!/usr/bin/env python3
"""
Debug script for date filtering in newsletter processing
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

def extract_article_date(soup, url):
    """Extract article publication date from webpage"""
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
            element = soup.select_one(selector)
            if element:
                date_text = element.get('datetime') or element.get('content') or element.get_text()
                if date_text:
                    print(f"   Found date element: {selector} = '{date_text}'")
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y']:
                        try:
                            parsed_date = datetime.strptime(date_text[:19], fmt)
                            print(f"   Successfully parsed date: {parsed_date}")
                            return parsed_date
                        except:
                            continue
        
        # If no date found, use current date
        print(f"   Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"   Error extracting date from {url}: {e}")
        return datetime.now()

def test_article_dates():
    """Test date extraction for key articles from API Security newsletter"""
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
    
    print("=== TESTING DATE EXTRACTION FOR KEY ARTICLES ===\\n")
    
    for i, url in enumerate(test_articles, 1):
        print(f"{i}. Testing: {url}")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                article_date = extract_article_date(soup, url)
                days_old = (datetime.now() - article_date).days
                print(f"   Article date: {article_date}")
                print(f"   Days old: {days_old}")
                print(f"   Would be filtered (>7 days): {days_old > 7}")
            else:
                print(f"   HTTP {response.status_code} - Cannot access article")
        except Exception as e:
            print(f"   Error: {e}")
        print()

if __name__ == '__main__':
    test_article_dates()