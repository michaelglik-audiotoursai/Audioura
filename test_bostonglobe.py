#!/usr/bin/env python3
"""
Test Boston Globe email content extraction
"""
import requests
from bs4 import BeautifulSoup

def test_bostonglobe():
    url = "https://view.email.bostonglobe.com/?qs=f5c5b263a361410773c7a0e695d276d61955798a94e17c8781cf3bcb26491dc1a43af8ddcd9bb3db4e9ad7a1d2a8cfb0eadf7fce21a8ebe84926d5498aeb789055a55cc54c9e3943fdf0e945c7e2066f3e0fd9eaa2c23a46e46c6745319389d8"
    
    print("Testing Boston Globe Email")
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
            
            # Test email-specific selectors
            email_selectors = [
                '.email-content',
                '.message-body',
                '.content',
                '.main-content',
                'table[role="presentation"]',
                'td[class*="content"]',
                '.article-content',
                '.newsletter-content'
            ]
            
            print("\n--- Testing Email Selectors ---")
            for selector in email_selectors:
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
            
            # Check all table content
            print("\n--- Testing Table Content ---")
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables")
            
            for i, table in enumerate(tables[:5]):  # Check first 5 tables
                text = table.get_text(separator=' ', strip=True)
                if len(text) > 50:
                    print(f"Table {i+1}: {len(text)} chars - {text[:100]}...")
            
            # Check for article links or content
            print("\n--- Looking for Article Links ---")
            links = soup.find_all('a', href=True)
            article_links = []
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                if 'bostonglobe.com' in href and len(text) > 10:
                    article_links.append((href, text))
            
            print(f"Found {len(article_links)} potential article links")
            for href, text in article_links[:5]:
                print(f"  Link: {text[:50]}... -> {href[:80]}...")
                
        else:
            print(f"Failed to fetch: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_bostonglobe()