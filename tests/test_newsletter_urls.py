#!/usr/bin/env python3
"""
Test newsletter URL content extraction to diagnose issues
"""
import requests
from bs4 import BeautifulSoup

def test_url_content(url, name):
    print(f"\n=== TESTING {name} ===")
    print(f"URL: {url}")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Test current Substack selectors
            substack_selectors = [
                '.available-content .body.markup',
                '.post-content .body.markup',
                'article .body.markup',
                '.single-post .body.markup'
            ]
            
            print(f"\n--- Testing Substack Selectors ---")
            for selector in substack_selectors:
                try:
                    element = soup.select_one(selector)
                    if element:
                        text = element.get_text(separator=' ', strip=True)
                        print(f"✅ {selector}: {len(text)} chars")
                        if len(text) > 0:
                            print(f"   Preview: {text[:100]}...")
                    else:
                        print(f"❌ {selector}: Not found")
                except Exception as e:
                    print(f"❌ {selector}: Error - {e}")
            
            # Test generic selectors
            generic_selectors = [
                'article',
                '.post-content', 
                '.newsletter-content',
                '.entry-content',
                'main',
                '[role="main"]',
                '.content',
                '.email-content',
                '.message-body'
            ]
            
            print(f"\n--- Testing Generic Selectors ---")
            for selector in generic_selectors:
                try:
                    element = soup.select_one(selector)
                    if element:
                        text = element.get_text(separator=' ', strip=True)
                        print(f"✅ {selector}: {len(text)} chars")
                        if len(text) > 200:
                            print(f"   Preview: {text[:100]}...")
                    else:
                        print(f"❌ {selector}: Not found")
                except Exception as e:
                    print(f"❌ {selector}: Error - {e}")
            
            # Check page title
            title = soup.title.string if soup.title else "No title"
            print(f"\nPage Title: {title}")
            
            # Check for common newsletter platforms
            page_html = str(soup).lower()
            platforms = {
                'mailchimp': 'mailchimp' in page_html or 'mailchi.mp' in url,
                'constant_contact': 'constantcontact' in page_html,
                'campaign_monitor': 'campaignmonitor' in page_html,
                'boston_globe': 'bostonglobe' in url,
                'email_view': 'view.email' in url
            }
            
            detected_platforms = [k for k, v in platforms.items() if v]
            print(f"Detected Platforms: {detected_platforms}")
            
            # Show all available CSS classes for analysis
            all_classes = set()
            for element in soup.find_all(class_=True):
                if isinstance(element.get('class'), list):
                    all_classes.update(element.get('class'))
            
            content_classes = [cls for cls in all_classes if any(keyword in cls.lower() for keyword in ['content', 'body', 'text', 'article', 'message', 'email'])]
            print(f"Content-related classes: {sorted(content_classes)[:10]}")
            
        else:
            print(f"❌ Failed to fetch content: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    # Test the two problematic URLs
    test_url_content(
        "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013",
        "MailChimp Newsletter"
    )
    
    test_url_content(
        "https://view.email.bostonglobe.com/?qs=f5c5b263a361410773c7a0e695d276d61955798a94e17c8781cf3bcb26491dc1a43af8ddcd9bb3db4e9ad7a1d2a8cfb0eadf7fce21a8ebe84926d5498aeb789055a55cc54c9e3943fdf0e945c7e2066f3e0fd9eaa2c23a46e46c6745319389d8",
        "Boston Globe Email"
    )