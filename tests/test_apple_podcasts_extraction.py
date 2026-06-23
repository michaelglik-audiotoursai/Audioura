#!/usr/bin/env python3
"""
Test script to verify Apple Podcasts URL extraction from HTML content
"""
import re
import requests
from bs4 import BeautifulSoup

def test_apple_podcasts_extraction():
    """Test Apple Podcasts URL extraction from Guy Raz newsletter"""
    
    # Test URL
    test_url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    print(f"Testing Apple Podcasts URL extraction from: {test_url}")
    
    try:
        # Fetch the content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch content: HTTP {response.status_code}")
            return
        
        print(f"Successfully fetched content: {len(response.text)} characters")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        html_content = str(soup)
        
        # Test the regex pattern
        apple_podcasts_pattern = r'https://podcasts\.apple\.com/[^\s"\'>\]]+\?i=[^\s"\'>\]]+'
        embedded_apple_urls = re.findall(apple_podcasts_pattern, html_content)
        
        print(f"\nApple Podcasts URLs found: {len(embedded_apple_urls)}")
        
        if embedded_apple_urls:
            for i, url in enumerate(embedded_apple_urls, 1):
                print(f"  {i}. {url}")
        else:
            print("No Apple Podcasts episode URLs found")
            
            # Let's search for any Apple Podcasts URLs (even without ?i=)
            general_apple_pattern = r'https://podcasts\.apple\.com/[^\s"\'>\]]+'
            general_apple_urls = re.findall(general_apple_pattern, html_content)
            
            print(f"\nGeneral Apple Podcasts URLs found: {len(general_apple_urls)}")
            for i, url in enumerate(general_apple_urls, 1):
                print(f"  {i}. {url}")
            
            # Let's also search for any mention of "podcasts.apple.com"
            if "podcasts.apple.com" in html_content:
                print("\nFound 'podcasts.apple.com' in content - checking context...")
                lines = html_content.split('\n')
                for i, line in enumerate(lines):
                    if "podcasts.apple.com" in line:
                        print(f"  Line {i}: {line.strip()[:200]}...")
                        break
            else:
                print("\nNo 'podcasts.apple.com' found in content")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_apple_podcasts_extraction()