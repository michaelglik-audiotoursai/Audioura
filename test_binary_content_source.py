#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
import re

def test_binary_content_source():
    """Test to isolate where binary content contamination occurs"""
    
    # Test URL - Guy Raz newsletter
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print(f"Testing binary content source for: {url}")
    
    # Step 1: Test raw HTTP response
    print("\n=== STEP 1: Raw HTTP Response ===")
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
        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
        print(f"Content-Encoding: {response.headers.get('content-encoding', 'None')}")
        print(f"Raw content length: {len(response.content)} bytes")
        print(f"Text content length: {len(response.text)} chars")
        
        # Check if raw content has binary data
        try:
            # Try to decode as UTF-8
            decoded_text = response.content.decode('utf-8')
            print("[OK] Raw content decodes cleanly as UTF-8")
            
            # Check for null bytes or other binary indicators
            if '\x00' in decoded_text:
                print("[ERROR] NULL BYTES found in decoded content")
            else:
                print("[OK] No null bytes in decoded content")
                
            # Check printable ratio
            printable_chars = sum(1 for c in decoded_text if c.isprintable() or c.isspace())
            total_chars = len(decoded_text)
            printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
            print(f"Printable ratio: {printable_ratio:.3f} ({printable_chars}/{total_chars})")
            
            if printable_ratio < 0.8:
                print("[ERROR] LOW PRINTABLE RATIO - likely binary contamination")
            else:
                print("[OK] Good printable ratio")
                
        except UnicodeDecodeError as e:
            print(f"[ERROR] UNICODE DECODE ERROR: {e}")
            return
        
        # Step 2: Test BeautifulSoup parsing
        print("\n=== STEP 2: BeautifulSoup Parsing ===")
        soup = BeautifulSoup(response.content, 'html.parser')
        print(f"Soup created successfully")
        
        # Step 3: Test content extraction
        print("\n=== STEP 3: Content Extraction ===")
        
        # Try Substack selectors
        substack_selectors = [
            '.available-content .body.markup',
            '.post-content .body.markup',
            'article .body.markup',
            '.single-post .body.markup'
        ]
        
        for selector in substack_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    print(f"\nFound content with selector: {selector}")
                    
                    # Get raw text
                    raw_text = element.get_text(separator=' ', strip=True)
                    print(f"Raw text length: {len(raw_text)} chars")
                    
                    # Check for binary content in extracted text
                    if '\x00' in raw_text:
                        print("[ERROR] NULL BYTES found in extracted text")
                    else:
                        print("[OK] No null bytes in extracted text")
                    
                    # Check printable ratio
                    printable_chars = sum(1 for c in raw_text if c.isprintable() or c.isspace())
                    total_chars = len(raw_text)
                    printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
                    print(f"Printable ratio: {printable_ratio:.3f}")
                    
                    if printable_ratio < 0.8:
                        print("[ERROR] BINARY CONTAMINATION in extracted text")
                        # Show first 200 chars with repr to see binary data
                        print(f"First 200 chars (repr): {repr(raw_text[:200])}")
                    else:
                        print("[OK] Clean extracted text")
                        print(f"First 200 chars: {raw_text[:200]}...")
                    
                    break
            except Exception as e:
                print(f"Error with selector {selector}: {e}")
        
        # Step 4: Test title extraction
        print("\n=== STEP 4: Title Extraction ===")
        title_element = soup.select_one('title')
        if title_element:
            title_text = title_element.get_text(strip=True)
            print(f"Title: {repr(title_text)}")
            
            # Check title for binary content
            if any(ord(c) < 32 and c not in '\n\r\t' for c in title_text):
                print("[ERROR] BINARY CONTENT in title")
            else:
                print("[OK] Clean title")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_binary_content_source()