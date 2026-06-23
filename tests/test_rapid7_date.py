#!/usr/bin/env python3
"""
Test the improved date extraction on the Rapid7 article
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

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
                    print(f"Found updated date: {date_text}")
                    # Try to parse various date formats
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
                print(f"Found updated date in text: {date_text}")
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
                    print(f"Found publication date: {date_text}")
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%B %d, %Y', '%d %B %Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_text[:19], fmt)
                        except:
                            continue
        
        # If no date found, use current date
        print(f"Could not determine date for {url}, using current date")
        return datetime.now()
        
    except Exception as e:
        print(f"Error extracting date from {url}: {e}")
        return datetime.now()

def test_rapid7_article():
    """Test the Rapid7 article specifically"""
    url = "https://www.rapid7.com/blog/post/securden-unified-pam-multiple-critical-vulnerabilities-fixed/"
    
    print(f"Testing improved date extraction for: {url}")
    print(f"Today: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"7 days ago: {(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')}")
    print()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Show what the user sees in browser
            print("VISIBLE TEXT FROM PAGE (first 500 chars):")
            visible_text = soup.get_text()[:500]
            print(visible_text)
            print()
            
            # Test date extraction
            article_date = extract_article_date(soup, url)
            days_old = (datetime.now() - article_date).days
            
            print(f"RESULT:")
            print(f"Extracted date: {article_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Days old: {days_old}")
            print(f"Would pass 7-day filter: {'YES' if days_old <= 7 else 'NO'}")
            
        else:
            print(f"HTTP {response.status_code} - Cannot access article")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    test_rapid7_article()