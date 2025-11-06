#!/usr/bin/env python3
"""
Find actual article links in MailChimp newsletter
"""
import requests
from bs4 import BeautifulSoup
import re

def find_article_links():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("=== FINDING ARTICLE LINKS IN MAILCHIMP NEWSLETTER ===")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            print("=== ALL LINKS IN NEWSLETTER ===")
            links = soup.find_all('a', href=True)
            
            article_links = []
            for i, link in enumerate(links, 1):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                print(f"{i}. Text: '{text[:50]}...'")
                print(f"   URL: {href}")
                
                # Look for Newton Beacon article links
                if 'newtonbeacon.org' in href and len(text) > 10:
                    article_links.append((href, text))
                    print(f"   *** POTENTIAL ARTICLE ***")
                print()
            
            print(f"=== FOUND {len(article_links)} NEWTON BEACON ARTICLES ===")
            for i, (href, text) in enumerate(article_links, 1):
                print(f"{i}. {text}")
                print(f"   {href}")
                print()
            
            # Also check for any other news site links
            print("=== OTHER NEWS SITE LINKS ===")
            news_domains = ['boston.com', 'bostonglobe.com', 'wbur.org', 'wcvb.com', 'nbcboston.com']
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if any(domain in href for domain in news_domains) and len(text) > 10:
                    print(f"Text: {text[:50]}...")
                    print(f"URL: {href}")
                    print()
                    
        else:
            print(f"Failed to fetch: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_article_links()