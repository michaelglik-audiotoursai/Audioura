#!/usr/bin/env python3
"""
Check what articles were created for the enhanced MailChimp newsletter
"""
import requests
import json

def check_mailchimp_results():
    newsletter_id = 106  # Latest MailChimp newsletter
    
    print(f"Checking articles for MailChimp Newsletter ID: {newsletter_id}")
    
    try:
        # Get the articles
        response = requests.post("http://localhost:5017/get_articles_by_newsletter_id", 
                               json={"newsletter_id": newsletter_id})
        
        if response.status_code == 200:
            result = response.json()
            articles = result.get('articles', [])
            
            print(f"\\nFound {len(articles)} articles:")
            print("=" * 80)
            
            for i, article in enumerate(articles, 1):
                title = article.get('title', 'No title')
                url = article.get('url', 'No URL')
                author = article.get('author', 'Unknown')
                article_id = article.get('article_id', 'No ID')
                
                print(f"{i}. {title}")
                print(f"   Author: {author}")
                print(f"   URL: {url}")
                print(f"   Article ID: {article_id}")
                print()
            
            # Try to get one of the ZIP files
            if articles:
                first_article_id = articles[0]['article_id']
                print(f"Attempting to download first article ZIP: {first_article_id}")
                
                zip_response = requests.get(f"http://localhost:5012/download/{first_article_id}")
                if zip_response.status_code == 200:
                    with open(f"mailchimp_article_{first_article_id[:8]}.zip", "wb") as f:
                        f.write(zip_response.content)
                    print(f"Downloaded ZIP file: mailchimp_article_{first_article_id[:8]}.zip ({len(zip_response.content)} bytes)")
                else:
                    print(f"Failed to download ZIP: HTTP {zip_response.status_code}")
        else:
            print(f"Failed to get articles: HTTP {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_mailchimp_results()