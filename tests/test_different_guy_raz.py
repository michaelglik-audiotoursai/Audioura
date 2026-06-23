#!/usr/bin/env python3
"""
Test different Guy Raz newsletter URL to check if corruption is article-specific
"""
import requests
from bs4 import BeautifulSoup

def test_different_guy_raz_url():
    """Test a different Guy Raz newsletter URL"""
    
    # Different Guy Raz newsletter URL
    url = "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines"
    
    print(f"Testing different Guy Raz URL: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',  # NO BROTLI
        'Connection': 'keep-alive'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
        print(f"Content-Encoding: {response.headers.get('content-encoding', 'None')}")
        print(f"Content Length: {len(response.content)} bytes")
        print(f"Text Length: {len(response.text)} characters")
        print()
        
        # Check if we get readable HTML
        if response.text.startswith('<'):
            print("SUCCESS: READABLE HTML received")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try to extract content
            element = soup.select_one('.available-content .body.markup')
            if element:
                text = element.get_text(separator=' ', strip=True)
                print(f"SUCCESS: Content extracted: {len(text)} characters")
                print(f"First 300 chars: {text[:300]}")
            else:
                print("FAILED: No content element found")
                print(f"Title: {soup.title.string if soup.title else 'No title'}")
        else:
            print("FAILED: BINARY/CORRUPTED response")
            print(f"First 200 bytes: {repr(response.content[:200])}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_different_guy_raz_url()