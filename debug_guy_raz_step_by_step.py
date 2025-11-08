#!/usr/bin/env python3
"""
Step-by-step debugging of Guy Raz newsletter processing
No assumptions - trace every step
"""

import requests
from bs4 import BeautifulSoup
import json

def debug_step_by_step():
    """Debug Guy Raz newsletter processing step by step"""
    
    url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print("=" * 80)
    print("STEP-BY-STEP DEBUG: Guy Raz Newsletter Processing")
    print(f"URL: {url}")
    print("=" * 80)
    
    # STEP 1: HTTP Request
    print("\nSTEP 1: HTTP REQUEST")
    print("-" * 40)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"SUCCESS HTTP Status: {response.status_code}")
        print(f"SUCCESS Content-Type: {response.headers.get('content-type', 'Unknown')}")
        print(f"SUCCESS Content-Encoding: {response.headers.get('content-encoding', 'None')}")
        print(f"SUCCESS Raw Content Length: {len(response.content)} bytes")
        print(f"SUCCESS Text Content Length: {len(response.text)} chars")
        print(f"SUCCESS First 200 chars: {repr(response.text[:200])}")
        
        if response.status_code != 200:
            print(f"ERROR HTTP ERROR: Status {response.status_code}")
            return
            
    except Exception as e:
        print(f"ERROR HTTP REQUEST FAILED: {e}")
        return
    
    # STEP 2: BeautifulSoup Parsing
    print("\nSTEP 2: HTML PARSING")
    print("-" * 40)
    
    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        print(f"SUCCESS Soup Created: {len(str(soup))} chars")
        print(f"SUCCESS Title Tag: {soup.title.string if soup.title else 'None'}")
        print(f"SUCCESS Body Exists: {soup.body is not None}")
        
        # Test key selectors
        selectors_to_test = [
            '.available-content .body.markup',
            '.post-content .body.markup', 
            'article .body.markup',
            'article',
            '.post-content'
        ]
        
        print(f"SUCCESS Selector Test Results:")
        for selector in selectors_to_test:
            elements = soup.select(selector)
            print(f"   {selector}: {len(elements)} elements found")
            if elements:
                text_length = len(elements[0].get_text(strip=True))
                print(f"      First element text length: {text_length} chars")
                
    except Exception as e:
        print(f"ERROR HTML PARSING FAILED: {e}")
        return
    
    # STEP 3: Content Extraction (try each selector)
    print("\nSTEP 3: CONTENT EXTRACTION")
    print("-" * 40)
    
    substack_selectors = [
        '.available-content .body.markup',
        '.post-content .body.markup',
        'article .body.markup',
        '.single-post .body.markup'
    ]
    
    extracted_content = None
    successful_selector = None
    
    for selector in substack_selectors:
        try:
            print(f"\n   Testing selector: {selector}")
            element = soup.select_one(selector)
            
            if element:
                # Remove problematic elements
                for tag in element.find_all(['script', 'style', 'img', 'svg', 'canvas', 'object', 'embed']):
                    tag.decompose()
                
                text = element.get_text(separator=' ', strip=True)
                print(f"   SUCCESS Found element with {len(text)} chars")
                print(f"   SUCCESS First 300 chars: {repr(text[:300])}")
                
                if len(text) > 200:
                    extracted_content = text
                    successful_selector = selector
                    print(f"   SUCCESS SELECTED: This selector provides substantial content")
                    break
                else:
                    print(f"   WARNING Content too short, trying next selector")
            else:
                print(f"   ERROR No element found")
                
        except Exception as e:
            print(f"   ERROR Selector failed: {e}")
    
    if not extracted_content:
        print(f"\nERROR NO CONTENT EXTRACTED from any Substack selector")
        return
    
    print(f"\nSUCCESS CONTENT EXTRACTED using selector: {successful_selector}")
    print(f"SUCCESS Raw content length: {len(extracted_content)} chars")
    
    # STEP 4: Unicode Replacement
    print("\nSTEP 4: UNICODE REPLACEMENT")
    print("-" * 40)
    
    print(f"Before Unicode replacement: {len(extracted_content)} chars")
    print(f"Sample before: {repr(extracted_content[:200])}")
    
    # Apply Unicode replacement
    unicode_replaced = extracted_content.replace(''', "'").replace(''', "'").replace('"', '"').replace('"', '"').replace('—', '-').replace('–', '-')
    
    print(f"After Unicode replacement: {len(unicode_replaced)} chars")
    print(f"Sample after: {repr(unicode_replaced[:200])}")
    print(f"Length change: {len(extracted_content)} -> {len(unicode_replaced)} ({len(unicode_replaced) - len(extracted_content):+d})")
    
    # STEP 5: Binary Detection Test
    print("\nSTEP 5: BINARY DETECTION TEST")
    print("-" * 40)
    
    # Test binary detection function (simplified version)
    def test_binary_detection(text):
        if not text or not isinstance(text, str):
            return True, "Not a string or empty"
        
        try:
            # Check for null bytes
            if '\\x00' in text:
                return True, "Contains null bytes"
            
            # Check for Unicode replacement characters
            if '\\ufffd' in text:
                return True, "Contains Unicode replacement chars"
            
            # Check printable character ratio
            printable_chars = sum(1 for c in text if c.isprintable() or c.isspace())
            total_chars = len(text)
            
            if total_chars > 0:
                printable_ratio = printable_chars / total_chars
                if printable_ratio < 0.7:
                    return True, f"Low printable ratio: {printable_ratio:.3f}"
            
            # Check control characters
            problem_control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\\n\\r\\t')
            if total_chars > 0 and problem_control_chars / total_chars > 0.05:
                return True, f"Too many control chars: {problem_control_chars}/{total_chars}"
            
            # Try UTF-8 encoding
            text.encode('utf-8')
            
            return False, "Clean content"
            
        except Exception as e:
            return True, f"Exception: {e}"
    
    is_binary_before, reason_before = test_binary_detection(extracted_content)
    is_binary_after, reason_after = test_binary_detection(unicode_replaced)
    
    print(f"Binary detection BEFORE Unicode replacement: {is_binary_before} ({reason_before})")
    print(f"Binary detection AFTER Unicode replacement: {is_binary_after} ({reason_after})")
    
    if is_binary_after:
        print(f"ERROR CONTENT REJECTED: Binary detection failed after Unicode replacement")
        print(f"ERROR Reason: {reason_after}")
        
        # Show problematic characters
        problem_chars = []
        for i, char in enumerate(unicode_replaced[:500]):
            if not (char.isprintable() or char.isspace()):
                problem_chars.append(f"pos {i}: {repr(char)} (ord {ord(char)})")
        
        if problem_chars:
            print(f"ERROR Problematic characters found: {problem_chars[:10]}")
        
        return
    
    print(f"SUCCESS CONTENT ACCEPTED: Passed binary detection")
    
    # STEP 6: Final Content Preparation
    print("\nSTEP 6: FINAL CONTENT PREPARATION")
    print("-" * 40)
    
    # Extract title
    page_title = soup.title.string if soup.title else "Newsletter Article"
    clean_title = page_title.replace(' | Substack', '').replace(' - Newsletter', '').strip()
    
    print(f"Page title: {repr(page_title)}")
    print(f"Clean title: {repr(clean_title)}")
    
    # Format final content
    final_content = f"NEWSLETTER: {clean_title}\\n\\nCONTENT: {unicode_replaced}"
    
    print(f"Final content length: {len(final_content)} chars")
    print(f"Final content preview: {repr(final_content[:300])}")
    
    # STEP 7: Test Newsletter Processor API
    print("\nSTEP 7: NEWSLETTER PROCESSOR API TEST")
    print("-" * 40)
    
    try:
        api_payload = {
            "newsletter_url": url,
            "user_id": "debug_test",
            "max_articles": 5
        }
        
        print(f"Sending API request to newsletter processor...")
        api_response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=api_payload,
            timeout=60
        )
        
        print(f"API Status: {api_response.status_code}")
        
        if api_response.status_code == 200:
            result = api_response.json()
            print(f"SUCCESS API SUCCESS")
            print(f"   Newsletter ID: {result.get('newsletter_id')}")
            print(f"   Articles Created: {result.get('articles_created')}")
            print(f"   Articles Failed: {result.get('articles_failed')}")
            
            if result.get('failed_articles'):
                print(f"   Failed Articles: {result['failed_articles']}")
        else:
            print(f"ERROR API FAILED: {api_response.status_code}")
            try:
                error_result = api_response.json()
                print(f"   Error: {error_result}")
            except:
                print(f"   Raw response: {api_response.text[:500]}")
                
    except Exception as e:
        print(f"ERROR API TEST FAILED: {e}")
    
    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    debug_step_by_step()