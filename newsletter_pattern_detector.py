#!/usr/bin/env python3
"""
Newsletter Pattern Recognition Library
Detects and extracts articles from different newsletter patterns
"""
from bs4 import BeautifulSoup
import re
import logging

def detect_mailchimp_button_pattern(soup, base_url):
    """Detect MailChimp 'Read full story' button pattern"""
    articles = []
    
    # Find all button-like elements with "Read" text
    button_selectors = [
        'a[class*="mcnButton"]',
        '.mcnButtonContent a',
        'a[class*="button"]'
    ]
    
    for selector in button_selectors:
        buttons = soup.select(selector)
        for button in buttons:
            text = button.get_text(strip=True).lower()
            href = button.get('href', '')
            
            if ('read' in text and 'story' in text) and href.startswith('http'):
                # Find article summary near this button
                summary = extract_article_summary_near_button(button)
                
                articles.append({
                    'url': href,
                    'title': f"Article: {summary[:50]}..." if summary else "Newsletter Article",
                    'summary': summary,
                    'pattern': 'mailchimp_button'
                })
                logging.info(f"Found MailChimp button article: {href}")
    
    return articles

def extract_article_summary_near_button(button_element):
    """Extract article summary text near a button element"""
    # Look for text content in parent containers
    for parent in [button_element.parent, button_element.parent.parent if button_element.parent else None]:
        if not parent:
            continue
            
        # Get all text from parent, excluding the button text
        parent_text = parent.get_text(separator=' ', strip=True)
        button_text = button_element.get_text(strip=True)
        
        # Remove button text from parent text
        summary = parent_text.replace(button_text, '').strip()
        
        # Look for substantial content (more than just navigation)
        if len(summary) > 50 and not all(word in summary.lower() for word in ['read', 'more', 'story']):
            # Clean up and return first sentence or reasonable chunk
            sentences = re.split(r'[.!?]+', summary)
            if sentences and len(sentences[0]) > 20:
                return sentences[0].strip()
            elif len(summary) > 100:
                return summary[:100].strip()
    
    return ""

def detect_newsletter_patterns(soup, newsletter_url):
    """Main pattern detection function - detects all newsletter patterns"""
    all_articles = []
    
    # 1. Quora pattern (for Quora newsletters)
    if 'quora.com' in newsletter_url:
        quora_articles = detect_quora_pattern(soup, newsletter_url)
        all_articles.extend(quora_articles)
        logging.info(f"Quora pattern detected: {len(quora_articles)} articles found")
    
    # 2. MailChimp button pattern
    elif 'mailchi.mp' in newsletter_url or any(cls in str(soup) for cls in ['mcnButton', 'mcnTextContent']):
        mailchimp_articles = detect_mailchimp_button_pattern(soup, newsletter_url)
        all_articles.extend(mailchimp_articles)
        logging.info(f"MailChimp pattern detected: {len(mailchimp_articles)} button articles found")
    
    # 3. Generic "Read more" pattern (for other newsletters)
    else:
        generic_articles = detect_generic_read_more_pattern(soup, newsletter_url)
        all_articles.extend(generic_articles)
    
    # 4. Podcast pattern (always check for all newsletters)
    podcast_articles = detect_podcast_pattern(soup, newsletter_url)
    all_articles.extend(podcast_articles)
    
    return all_articles

def detect_generic_read_more_pattern(soup, base_url):
    """Detect generic 'Read more' patterns in any newsletter"""
    articles = []
    
    # Look for links with "read more" type text
    read_more_patterns = [
        r'read\s+more',
        r'continue\s+reading', 
        r'full\s+article',
        r'read\s+full',
        r'view\s+more'
    ]
    
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        text = link.get_text(strip=True).lower()
        href = link.get('href', '')
        
        if any(re.search(pattern, text) for pattern in read_more_patterns) and href.startswith('http'):
            summary = extract_article_summary_near_button(link)
            
            articles.append({
                'url': href,
                'title': f"Article: {summary[:50]}..." if summary else "Newsletter Article", 
                'summary': summary,
                'pattern': 'generic_read_more'
            })
            logging.info(f"Found generic read-more article: {href}")
    
    return articles

def detect_quora_pattern(soup, base_url):
    """Detect Quora article links from newsletter content"""
    articles = []
    
    # Quora articles are typically links to individual questions/answers
    all_links = soup.find_all('a', href=True)
    logging.info(f"Quora pattern: Found {len(all_links)} total links to analyze")
    
    for link in all_links:
        href = link.get('href', '')
        link_text = link.get_text(strip=True)
        
        # Log first few links for debugging
        if len(articles) < 5:
            logging.info(f"Analyzing link: '{link_text[:50]}...' -> {href[:80]}...")
        
        # Quora article URLs - broader pattern matching
        if ('quora.com' in href and 
            len(link_text) > 15 and  # Reduced minimum length
            not any(skip in href.lower() for skip in ['/search', '/login', '/signup', '/settings', '/notifications']) and
            not any(skip in link_text.lower() for skip in ['follow', 'sign up', 'log in', 'search', 'profile'])):
            
            # Use link text as title (it's usually the question/article title)
            title = link_text[:100]  # Limit title length
            
            articles.append({
                'url': href,
                'title': title,
                'summary': link_text,
                'pattern': 'quora_article'
            })
            logging.info(f"Found Quora article: {title[:50]}... -> {href}")
    
    logging.info(f"Quora pattern detection complete: {len(articles)} articles found")
    return articles

def detect_podcast_pattern(soup, base_url):
    """Detect podcast links (Spotify, Apple Podcasts)"""
    articles = []
    
    all_links = soup.find_all('a', href=True)
    for link in all_links:
        href = link.get('href', '')
        
        # Podcast URLs
        if ('podcasts.apple.com' in href and '?i=' in href) or 'open.spotify.com/episode' in href:
            articles.append({
                'url': href,
                'title': 'Podcast Episode',
                'summary': '',
                'pattern': 'podcast'
            })
            logging.info(f"Found podcast article: {href}")
    
    return articles