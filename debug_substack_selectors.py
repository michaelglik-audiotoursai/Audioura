#!/usr/bin/env python3
"""
Debug Substack content selector extraction step by step
"""
import requests
from bs4 import BeautifulSoup

def debug_substack_extraction():
    """Debug each step of Substack content extraction"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom"
    
    print("=== SUBSTACK SELECTOR DEBUG ===")
    print(f"URL: {url}")
    
    # Step 1: HTTP Request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    print("\nStep 1: HTTP Request")
    response = requests.get(url, headers=headers, timeout=10)
    response.encoding = 'utf-8'
    print(f"Status: {response.status_code}")
    print(f"Content length: {len(response.text)} chars")
    
    # Step 2: BeautifulSoup parsing
    print("\nStep 2: BeautifulSoup parsing")
    soup = BeautifulSoup(response.text, 'html.parser')
    print("Parsing complete")
    
    # Step 3: Test each Substack selector
    print("\nStep 3: Testing Substack selectors")
    substack_selectors = [
        '.available-content .body.markup',
        '.post-content .body.markup',
        'article .body.markup',
        '.single-post .body.markup'
    ]
    
    for i, selector in enumerate(substack_selectors, 1):
        print(f"\n3.{i} Testing selector: '{selector}'")
        
        try:
            element = soup.select_one(selector)
            if element:
                print(f"  ✅ Element found!")
                print(f"  Tag: {element.name}")
                print(f"  Classes: {element.get('class', [])}")
                
                # Check for problematic child elements
                scripts = element.find_all('script')
                styles = element.find_all('style')
                imgs = element.find_all('img')
                print(f"  Child elements: {len(scripts)} scripts, {len(styles)} styles, {len(imgs)} images")
                
                # Get raw text before cleaning
                raw_text = element.get_text(separator=' ', strip=True)
                print(f"  Raw text length: {len(raw_text)} chars")
                print(f"  Raw preview: {raw_text[:200]}...")
                
                # Remove problematic elements (as done in newsletter processor)
                element_copy = BeautifulSoup(str(element), 'html.parser')
                for tag in element_copy.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                    tag.decompose()
                
                # Get text after element removal
                cleaned_text = element_copy.get_text(separator=' ', strip=True)
                print(f"  After element removal: {len(cleaned_text)} chars")
                print(f"  Cleaned preview: {cleaned_text[:200]}...")
                
                # Apply Guy Raz Unicode replacement
                unicode_cleaned = cleaned_text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('\u2014', '-').replace('\u2013', '-')
                print(f"  After Unicode replacement: {len(unicode_cleaned)} chars")
                print(f"  Unicode preview: {unicode_cleaned[:200]}...")
                
                # Check validation criteria
                if len(unicode_cleaned) > 200:
                    words = unicode_cleaned.split()
                    valid_words = sum(1 for word in words if len(word) > 1 and any(c.isalnum() for c in word))
                    word_ratio = valid_words / len(words) if words else 0
                    print(f"  Validation: {len(words)} words, {valid_words} valid ({word_ratio:.2%})")
                    
                    if word_ratio > 0.5:
                        print(f"  ✅ PASSES validation - would be used as main content")
                        return unicode_cleaned
                    else:
                        print(f"  ❌ FAILS word validation ({word_ratio:.2%} < 50%)")
                else:
                    print(f"  ❌ FAILS length validation ({len(unicode_cleaned)} < 200)")
            else:
                print(f"  ❌ No element found")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Step 4: Check fallback selectors
    print(f"\nStep 4: Testing fallback selectors")
    fallback_selectors = ['article', '.post-content', 'main', '[role=\"main\"]']
    
    for i, selector in enumerate(fallback_selectors, 1):
        print(f"\n4.{i} Testing fallback: '{selector}'")
        try:
            element = soup.select_one(selector)
            if element:
                print(f"  ✅ Element found: {element.name}")
                # Quick test
                text = element.get_text(separator=' ', strip=True)
                print(f"  Text length: {len(text)} chars")
                if len(text) > 200:
                    print(f"  Preview: {text[:200]}...")
            else:
                print(f"  ❌ No element found")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Step 5: Check Guy Raz fallback logic
    print(f"\nStep 5: Guy Raz fallback logic")
    print("Checking if 'guyraz.substack.com' in URL...")
    if 'guyraz.substack.com' in url:
        print("✅ Guy Raz detected - fallback logic would trigger")
        
        # Test title extraction
        if soup.title:
            title_text = soup.title.get_text(strip=True)
            print(f"Page title: {title_text}")
            
        # Test meta description
        meta_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        if meta_tag and meta_tag.get('content'):
            meta_desc = meta_tag['content']
            print(f"Meta description: {meta_desc[:200]}...")
        
        print("❌ Would use generic fallback content (262 chars)")
    
    return None

if __name__ == "__main__":
    result = debug_substack_extraction()
    if result:
        print(f"\n✅ SUCCESS: Found content with {len(result)} chars")
    else:
        print(f"\n❌ FAILED: No content found, would use fallback")