#!/usr/bin/env python3
"""
Debug MailChimp content extraction to find the actual articles
"""
import requests
from bs4 import BeautifulSoup

def debug_mailchimp():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("=== DEBUGGING MAILCHIMP CONTENT EXTRACTION ===")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            print("=== CURRENT EXTRACTION (WHAT WE'RE GETTING) ===")
            # Test current selectors
            current_selectors = ['.bodyContainer', '#templateBody', '.mcnTextContent']
            
            for selector in current_selectors:
                elements = soup.select(selector)
                if elements:
                    combined_text = ""
                    for element in elements:
                        text = element.get_text(separator=' ', strip=True)
                        combined_text += text + " "
                    
                    print(f"\n{selector}: {len(combined_text)} chars")
                    print(f"Preview: {combined_text[:200]}...")
            
            print("\n=== LOOKING FOR ARTICLE LINKS ===")
            # Look for article links
            links = soup.find_all('a', href=True)
            article_links = []
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Look for meaningful article links (not social media, unsubscribe, etc.)
                if (len(text) > 20 and 
                    not any(skip in href.lower() for skip in ['facebook', 'twitter', 'unsubscribe', 'mailchimp', 'mailto']) and
                    not any(skip in text.lower() for skip in ['unsubscribe', 'facebook', 'twitter', 'follow us'])):
                    article_links.append((href, text))
            
            print(f"Found {len(article_links)} potential article links:")
            for i, (href, text) in enumerate(article_links[:10], 1):
                print(f"{i}. {text[:60]}...")
                print(f"   URL: {href[:80]}...")
            
            print("\n=== LOOKING FOR ARTICLE CONTENT SECTIONS ===")
            # Look for content sections that might contain full articles
            content_selectors = [
                '.mcnTextContent',
                'td[class*="mcnTextContent"]',
                '.bodyContainer .mcnTextBlockInner',
                'table[class*="mcnTextBlock"]',
                '.templateContainer td'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                print(f"\n{selector}: Found {len(elements)} elements")
                
                for i, element in enumerate(elements[:3]):  # Check first 3
                    text = element.get_text(separator=' ', strip=True)
                    if len(text) > 100:
                        print(f"  Element {i+1}: {len(text)} chars - {text[:100]}...")
                        
                        # Check if this element contains article links
                        element_links = element.find_all('a', href=True)
                        if element_links:
                            print(f"    Contains {len(element_links)} links")
                            
        else:
            print(f"Failed to fetch: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_mailchimp()