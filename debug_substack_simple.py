#!/usr/bin/env python3
"""
Simple debug for Substack selectors without emoji
"""
import requests
from bs4 import BeautifulSoup

def debug_substack_simple():
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom"
    
    print("=== SUBSTACK DEBUG ===")
    print(f"URL: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers, timeout=10)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    print(f"HTML length: {len(response.text)} chars")
    
    # Test each selector
    selectors = [
        '.available-content .body.markup',
        '.post-content .body.markup', 
        'article .body.markup',
        '.single-post .body.markup'
    ]
    
    for i, selector in enumerate(selectors, 1):
        print(f"\n{i}. Testing: {selector}")
        element = soup.select_one(selector)
        
        if element:
            print(f"   FOUND element")
            text = element.get_text(separator=' ', strip=True)
            print(f"   Text length: {len(text)} chars")
            print(f"   Preview: {text[:150]}...")
            
            # Apply cleaning
            cleaned = text.replace("'", "'").replace("'", "'").replace(""", '"').replace(""", '"')
            print(f"   After cleaning: {len(cleaned)} chars")
            
            if len(cleaned) > 200:
                words = cleaned.split()
                valid_words = sum(1 for word in words if len(word) > 1 and any(c.isalnum() for c in word))
                ratio = valid_words / len(words) if words else 0
                print(f"   Words: {len(words)}, Valid: {valid_words} ({ratio:.1%})")
                
                if ratio > 0.5:
                    print(f"   PASSES - would use this content")
                    return cleaned
                else:
                    print(f"   FAILS word validation")
            else:
                print(f"   FAILS length validation")
        else:
            print(f"   NOT FOUND")
    
    print(f"\nNo selectors worked - would use fallback")
    return None

if __name__ == "__main__":
    result = debug_substack_simple()
    if result:
        print(f"\nSUCCESS: {len(result)} chars extracted")
    else:
        print(f"\nFAILED: Using fallback content")