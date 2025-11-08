#!/usr/bin/env python3
"""
Simple Guy Raz extraction test without emoji characters
"""
import requests
from bs4 import BeautifulSoup

def test_guy_raz_simple():
    """Test Guy Raz extraction with proper encoding handling"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom"
    
    print("=== GUY RAZ EXTRACTION TEST ===")
    print(f"URL: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    try:
        print("Making HTTP request...")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Encoding: {response.encoding}")
        
        # Force UTF-8 encoding
        response.encoding = 'utf-8'
        
        print("Parsing with BeautifulSoup...")
        soup = BeautifulSoup(response.text, 'html.parser')  # Use .text instead of .content
        
        print("Testing Substack selector...")
        element = soup.select_one('.available-content .body.markup')
        
        if element:
            print("FOUND element with selector!")
            
            # Remove problematic elements
            for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                tag.decompose()
            
            # Extract text
            text = element.get_text(separator=' ', strip=True)
            print(f"Extracted text length: {len(text)} chars")
            
            # Show first 300 chars
            preview = text[:300]
            print(f"Preview: {preview}")
            
            # Check for problematic characters
            problem_chars = []
            for i, char in enumerate(preview):
                if ord(char) > 127:  # Non-ASCII
                    problem_chars.append((i, char, ord(char), hex(ord(char))))
            
            if problem_chars:
                print(f"Non-ASCII characters in preview: {len(problem_chars)}")
                for i, (pos, char, code, hex_code) in enumerate(problem_chars[:10]):
                    print(f"  {i+1}. Pos {pos}: '{char}' = {code} ({hex_code})")
            else:
                print("No problematic characters found in preview")
            
            # Test the Guy Raz Unicode replacement
            print("Testing Guy Raz Unicode replacement...")
            cleaned = text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('\u2014', '-').replace('\u2013', '-')
            print(f"After Unicode replacement: {len(cleaned)} chars")
            print(f"Cleaned preview: {cleaned[:300]}")
            
            return cleaned
        else:
            print("NO element found with Substack selector")
            
            # Try alternative selectors
            alt_selectors = ['article', '.post-content', 'main']
            for selector in alt_selectors:
                elem = soup.select_one(selector)
                if elem:
                    print(f"Found element with {selector}")
                    break
            
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    result = test_guy_raz_simple()
    if result:
        print(f"SUCCESS: Extracted {len(result)} characters")
    else:
        print("FAILED: No content extracted")