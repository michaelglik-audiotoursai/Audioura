#!/usr/bin/env python3
"""
Debug script to test the crawl_newsletter_links function directly
"""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def test_crawl_debug():
    """Test the crawling logic to see where Apple Podcasts URLs are missed"""
    
    test_url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    print(f"Testing crawl logic for: {test_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch: HTTP {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Step 1: Extract all <a href=""> links (current method)
        all_links = soup.find_all('a', href=True)
        print(f"\nStep 1: Found {len(all_links)} <a href=''> links")
        
        apple_links_from_href = []
        for link in all_links:
            href = link['href']
            full_url = urljoin(test_url, href)
            if 'podcasts.apple.com' in full_url and '?i=' in full_url:
                apple_links_from_href.append(full_url)
        
        print(f"Apple Podcasts URLs from <a href=''>: {len(apple_links_from_href)}")
        for url in apple_links_from_href[:3]:  # Show first 3
            print(f"  {url}")
        
        # Step 2: Extract from HTML content (new method)
        html_content = str(soup)
        apple_podcasts_pattern = r'https://podcasts\.apple\.com/[^\s"\'>\]]+\?i=[^\s"\'>\]]+'
        embedded_apple_urls = re.findall(apple_podcasts_pattern, html_content)
        
        print(f"\nStep 2: Apple Podcasts URLs from HTML content: {len(embedded_apple_urls)}")
        
        # Remove duplicates and show unique URLs
        unique_urls = list(set(embedded_apple_urls))
        print(f"Unique Apple Podcasts URLs: {len(unique_urls)}")
        
        for i, url in enumerate(unique_urls[:8], 1):  # Show first 8
            print(f"  {i}. {url}")
        
        # Step 3: Test the fake link creation logic
        print(f"\nStep 3: Testing fake link creation...")
        
        fake_links_created = 0
        for url in unique_urls:
            # Create fake link elements for these URLs to process them normally
            fake_link = soup.new_tag('a', href=url)
            fake_link.string = "Apple Podcasts Episode"
            all_links.append(fake_link)
            fake_links_created += 1
        
        print(f"Created {fake_links_created} fake links")
        print(f"Total links after enhancement: {len(all_links)}")
        
        # Step 4: Test article URL detection
        print(f"\nStep 4: Testing article URL detection...")
        
        def is_article_url_test(url):
            """Simplified version of is_article_url for testing"""
            # ALWAYS accept Apple Podcasts episode URLs with specific episode IDs
            if 'podcasts.apple.com' in url.lower() and '?i=' in url.lower():
                return True
            return False
        
        article_urls = []
        for link in all_links:
            full_url = urljoin(test_url, link['href'])
            if is_article_url_test(full_url):
                article_urls.append(full_url)
        
        print(f"URLs detected as articles: {len(article_urls)}")
        for i, url in enumerate(article_urls[:5], 1):  # Show first 5
            print(f"  {i}. {url}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_crawl_debug()