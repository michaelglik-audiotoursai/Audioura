#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup

def test_encoding_fix():
    """Test different encoding strategies to fix binary contamination"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print(f"Testing encoding fixes for: {url}")
    
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
        
        # Strategy 1: Use response.text (requests handles encoding automatically)
        print("\n=== STRATEGY 1: Use response.text ===")
        try:
            text_content = response.text
            print(f"Text content length: {len(text_content)} chars")
            print(f"Response encoding detected: {response.encoding}")
            
            # Check for binary contamination
            printable_chars = sum(1 for c in text_content if c.isprintable() or c.isspace())
            total_chars = len(text_content)
            printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
            print(f"Printable ratio: {printable_ratio:.3f}")
            
            if printable_ratio > 0.95:
                print("[OK] Clean text using response.text")
                
                # Test BeautifulSoup with clean text
                soup = BeautifulSoup(text_content, 'html.parser')
                
                # Test content extraction
                element = soup.select_one('.available-content .body.markup')
                if element:
                    extracted_text = element.get_text(separator=' ', strip=True)
                    print(f"Extracted content length: {len(extracted_text)} chars")
                    
                    # Check extracted content
                    ext_printable = sum(1 for c in extracted_text if c.isprintable() or c.isspace())
                    ext_total = len(extracted_text)
                    ext_ratio = ext_printable / ext_total if ext_total > 0 else 0
                    print(f"Extracted printable ratio: {ext_ratio:.3f}")
                    
                    if ext_ratio > 0.95:
                        print("[OK] Clean extracted content")
                        print(f"Sample: {extracted_text[:200]}...")
                    else:
                        print("[ERROR] Binary contamination in extracted content")
                        print(f"Sample (repr): {repr(extracted_text[:200])}")
                else:
                    print("[WARNING] No content found with Substack selector")
            else:
                print("[ERROR] Binary contamination in response.text")
                
        except Exception as e:
            print(f"[ERROR] Strategy 1 failed: {e}")
        
        # Strategy 2: Force UTF-8 with error handling
        print("\n=== STRATEGY 2: Force UTF-8 with error handling ===")
        try:
            # Try different error handling strategies
            for error_mode in ['replace', 'ignore', 'strict']:
                try:
                    decoded_content = response.content.decode('utf-8', errors=error_mode)
                    print(f"UTF-8 decode with '{error_mode}': {len(decoded_content)} chars")
                    
                    if error_mode == 'replace':
                        # Count replacement characters
                        replacement_count = decoded_content.count('\ufffd')
                        print(f"Replacement characters: {replacement_count}")
                        
                        if replacement_count == 0:
                            print("[OK] No replacement characters needed")
                        else:
                            print(f"[WARNING] {replacement_count} characters replaced")
                    
                    break  # Use first successful decode
                    
                except UnicodeDecodeError as e:
                    print(f"UTF-8 decode with '{error_mode}' failed: {e}")
                    
        except Exception as e:
            print(f"[ERROR] Strategy 2 failed: {e}")
        
        # Strategy 3: Auto-detect encoding
        print("\n=== STRATEGY 3: Auto-detect encoding ===")
        try:
            import chardet
            detected = chardet.detect(response.content)
            print(f"Detected encoding: {detected}")
            
            if detected['encoding']:
                decoded_content = response.content.decode(detected['encoding'], errors='replace')
                print(f"Decoded with {detected['encoding']}: {len(decoded_content)} chars")
                
                # Check quality
                printable_chars = sum(1 for c in decoded_content if c.isprintable() or c.isspace())
                total_chars = len(decoded_content)
                printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
                print(f"Printable ratio: {printable_ratio:.3f}")
                
        except ImportError:
            print("[INFO] chardet not available, skipping auto-detection")
        except Exception as e:
            print(f"[ERROR] Strategy 3 failed: {e}")
            
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")

if __name__ == "__main__":
    test_encoding_fix()