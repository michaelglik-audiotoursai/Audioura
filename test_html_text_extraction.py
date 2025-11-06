#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup

def test_html_text_extraction():
    """Test different methods of extracting clean text from HTML elements"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print(f"Testing HTML text extraction methods for: {url}")
    
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
        print(f"Response encoding: {response.encoding}")
        
        # Use response.text (fixed encoding)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main content element
        element = soup.select_one('.available-content .body.markup')
        if not element:
            print("No content element found")
            return
        
        print(f"Found content element: {element.name}")
        
        # Method 1: Standard get_text()
        print("\n=== METHOD 1: Standard get_text() ===")
        text1 = element.get_text(separator=' ', strip=True)
        print(f"Length: {len(text1)} chars")
        
        # Check for binary contamination
        printable_chars = sum(1 for c in text1 if c.isprintable() or c.isspace())
        total_chars = len(text1)
        printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
        print(f"Printable ratio: {printable_ratio:.3f}")
        
        if printable_ratio < 0.95:
            print("[ERROR] Binary contamination detected")
            print(f"First 200 chars (repr): {repr(text1[:200])}")
        else:
            print("[OK] Clean text")
            print(f"First 200 chars: {text1[:200]}...")
        
        # Method 2: get_text() with encoding normalization
        print("\n=== METHOD 2: get_text() with encoding normalization ===")
        try:
            text2 = element.get_text(separator=' ', strip=True)
            # Try to normalize encoding
            text2_normalized = text2.encode('utf-8', errors='replace').decode('utf-8')
            print(f"Length: {len(text2_normalized)} chars")
            
            # Check for replacement characters
            replacement_count = text2_normalized.count('\ufffd')
            print(f"Replacement characters: {replacement_count}")
            
            if replacement_count == 0:
                print("[OK] No encoding issues")
                print(f"First 200 chars: {text2_normalized[:200]}...")
            else:
                print(f"[WARNING] {replacement_count} characters replaced")
                print(f"First 200 chars: {text2_normalized[:200]}...")
                
        except Exception as e:
            print(f"[ERROR] Encoding normalization failed: {e}")
        
        # Method 3: Manual text extraction
        print("\n=== METHOD 3: Manual text extraction ===")
        try:
            # Remove problematic elements first
            element_copy = soup.select_one('.available-content .body.markup')
            for tag in element_copy.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                tag.decompose()
            
            # Get all text nodes manually
            text_parts = []
            for string in element_copy.stripped_strings:
                # Clean each text node individually
                try:
                    clean_string = str(string).encode('utf-8', errors='replace').decode('utf-8')
                    if clean_string.strip():
                        text_parts.append(clean_string.strip())
                except Exception as e:
                    print(f"Skipping problematic string: {e}")
                    continue
            
            text3 = ' '.join(text_parts)
            print(f"Length: {len(text3)} chars")
            
            # Check quality
            printable_chars = sum(1 for c in text3 if c.isprintable() or c.isspace())
            total_chars = len(text3)
            printable_ratio = printable_chars / total_chars if total_chars > 0 else 0
            print(f"Printable ratio: {printable_ratio:.3f}")
            
            if printable_ratio > 0.95:
                print("[OK] Clean manual extraction")
                print(f"First 200 chars: {text3[:200]}...")
            else:
                print("[ERROR] Still contaminated")
                print(f"First 200 chars (repr): {repr(text3[:200])}")
                
        except Exception as e:
            print(f"[ERROR] Manual extraction failed: {e}")
        
        # Method 4: Character filtering
        print("\n=== METHOD 4: Character filtering ===")
        try:
            text4 = element.get_text(separator=' ', strip=True)
            
            # Filter out non-printable characters
            filtered_chars = []
            for c in text4:
                if c.isprintable() or c in '\n\r\t ':
                    filtered_chars.append(c)
                else:
                    # Replace with space for readability
                    filtered_chars.append(' ')
            
            text4_filtered = ''.join(filtered_chars)
            # Normalize whitespace
            text4_filtered = ' '.join(text4_filtered.split())
            
            print(f"Length: {len(text4_filtered)} chars")
            print(f"First 200 chars: {text4_filtered[:200]}...")
            
        except Exception as e:
            print(f"[ERROR] Character filtering failed: {e}")
            
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")

if __name__ == "__main__":
    test_html_text_extraction()