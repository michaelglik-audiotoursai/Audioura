#!/usr/bin/env python3
"""
Test enhanced newsletter processing with MailChimp and Boston Globe
"""
import requests
import json

def test_newsletter(url, name):
    print(f"\n=== Testing {name} ===")
    print(f"URL: {url}")
    
    payload = {
        "newsletter_url": url,
        "user_id": "test_user",
        "max_articles": 10
    }
    
    try:
        response = requests.post("http://localhost:5017/process_newsletter", json=payload, timeout=300)
        print(f"Status Code: {response.status_code}")
        
        result = response.json()
        print(f"Status: {result.get('status')}")
        print(f"Articles Found: {result.get('articles_found', 0)}")
        print(f"Articles Created: {result.get('articles_created', 0)}")
        print(f"Articles Failed: {result.get('articles_failed', 0)}")
        
        if result.get('failed_articles'):
            print(f"Failed Articles:")
            for i, failed in enumerate(result['failed_articles'][:3], 1):
                print(f"  {i}. {failed.get('url', 'Unknown URL')[:60]}...")
                print(f"     Error: {failed.get('error', 'Unknown error')}")
        
        return result.get('newsletter_id')
        
    except Exception as e:
        print(f"Request failed: {e}")
        return None

if __name__ == "__main__":
    # Test MailChimp newsletter
    mailchimp_id = test_newsletter(
        "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013",
        "MailChimp Newsletter"
    )
    
    # Test Boston Globe email
    bostonglobe_id = test_newsletter(
        "https://view.email.bostonglobe.com/?qs=f5c5b263a361410773c7a0e695d276d61955798a94e17c8781cf3bcb26491dc1a43af8ddcd9bb3db4e9ad7a1d2a8cfb0eadf7fce21a8ebe84926d5498aeb789055a55cc54c9e3943fdf0e945c7e2066f3e0fd9eaa2c23a46e46c6745319389d8",
        "Boston Globe Email"
    )
    
    print(f"\n=== Results Summary ===")
    print(f"MailChimp Newsletter ID: {mailchimp_id}")
    print(f"Boston Globe Email ID: {bostonglobe_id}")