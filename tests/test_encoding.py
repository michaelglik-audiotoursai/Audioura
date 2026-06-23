#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup

def test_guy_raz_encoding():
    """Test BeautifulSoup text extraction on Guy Raz Substack page"""
    
    url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        print("Fetching Guy Raz Substack page...")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        print(f"Response encoding: {response.encoding}")
        print(f"Content type: {response.headers.get('content-type', 'unknown')}")
        
        if response.status_code != 200:
            print(f"Failed to fetch page: HTTP {response.status_code}")
            return
        
        # Test different BeautifulSoup approaches
        print("\n=== Testing BeautifulSoup parsing ===")
        
        # Method 1: Direct content parsing (current approach)
        print("Method 1: Direct content parsing")
        try:
            soup1 = BeautifulSoup(response.content, 'html.parser')
            main_content1 = soup1.find('body') or soup1
            article_content1 = main_content1.get_text(separator=' ', strip=True)
            print(f"Success: {len(article_content1)} chars")
            print(f"First 200 chars: {article_content1[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
        
        # Method 2: Decode first, then parse
        print("\nMethod 2: Decode first, then parse")
        try:
            if response.encoding:
                html_content = response.content.decode(response.encoding, errors='replace')
            else:
                html_content = response.content.decode('utf-8', errors='replace')
            
            soup2 = BeautifulSoup(html_content, 'html.parser')
            main_content2 = soup2.find('body') or soup2
            article_content2 = main_content2.get_text(separator=' ', strip=True)
            print(f"Success: {len(article_content2)} chars")
            print(f"First 200 chars: {article_content2[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
        
        # Method 3: Force UTF-8
        print("\nMethod 3: Force UTF-8")
        try:
            html_content = response.content.decode('utf-8', errors='replace')
            soup3 = BeautifulSoup(html_content, 'html.parser')
            main_content3 = soup3.find('body') or soup3
            article_content3 = main_content3.get_text(separator=' ', strip=True)
            print(f"Success: {len(article_content3)} chars")
            print(f"First 200 chars: {article_content3[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
            
        # Method 4: Use response.text instead of content
        print("\nMethod 4: Use response.text")
        try:
            soup4 = BeautifulSoup(response.text, 'html.parser')
            main_content4 = soup4.find('body') or soup4
            article_content4 = main_content4.get_text(separator=' ', strip=True)
            print(f"Success: {len(article_content4)} chars")
            print(f"First 200 chars: {article_content4[:200]}")
        except Exception as e:
            print(f"Failed: {e}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_guy_raz_encoding()