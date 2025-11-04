#!/usr/bin/env python3
"""
Test MailChimp newsletter content extraction
"""
import requests
from bs4 import BeautifulSoup

def test_mailchimp():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("Testing MailChimp Newsletter")
    print(f"URL: {url}")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check page title
            title = soup.title.string if soup.title else "No title"
            print(f"Page Title: {title}")
            
            # Test MailChimp specific selectors
            mailchimp_selectors = [
                '.bodyContainer',
                '.mcnTextContent',
                '.templateContainer',
                '#templateBody',
                '.headerContainer',
                '.bodyContent',
                'table[class*="mcn"]',
                'td[class*="mcnTextContent"]'
            ]
            
            print("\n--- Testing MailChimp Selectors ---")
            for selector in mailchimp_selectors:
                try:
                    elements = soup.select(selector)
                    if elements:
                        total_text = ""
                        for element in elements:
                            text = element.get_text(separator=' ', strip=True)
                            total_text += text + " "
                        
                        print(f"FOUND {selector}: {len(elements)} elements, {len(total_text)} chars")
                        if len(total_text) > 100:
                            print(f"   Preview: {total_text[:150]}...")
                    else:
                        print(f"NOT FOUND {selector}")
                except Exception as e:
                    print(f"ERROR {selector}: {e}")
            
            # Check all table content (MailChimp uses tables heavily)
            print("\n--- Testing Table Content ---")
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables")
            
            for i, table in enumerate(tables[:5]):  # Check first 5 tables
                text = table.get_text(separator=' ', strip=True)
                if len(text) > 50:
                    print(f"Table {i+1}: {len(text)} chars - {text[:100]}...")
            
            # Get all text content
            print("\n--- Full Body Text ---")
            body_text = soup.get_text(separator=' ', strip=True)
            print(f"Total body text: {len(body_text)} chars")
            if len(body_text) > 0:
                print(f"Preview: {body_text[:300]}...")
                
        else:
            print(f"Failed to fetch: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_mailchimp()