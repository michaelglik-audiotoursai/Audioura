#!/usr/bin/env python3
"""
DEBUG Step 4: Unicode Replacement
Test what happens to Guy Raz content before and after Unicode replacement
"""
import requests
from bs4 import BeautifulSoup

def debug_unicode_replacement():
    """Debug Unicode replacement step by step"""
    
    # Guy Raz newsletter URL
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print("=== STEP 4 DEBUG: Unicode Replacement ===")
    print(f"URL: {url}")
    print()
    
    # Get raw content
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract content using Substack selector
        element = soup.select_one('.available-content .body.markup')
        if not element:
            element = soup.select_one('article .body.markup')
        if not element:
            element = soup.select_one('.post-content .body.markup')
        
        if element:
            # Remove problematic elements
            for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                tag.decompose()
            
            # Get raw text
            raw_text = element.get_text(separator=' ', strip=True)
            
            print("=== BEFORE Unicode Replacement ===")
            print(f"Length: {len(raw_text)} characters")
            print(f"First 300 chars: {repr(raw_text[:300])}")
            print()
            
            # Check for Unicode characters
            unicode_chars = []
            for i, char in enumerate(raw_text[:1000]):  # Check first 1000 chars
                if ord(char) > 127:
                    unicode_chars.append((i, char, ord(char), hex(ord(char))))
            
            print(f"Unicode characters found in first 1000 chars: {len(unicode_chars)}")
            for pos, char, code, hex_code in unicode_chars[:10]:  # Show first 10
                print(f"  Position {pos}: '{char}' (U+{hex_code[2:].upper().zfill(4)}, decimal {code})")
            if len(unicode_chars) > 10:
                print(f"  ... and {len(unicode_chars) - 10} more")
            print()
            
            # Apply Unicode replacement
            replaced_text = raw_text.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
            
            print("=== AFTER Unicode Replacement ===")
            print(f"Length: {len(replaced_text)} characters")
            print(f"First 300 chars: {repr(replaced_text[:300])}")
            print()
            
            # Check changes
            if len(raw_text) != len(replaced_text):
                print(f"⚠️  LENGTH CHANGED: {len(raw_text)} → {len(replaced_text)} ({len(replaced_text) - len(raw_text):+d})")
            else:
                print("✅ Length unchanged")
            
            # Count replacements
            replacements = {
                ''': raw_text.count('''),
                ''': raw_text.count('''),
                '"': raw_text.count('"'),
                '"': raw_text.count('"'),
                '—': raw_text.count('—'),
                '–': raw_text.count('–')
            }
            
            total_replacements = sum(replacements.values())
            print(f"Replacements made: {total_replacements} total")
            for char, count in replacements.items():
                if count > 0:
                    print(f"  '{char}' (U+{hex(ord(char))[2:].upper().zfill(4)}): {count} times")
            print()
            
            # Check for remaining Unicode
            remaining_unicode = []
            for i, char in enumerate(replaced_text[:1000]):
                if ord(char) > 127:
                    remaining_unicode.append((i, char, ord(char), hex(ord(char))))
            
            print(f"Remaining Unicode characters: {len(remaining_unicode)}")
            for pos, char, code, hex_code in remaining_unicode[:5]:
                print(f"  Position {pos}: '{char}' (U+{hex_code[2:].upper().zfill(4)}, decimal {code})")
            if len(remaining_unicode) > 5:
                print(f"  ... and {len(remaining_unicode) - 5} more")
            print()
            
            # Test binary detection on both versions
            from newsletter_processor_service import is_binary_content
            
            print("=== Binary Detection Test ===")
            raw_is_binary = is_binary_content(raw_text)
            replaced_is_binary = is_binary_content(replaced_text)
            
            print(f"Raw text binary detection: {raw_is_binary}")
            print(f"Replaced text binary detection: {replaced_is_binary}")
            
            if raw_is_binary and not replaced_is_binary:
                print("✅ SUCCESS: Unicode replacement fixed binary detection!")
            elif not raw_is_binary and not replaced_is_binary:
                print("ℹ️  Both versions pass binary detection")
            elif raw_is_binary and replaced_is_binary:
                print("❌ PROBLEM: Both versions fail binary detection")
            else:
                print("⚠️  UNEXPECTED: Raw passes but replaced fails")
            
            print()
            print("=== Content Quality Check ===")
            
            # Word analysis
            raw_words = raw_text.split()
            replaced_words = replaced_text.split()
            
            print(f"Word count - Raw: {len(raw_words)}, Replaced: {len(replaced_words)}")
            
            # Check for readable content
            readable_words_raw = sum(1 for word in raw_words[:100] if len(word) > 1 and any(c.isalnum() for c in word))
            readable_words_replaced = sum(1 for word in replaced_words[:100] if len(word) > 1 and any(c.isalnum() for c in word))
            
            print(f"Readable words (first 100) - Raw: {readable_words_raw}, Replaced: {readable_words_replaced}")
            
            # Sample content comparison
            print("\n=== Sample Content Comparison ===")
            print("Raw (chars 500-800):")
            print(repr(raw_text[500:800]))
            print("\nReplaced (chars 500-800):")
            print(repr(replaced_text[500:800]))
            
        else:
            print("❌ Could not find content element")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_unicode_replacement()