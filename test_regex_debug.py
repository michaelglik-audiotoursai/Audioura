#!/usr/bin/env python3
"""
Debug script to test regex pattern matching on Guy Raz newsletter
"""
import re
import requests
from bs4 import BeautifulSoup

def test_regex_debug():
    """Test regex pattern matching"""
    
    test_url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    print(f"Testing regex pattern matching for: {test_url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch: HTTP {response.status_code}")
            return
        
        # Test different approaches
        print(f"\n=== Testing Different Approaches ===")
        
        # Approach 1: Direct regex on response.text
        print(f"\n1. Direct regex on response.text:")
        pattern1 = r'https://podcasts\.apple\.com/[^\s"\'>\]]+\?i=[^\s"\'>\]]+'
        matches1 = re.findall(pattern1, response.text)
        print(f"   Found {len(matches1)} matches")
        if matches1:
            for i, match in enumerate(matches1[:3], 1):
                print(f"   {i}. {match}")
        
        # Approach 2: BeautifulSoup then regex
        print(f"\n2. BeautifulSoup then regex on str(soup):")
        soup = BeautifulSoup(response.content, 'html.parser')
        html_content = str(soup)
        pattern2 = r'https://podcasts\.apple\.com/[^\s"\'>\]]+\?i=[^\s"\'>\]]+'
        matches2 = re.findall(pattern2, html_content)
        print(f"   Found {len(matches2)} matches")
        if matches2:
            for i, match in enumerate(matches2[:3], 1):
                print(f"   {i}. {match}")
        
        # Approach 3: More permissive pattern
        print(f"\n3. More permissive pattern:")
        pattern3 = r'https://podcasts\.apple\.com/[^\\s"\'>\]]*\?i=[^\\s"\'>\]]*'
        matches3 = re.findall(pattern3, html_content)
        print(f"   Found {len(matches3)} matches")
        if matches3:
            for i, match in enumerate(matches3[:3], 1):
                print(f"   {i}. {match}")
        
        # Approach 4: Search for any Apple Podcasts URLs first
        print(f"\n4. Any Apple Podcasts URLs:")
        pattern4 = r'https://podcasts\.apple\.com/[^\\s"\'>\]]*'
        matches4 = re.findall(pattern4, html_content)
        print(f"   Found {len(matches4)} Apple Podcasts URLs")
        
        # Filter for episode URLs
        episode_urls = [url for url in matches4 if '?i=' in url]
        print(f"   Episode URLs (with ?i=): {len(episode_urls)}")
        if episode_urls:
            for i, url in enumerate(episode_urls[:5], 1):
                print(f"   {i}. {url}")
        
        # Approach 5: Check encoding issues
        print(f"\n5. Encoding check:")
        print(f"   Response encoding: {response.encoding}")
        print(f"   Content type: {response.headers.get('content-type', 'unknown')}")
        
        # Check if there are any Apple Podcasts mentions at all
        apple_mentions = html_content.count('podcasts.apple.com')
        print(f"   'podcasts.apple.com' mentions: {apple_mentions}")
        
        if apple_mentions > 0:
            # Find first mention context
            index = html_content.find('podcasts.apple.com')
            if index >= 0:
                context = html_content[max(0, index-50):index+200]
                print(f"   First mention context: {repr(context)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_regex_debug()