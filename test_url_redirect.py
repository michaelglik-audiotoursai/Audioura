#!/usr/bin/env python3
"""
Test URL redirect to see what the Boston Globe newsletter URLs actually point to
"""

import requests
import logging

def test_url_redirect():
    """Follow redirects to see final destination"""
    
    test_urls = [
        "https://click.email.bostonglobe.com/?qs=39dc4f12df993629c5e269dd17e0b352d8b847531dd79d7e8c69be0317cc32b5cc8a071de7d5e3dcf673869d27589ed9cdff15774a54efdbbdfcb3dd13af7991",
        "https://click.email.bostonglobe.com/?qs=04d2372f767073e88060d4c942f91afde0ae8e54bd585626ea5864f7e6cea38003a2535ceb513e1f94acde52bcafebe4a7002e07fe0ce79c3ba04cdb4e390fc5"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n=== Testing URL {i} ===")
        print(f"Original: {url}")
        
        try:
            # Follow redirects
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            
            print(f"Final URL: {response.url}")
            print(f"Status Code: {response.status_code}")
            print(f"Content Length: {len(response.text)} chars")
            
            # Check if it's a Boston Globe article
            if 'bostonglobe.com' in response.url:
                print("POINTS TO: Boston Globe domain")
                
                # Check for subscription indicators
                if any(indicator in response.text.lower() for indicator in ['subscribe', 'subscription', 'paywall', 'premium']):
                    print("CONTENT TYPE: Likely subscription-required")
                else:
                    print("CONTENT TYPE: Appears to be free content")
                    
                # Show title if available
                if '<title>' in response.text:
                    title_start = response.text.find('<title>') + 7
                    title_end = response.text.find('</title>', title_start)
                    if title_end > title_start:
                        title = response.text[title_start:title_end].strip()
                        print(f"Title: {title}")
                        
            else:
                print("POINTS TO: Non-article page")
                print(f"Final destination: {response.url}")
                
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_url_redirect()