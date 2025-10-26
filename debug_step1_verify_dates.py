#!/usr/bin/env python3
"""
Step 1: Debug script to verify article dates for manual browser verification
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
                            return parsed_date
                        except:
                            continue
        
        # If no date found, use current date
        print(f"   Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"   Error extracting date from {url}: {e}")
        return datetime.now()

def test_api_security_newsletter():
    """Test the original API Security newsletter that had the issue"""
    url = "https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/"
    
    print(f"=== STEP 1: VERIFYING DATES FOR MANUAL BROWSER CHECK ===")
    print(f"Newsletter URL: {url}")
    print(f"Today's date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"7 days ago: {(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}")
    print()
    
    # Key external articles that should be checked manually
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
    
    print("ARTICLES TO VERIFY MANUALLY IN BROWSER:")
    print("="*60)
    
    for i, article_url in enumerate(test_articles, 1):
        print(f"{i}. {article_url}")
        try:
            response = requests.get(article_url, headers=headers, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                article_date = extract_article_date(soup, article_url)
                days_old = (datetime.now() - article_date).days
                
                print(f"   System detected date: {article_date.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Days old: {days_old}")
                print(f"   Would pass 7-day filter: {'YES' if days_old <= 7 else 'NO'}")
                print(f"   --> PLEASE VERIFY THIS DATE IN YOUR BROWSER")
            else:
                print(f"   HTTP {response.status_code} - Cannot access article")
        except Exception as e:
            print(f"   Error: {e}")
        print()
    
    print("MANUAL VERIFICATION INSTRUCTIONS:")
    print("="*60)
    print("1. Open each URL above in your browser")
    print("2. Look for the publication date on the webpage")
    print("3. Compare with the 'System detected date' shown above")
    print("4. Check if articles are actually within 7 days of today")
    print("5. Report any discrepancies between browser and system dates")

if __name__ == '__main__':
    test_api_security_newsletter()