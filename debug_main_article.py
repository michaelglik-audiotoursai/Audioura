#!/usr/bin/env python3
"""
Debug why the main MailChimp article content is not being extracted
"""
import requests
from bs4 import BeautifulSoup

def debug_main_article_extraction():
    url = "https://mailchi.mp/cffaa0a1186b/friday-news-decoding-the-office-space-market-mystery-10346462?e=f2ed12d013"
    
    print("=== DEBUGGING MAIN ARTICLE EXTRACTION ===")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            print("=== TESTING MAILCHIMP SELECTORS (CURRENT LOGIC) ===")
            
            # Test the exact logic from the newsletter processor
            main_content = ""
            
            # MailChimp selectors from the code
            mailchimp_selectors = [
                '.bodyContainer',
                '#templateBody', 
                '.mcnTextContent',
                '.templateContainer'
            ]
            
            for selector in mailchimp_selectors:
                try:
                    elements = soup.select(selector)
                    if elements:
                        combined_text = ""
                        for element in elements:
                            text = element.get_text(separator=' ', strip=True)
                            combined_text += text + " "
                        
                        print(f"\\n{selector}:")
                        print(f"  Elements found: {len(elements)}")
                        print(f"  Combined length: {len(combined_text)} chars")
                        print(f"  Content check: {len(combined_text) > 200}")
                        
                        if len(combined_text) > 200:
                            main_content = combined_text.strip()
                            print(f"  *** WOULD BE SELECTED ***")
                            print(f"  Preview: {main_content[:300]}...")
                            break
                        else:
                            print(f"  Preview: {combined_text[:100]}...")
                except Exception as e:
                    print(f"  ERROR: {e}")
            
            print(f"\\n=== FINAL RESULT ===")
            print(f"Main content extracted: {len(main_content)} chars")
            print(f"Would create main article: {len(main_content) >= 100}")
            
            if main_content:
                print(f"\\nContent preview:")
                print(main_content[:500])
            else:
                print("\\nNo main content extracted - this explains the empty article!")
                
        else:
            print(f"Failed to fetch: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_main_article_extraction()