#!/usr/bin/env python3
"""
Test Apple Podcasts URL extraction without audio generation
"""
import re
import requests
from bs4 import BeautifulSoup
from apple_podcasts_processor import process_apple_podcasts_url

def test_apple_extraction():
    """Test Apple Podcasts URL extraction from Guy Raz newsletter"""
    
    test_url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    print(f"Testing Apple Podcasts URL extraction from: {test_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        article_response = requests.get(test_url, headers=headers, timeout=10)
        
        if article_response.status_code != 200:
            print(f"Failed to fetch: HTTP {article_response.status_code}")
            return
        
        print(f"Successfully fetched content")
        
        # ENHANCEMENT: Extract Apple Podcasts URLs from newsletter content
        print(f"Checking for Apple Podcasts URLs in newsletter content")
        
        # Use raw response text to avoid BeautifulSoup encoding issues
        raw_html_content = article_response.text
        apple_podcasts_pattern = r'https://podcasts\.apple\.com/[^\s"\'>]+\?i=[^\s"\'>]+'
        embedded_apple_urls = re.findall(apple_podcasts_pattern, raw_html_content)
        
        print(f"Raw HTML content length: {len(raw_html_content)} chars")
        apple_mentions = raw_html_content.count('podcasts.apple.com')
        print(f"Apple Podcasts mentions in raw content: {apple_mentions}")
        print(f"Raw regex matches found: {len(embedded_apple_urls)}")
        
        if embedded_apple_urls:
            # Clean URLs by removing HTML encoding artifacts
            cleaned_urls = []
            for url in embedded_apple_urls:
                # Remove common HTML encoding artifacts
                cleaned_apple_url = url.split('&quot;')[0].split('\\')[0].split('"')[0]
                if '?i=' in cleaned_apple_url and cleaned_apple_url not in cleaned_urls:
                    cleaned_urls.append(cleaned_apple_url)
            
            unique_apple_urls = cleaned_urls
            print(f"Found {len(unique_apple_urls)} unique Apple Podcasts episode URLs in newsletter")
            
            for i, url in enumerate(unique_apple_urls[:8], 1):  # Show first 8
                print(f"  {i}. {url}")
            
            # Test Apple Podcasts processing for first URL (without audio generation)
            if unique_apple_urls:
                test_url = unique_apple_urls[0]
                print(f"\nTesting Apple Podcasts processor for: {test_url}")
                
                try:
                    apple_result = process_apple_podcasts_url(test_url)
                    
                    if apple_result.get('success'):
                        apple_content = apple_result['content']
                        apple_title = apple_result['title']
                        
                        print(f"✅ Apple Podcasts processing successful")
                        print(f"   Title: {apple_title}")
                        print(f"   Content length: {len(apple_content)} chars")
                        print(f"   Content preview: {apple_content[:200]}...")
                    else:
                        print(f"❌ Apple Podcasts processing failed: {apple_result.get('error')}")
                        
                except Exception as e:
                    print(f"❌ Error processing Apple Podcasts URL: {e}")
        else:
            print(f"No Apple Podcasts episode URLs found in newsletter content")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_apple_extraction()