#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup

def test_content_selectors():
    """Test what content selectors are available in the Guy Raz newsletter"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print(f"Testing content selectors for: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Test all the selectors used in newsletter processor
        selectors = [
            '.available-content .body.markup',
            '.post-content .body.markup', 
            'article .body.markup',
            '.single-post .body.markup',
            'article',
            '.post-content',
            '.newsletter-content',
            '.entry-content',
            'main',
            '[role="main"]'
        ]
        
        print("\n=== Testing Selectors ===")
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                element = elements[0]
                text = element.get_text(separator=' ', strip=True)
                print(f"[FOUND] {selector}: Found {len(elements)} elements, first has {len(text)} chars")
                
                # Test for binary contamination
                printable_chars = sum(1 for c in text if c.isprintable() or c.isspace())
                total_chars = len(text)
                printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
                
                if printable_ratio < 0.95:
                    print(f"  [ERROR] Binary contamination: {printable_ratio:.3f} printable ratio")
                    print(f"  Sample (repr): {repr(text[:100])}")
                else:
                    print(f"  [OK] Clean text: {printable_ratio:.3f} printable ratio")
                    print(f"  Sample: {text[:100]}...")
                print()
            else:
                print(f"[NONE] {selector}: No elements found")
        
        # Also check title
        print("=== Title ===")
        title_element = soup.select_one('title')
        if title_element:
            title_text = title_element.get_text(strip=True)
            print(f"Title: {repr(title_text)}")
            
            # Check for binary in title
            printable_chars = sum(1 for c in title_text if c.isprintable() or c.isspace())
            total_chars = len(title_text)
            printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
            
            if printable_ratio < 0.95:
                print(f"[ERROR] Binary contamination in title: {printable_ratio:.3f}")
            else:
                print(f"[OK] Clean title: {printable_ratio:.3f}")
        
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")

if __name__ == "__main__":
    test_content_selectors()