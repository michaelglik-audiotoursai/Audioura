#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup

def debug_page_structure():
    """Debug the actual page structure to understand why selectors aren't working"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print(f"Debugging page structure for: {url}")
    
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
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Content length: {len(response.text)} chars")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check title
        title = soup.select_one('title')
        if title:
            print(f"Title: {title.get_text(strip=True)}")
        else:
            print("No title found")
        
        # Look for any elements with substantial text content
        print("\n=== Elements with substantial text (>500 chars) ===")
        all_elements = soup.find_all(True)  # Find all elements
        
        text_elements = []
        for element in all_elements:
            if element.name in ['script', 'style', 'meta', 'link', 'head']:
                continue
                
            text = element.get_text(strip=True)
            if len(text) > 500:
                text_elements.append((element.name, element.get('class', []), len(text), text[:100]))
        
        # Sort by text length
        text_elements.sort(key=lambda x: x[2], reverse=True)
        
        for i, (tag, classes, length, preview) in enumerate(text_elements[:10]):
            class_str = '.'.join(classes) if classes else 'no-class'
            print(f"{i+1}. <{tag}> class='{class_str}' - {length} chars")
            print(f"   Preview: {repr(preview)}")
            print()
        
        # Check if this might be a redirect or error page
        print("=== Page Analysis ===")
        body = soup.select_one('body')
        if body:
            body_text = body.get_text(strip=True)
            print(f"Body text length: {len(body_text)} chars")
            
            # Check for common error/redirect indicators
            error_indicators = ['404', 'not found', 'error', 'redirect', 'access denied', 'forbidden']
            for indicator in error_indicators:
                if indicator.lower() in body_text.lower():
                    print(f"[WARNING] Found '{indicator}' in page content")
            
            # Show first 500 chars of body
            print(f"Body preview: {repr(body_text[:500])}")
        else:
            print("No body element found")
            
        # Check for JavaScript-heavy content
        scripts = soup.find_all('script')
        print(f"Found {len(scripts)} script elements")
        
        # Check if content might be in JSON or other format
        for script in scripts[:5]:  # Check first 5 scripts
            script_text = script.get_text()
            if len(script_text) > 1000 and ('content' in script_text.lower() or 'article' in script_text.lower()):
                print(f"[INFO] Large script with content/article keywords: {len(script_text)} chars")
                print(f"Script preview: {repr(script_text[:200])}")
                break
        
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")

if __name__ == "__main__":
    debug_page_structure()