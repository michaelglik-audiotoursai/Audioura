#!/usr/bin/env python3
"""
Analyze MailChimp newsletter HTML structure to identify article patterns
"""
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

def analyze_mailchimp_pattern():
    """Analyze the MailChimp newsletter to understand article extraction patterns"""
    
    # Read the downloaded HTML
    with open('mailchimp_newsletter.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    print("=== MAILCHIMP NEWSLETTER PATTERN ANALYSIS ===\n")
    
    # 1. Find all links
    all_links = soup.find_all('a', href=True)
    print(f"Total links found: {len(all_links)}")
    
    # 2. Categorize links
    external_links = []
    newtonbeacon_links = []
    other_news_links = []
    
    for link in all_links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        if 'newtonbeacon.org' in href:
            newtonbeacon_links.append({
                'url': href,
                'text': text,
                'parent': str(link.parent)[:200] if link.parent else 'No parent'
            })
        elif any(domain in href for domain in ['bostonglobe.com', 'boston.com', 'wbur.org']):
            other_news_links.append({
                'url': href,
                'text': text,
                'parent': str(link.parent)[:200] if link.parent else 'No parent'
            })
        elif href.startswith('http') and not any(skip in href for skip in [
            'mailchi.mp', 'mailchimp.com', 'facebook.com', 'twitter.com', 
            'instagram.com', 'unsubscribe', 'campaign-archive.com'
        ]):
            external_links.append({
                'url': href,
                'text': text,
                'parent': str(link.parent)[:200] if link.parent else 'No parent'
            })
    
    print(f"\n=== NEWTON BEACON LINKS ({len(newtonbeacon_links)}) ===")
    for i, link in enumerate(newtonbeacon_links, 1):
        print(f"{i}. URL: {link['url']}")
        print(f"   Text: '{link['text']}'")
        print(f"   Parent: {link['parent']}")
        print()
    
    print(f"\n=== OTHER NEWS LINKS ({len(other_news_links)}) ===")
    for i, link in enumerate(other_news_links, 1):
        print(f"{i}. URL: {link['url']}")
        print(f"   Text: '{link['text']}'")
        print(f"   Parent: {link['parent']}")
        print()
    
    print(f"\n=== EXTERNAL LINKS ({len(external_links)}) ===")
    for i, link in enumerate(external_links, 1):
        print(f"{i}. URL: {link['url']}")
        print(f"   Text: '{link['text']}'")
        print(f"   Parent: {link['parent']}")
        print()
    
    # 3. Look for repeating patterns
    print("\n=== PATTERN ANALYSIS ===")
    
    # Find elements with "Read" text
    read_elements = soup.find_all(text=re.compile(r'read', re.IGNORECASE))
    print(f"Elements containing 'read': {len(read_elements)}")
    
    for i, element in enumerate(read_elements[:5], 1):
        parent = element.parent if hasattr(element, 'parent') else None
        print(f"{i}. Text: '{element.strip()}'")
        if parent:
            print(f"   Parent tag: {parent.name}")
            print(f"   Parent text: '{parent.get_text(strip=True)[:100]}'")
        print()
    
    # 4. Look for table structures (common in MailChimp)
    tables = soup.find_all('table')
    print(f"\nTable structures found: {len(tables)}")
    
    # 5. Look for specific MailChimp classes
    mailchimp_classes = [
        'mcnTextContent', 'bodyContainer', 'templateContainer', 
        'mcnButtonContent', 'mcnTextBlock', 'mcnDividerBlock'
    ]
    
    for class_name in mailchimp_classes:
        elements = soup.find_all(class_=class_name)
        if elements:
            print(f"\nFound {len(elements)} elements with class '{class_name}'")
            for i, elem in enumerate(elements[:2], 1):
                text = elem.get_text(strip=True)[:200]
                print(f"  {i}. {text}...")
    
    # 6. Look for button-like elements
    buttons = soup.find_all(['button', 'input'])
    button_links = soup.find_all('a', class_=re.compile(r'button|btn', re.IGNORECASE))
    
    print(f"\nButton elements: {len(buttons)}")
    print(f"Button-like links: {len(button_links)}")
    
    for button in button_links[:3]:
        print(f"Button link: '{button.get_text(strip=True)}' -> {button.get('href', 'No href')}")

if __name__ == '__main__':
    analyze_mailchimp_pattern()