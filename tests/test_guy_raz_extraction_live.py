#!/usr/bin/env python3
"""
Test live Guy Raz content extraction to see where corruption happens
"""
import requests
from bs4 import BeautifulSoup

def test_guy_raz_extraction():
    """Test actual Guy Raz content extraction step by step"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom"
    
    print("=== LIVE GUY RAZ EXTRACTION TEST ===")
    print(f"URL: {url}")
    print()
    
    # Step 1: HTTP Request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        print("Step 1: Making HTTP request...")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
        print(f"Content-Length: {len(response.content)} bytes")
        print(f"Encoding: {response.encoding}")
        print()
        
        # Step 2: BeautifulSoup parsing
        print("Step 2: Parsing with BeautifulSoup...")
        soup = BeautifulSoup(response.content, 'html.parser')
        print("Parsing successful")
        print()
        
        # Step 3: Try Substack selectors
        print("Step 3: Testing Substack selectors...")
        substack_selectors = [
            '.available-content .body.markup',
            '.post-content .body.markup', 
            'article .body.markup',
            '.single-post .body.markup'
        ]
        
        for selector in substack_selectors:
            print(f"Testing selector: {selector}")
            element = soup.select_one(selector)
            if element:
                print(f"  ✅ Found element")
                
                # Remove problematic elements
                for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                    tag.decompose()
                
                # Extract text
                text = element.get_text(separator=' ', strip=True)
                print(f"  Text length: {len(text)} chars")
                
                # Check first 200 chars for corruption
                preview = text[:200]
                print(f"  Preview: {preview}")
                
                # Check for non-ASCII chars in preview
                non_ascii_in_preview = [(i, c, ord(c)) for i, c in enumerate(preview) if ord(c) > 127]
                if non_ascii_in_preview:
                    print(f"  Non-ASCII chars in preview: {len(non_ascii_in_preview)}")
                    for i, (pos, char, code) in enumerate(non_ascii_in_preview[:5]):
                        print(f"    {i+1}. Pos {pos}: '{char}' (U+{code:04X})")
                
                # Test Guy Raz pre-cleaning
                print("  Testing Guy Raz pre-cleaning...")
                import re
                cleaned_text = re.sub(r'[^\\x20-\\x7E\\n\\r\\t]+', ' ', text)
                print(f"  After pre-cleaning: {len(cleaned_text)} chars")
                print(f"  Preview after cleaning: {cleaned_text[:200]}")
                
                return text  # Return the first successful extraction
            else:
                print(f"  ❌ No element found")
        
        print("❌ No Substack selectors worked")
        return None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    test_guy_raz_extraction()