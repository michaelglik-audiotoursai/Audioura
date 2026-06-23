#!/usr/bin/env python3
"""
Test enhanced MailChimp newsletter processing
"""
import requests
import json

def test_enhanced_mailchimp():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("Testing Enhanced MailChimp Newsletter Processing")
    
    payload = {
        "newsletter_url": url,
        "user_id": "test_user",
        "max_articles": 15
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
            print(f"\\nFailed Articles:")
            for i, failed in enumerate(result['failed_articles'][:5], 1):
                print(f"  {i}. {failed.get('url', 'Unknown URL')[:60]}...")
                print(f"     Error: {failed.get('error', 'Unknown error')}")
        
        if result.get('status') == 'success':
            newsletter_id = result.get('newsletter_id')
            print(f"\\nNewsletter ID: {newsletter_id}")
            
            # Get the articles to see what we created
            articles_response = requests.post("http://localhost:5017/get_articles_by_newsletter_id", 
                                            json={"newsletter_id": newsletter_id})
            if articles_response.status_code == 200:
                articles_result = articles_response.json()
                articles = articles_result.get('articles', [])
                print(f"\\nCreated Articles ({len(articles)}):")
                for i, article in enumerate(articles, 1):
                    print(f"  {i}. {article.get('title', 'No title')[:60]}...")
                    print(f"     URL: {article.get('url', 'No URL')[:60]}...")
        
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_enhanced_mailchimp()