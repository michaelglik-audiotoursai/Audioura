#!/usr/bin/env python3
"""
Test MailChimp newsletter with debugging focused on main article
"""
import requests
import json

def test_main_article_debug():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("Testing MailChimp Newsletter with Main Article Debugging")
    
    payload = {
        "newsletter_url": url,
        "user_id": "test_user",
        "max_articles": 3  # Limit to just a few articles to focus on main article
    }
    
    try:
        response = requests.post("http://localhost:5017/process_newsletter", json=payload, timeout=300)
        print(f"Status Code: {response.status_code}")
        
        result = response.json()
        print(f"Status: {result.get('status')}")
        print(f"Articles Found: {result.get('articles_found', 0)}")
        print(f"Articles Created: {result.get('articles_created', 0)}")
        
        if result.get('status') == 'success':
            newsletter_id = result.get('newsletter_id')
            print(f"Newsletter ID: {newsletter_id}")
            
            # Check what articles were created
            articles_response = requests.post("http://localhost:5017/get_articles_by_newsletter_id", 
                                            json={"newsletter_id": newsletter_id})
            if articles_response.status_code == 200:
                articles_result = articles_response.json()
                articles = articles_result.get('articles', [])
                print(f"\\nCreated Articles ({len(articles)}):")
                for i, article in enumerate(articles, 1):
                    title = article.get('title', 'No title')
                    url_preview = article.get('url', 'No URL')[:60]
                    article_id = article.get('article_id', 'No ID')
                    
                    print(f"  {i}. {title}")
                    print(f"     URL: {url_preview}...")
                    print(f"     ID: {article_id}")
                    
                    # Check if this is the main article (MailChimp URL)
                    if 'mailchi.mp' in article.get('url', ''):
                        print(f"     *** THIS IS THE MAIN ARTICLE ***")
                        print(f"     Testing download...")
                        
                        # Try to download this article
                        zip_response = requests.get(f"http://localhost:5012/download/{article_id}")
                        if zip_response.status_code == 200:
                            print(f"     Download SUCCESS: {len(zip_response.content)} bytes")
                        else:
                            print(f"     Download FAILED: HTTP {zip_response.status_code}")
        
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_main_article_debug()