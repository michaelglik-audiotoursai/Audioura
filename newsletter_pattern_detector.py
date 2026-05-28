#!/usr/bin/env python3
"""
Newsletter Pattern Recognition Library
Detects and extracts articles from different newsletter patterns
"""
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
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

def detect_email_newsletter_pattern(soup, base_url):
    """Detect generic email newsletter patterns with Read Now buttons and clickable titles"""
    articles = []
    
    # Look for email newsletter structures (table-based layouts)
    email_containers = soup.find_all(['table', 'div'], attrs={
        'role': 'presentation',
        'class': lambda x: x and any(term in x.lower() for term in ['email', 'newsletter', 'content', 'article'])
    }) or soup.find_all(['td', 'div'], class_=lambda x: x and 'content' in x.lower())
    
    if not email_containers:
        # Fallback: look for any table-based structure
        email_containers = soup.find_all('table')
    
    for container in email_containers:
        # Find "Read Now" / "Read More" buttons and clickable titles
        read_buttons = container.find_all('a', string=lambda text: text and any(
            phrase in text.lower() for phrase in ['read now', 'read more', 'continue reading', 'full story', 'read full']
        ))
        
        # Also look for buttons with these patterns in href or nearby text
        if not read_buttons:
            read_buttons = container.find_all('a', href=True)
            read_buttons = [btn for btn in read_buttons if btn.get_text(strip=True) and any(
                phrase in btn.get_text(strip=True).lower() for phrase in ['read', 'more', 'continue', 'full']
            )]
        
        for button in read_buttons:
            href = button.get('href', '')
            if not href.startswith('http'):
                continue
                
            # Find associated article content near this button
            article_info = extract_article_info_near_element(button)
            
            if article_info['title'] and len(article_info['title']) > 10:
                articles.append({
                    'url': href,
                    'title': article_info['title'],
                    'summary': article_info['summary'],
                    'pattern': 'email_newsletter_button'
                })
                logging.info(f"Found email newsletter article: {article_info['title'][:50]}... -> {href}")
    
    # Also look for clickable headlines (common in email newsletters)
    clickable_headlines = soup.find_all('a', href=True)
    for headline in clickable_headlines:
        href = headline.get('href', '')
        if not href.startswith('http'):
            continue
            
        headline_text = headline.get_text(strip=True)
        
        # Skip if it's clearly navigation, social media, or subscription links
        if any(skip in href.lower() for skip in [
            'unsubscribe', 'manage', 'preferences', 'facebook.com', 'twitter.com', 
            'linkedin.com', 'instagram.com', 'subscribe', 'signup'
        ]):
            continue
            
        # Look for substantial headlines (likely article titles)
        if (len(headline_text) > 20 and len(headline_text) < 200 and 
            not any(skip in headline_text.lower() for skip in [
                'click here', 'read more', 'subscribe', 'follow us', 'unsubscribe'
            ])):
            
            # Check if this looks like a news headline
            if any(indicator in headline_text.lower() for indicator in [
                'trump', 'biden', 'congress', 'senate', 'house', 'president', 'governor',
                'election', 'vote', 'poll', 'campaign', 'political', 'government',
                'economy', 'market', 'stock', 'business', 'company', 'ceo',
                'health', 'medical', 'hospital', 'doctor', 'patient',
                'school', 'student', 'teacher', 'education', 'university',
                'police', 'court', 'judge', 'trial', 'lawsuit', 'crime'
            ]) or len(headline_text.split()) >= 5:  # Or substantial multi-word headlines
                
                # Get summary from nearby content
                summary = extract_summary_near_element(headline)
                
                articles.append({
                    'url': href,
                    'title': headline_text,
                    'summary': summary,
                    'pattern': 'email_newsletter_headline'
                })
                logging.info(f"Found clickable headline: {headline_text[:50]}... -> {href}")
    
    return articles

def extract_article_info_near_element(element):
    """Extract article title and summary from content near a button/link element"""
    title = ""
    summary = ""
    
    # Look in parent containers for article content
    for parent in [element.parent, element.parent.parent if element.parent else None]:
        if not parent:
            continue
            
        # Find potential titles (headings, strong text, larger text)
        title_elements = parent.find_all(['h1', 'h2', 'h3', 'h4', 'strong', 'b']) + \
                        parent.find_all('a', href=True)
        
        for title_elem in title_elements:
            if title_elem == element:  # Skip the button itself
                continue
                
            title_text = title_elem.get_text(strip=True)
            if len(title_text) > 10 and len(title_text) < 200:
                title = title_text
                break
        
        # Find summary text (paragraphs, divs with substantial content)
        text_elements = parent.find_all(['p', 'div', 'span'])
        summary_parts = []
        
        for text_elem in text_elements:
            text = text_elem.get_text(strip=True)
            if (len(text) > 30 and len(text) < 500 and 
                text != title and 
                not any(skip in text.lower() for skip in ['read more', 'click here', 'unsubscribe'])):
                summary_parts.append(text)
                if len(' '.join(summary_parts)) > 200:
                    break
        
        if summary_parts:
            summary = ' '.join(summary_parts)[:300]  # Limit summary length
            break
    
    return {'title': title, 'summary': summary}

def extract_summary_near_element(element):
    """Extract summary text near a headline element"""
    summary = ""
    
    # Look for summary in siblings or parent content
    parent = element.parent
    if parent:
        # Get all text from parent, excluding the headline
        parent_text = parent.get_text(separator=' ', strip=True)
        headline_text = element.get_text(strip=True)
        
        # Remove headline from parent text to get summary
        if headline_text in parent_text:
            summary = parent_text.replace(headline_text, '').strip()
            # Take first sentence or reasonable chunk
            if len(summary) > 100:
                sentences = summary.split('. ')
                if sentences and len(sentences[0]) > 30:
                    summary = sentences[0] + '.'
                else:
                    summary = summary[:150] + '...'
    
    return summary

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
    
    # 3. Email newsletter pattern (generic - for Boston Globe, NY Times, etc.)
    elif any(indicator in newsletter_url for indicator in ['view.email.', 'email.', 'newsletter.', 'messaging-custom-newsletters']):
        email_articles = detect_email_newsletter_pattern(soup, newsletter_url)
        all_articles.extend(email_articles)
        logging.info(f"Email newsletter pattern detected: {len(email_articles)} articles found")
    
    # 4. Generic "Read more" pattern (fallback for other newsletters)
    else:
        generic_articles = detect_generic_read_more_pattern(soup, newsletter_url)
        all_articles.extend(generic_articles)
    
    # 5. Podcast pattern (always check for all newsletters)
    podcast_articles = detect_podcast_pattern(soup, newsletter_url)
    all_articles.extend(podcast_articles)
    
    return all_articles

def detect_generic_read_more_pattern(soup, base_url):
    """Detect generic 'Read more' patterns and blog/newsletter homepage article listings"""
    articles = []
    
    # --- Pattern A: Links with "read more" type text ---
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
    
    # --- Pattern B: Blog/newsletter homepage with same-domain article links ---
    # Detects pages that list multiple articles as linked cards (Ghost, WordPress, etc.)
    if not articles:
        blog_articles = detect_blog_homepage_pattern(soup, base_url)
        articles.extend(blog_articles)
    
    return articles

def detect_blog_homepage_pattern(soup, base_url):
    """
    Detect blog/newsletter homepage pattern where the page lists multiple articles
    from the same domain as linked cards with titles and summaries.
    Common on Ghost, WordPress, Substack archive pages, and similar platforms.
    """
    articles = []
    
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.replace('www.', '')
    
    # Collect all links that point to the same domain (internal article links)
    all_links = soup.find_all('a', href=True)
    candidate_articles = []
    
    # Navigation/utility paths to skip
    skip_paths = [
        '/page/', '/tag/', '/author/', '/category/', '/about', '/contact',
        '/subscribe', '/login', '/signup', '/account', '/search', '/privacy',
        '/terms', '/rss', '/feed', '/sitemap', '/#', '/cdn-cgi/'
    ]
    
    for link in all_links:
        href = link.get('href', '')
        
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed_href = urlparse(full_url)
        link_domain = parsed_href.netloc.replace('www.', '')
        
        # Must be same domain
        if link_domain != base_domain:
            continue
        
        # Must have a meaningful path (not just the homepage)
        path = parsed_href.path.rstrip('/')
        if not path or path == '':
            continue
        
        # Skip navigation/utility pages
        if any(skip in path.lower() for skip in skip_paths):
            continue
        
        # Get the link text content (title + possibly summary)
        link_text = link.get_text(separator=' ', strip=True)
        
        # Must have substantial text (article title + possibly summary)
        # A real article card typically has at least a multi-word title
        if len(link_text) < 20:
            continue
        
        # Skip if text looks like navigation
        if link_text.lower() in ['home', 'about', 'contact', 'subscribe', 'sign in', 'see all']:
            continue
        
        # Extract title: first sentence or line, typically the headline
        # Many blog cards have format: "Title Summary text By Author —Date"
        title = ''
        summary = ''
        
        # Try to split title from summary
        # Common patterns: title is in a child heading element
        heading = link.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if heading:
            title = heading.get_text(strip=True)
            # Summary is the remaining text
            summary = link_text.replace(title, '').strip()
        else:
            # No heading — try splitting on "By " (author attribution) or date patterns
            by_split = re.split(r'\s+By\s+(?=[A-Z])', link_text, maxsplit=1)
            if len(by_split) == 2 and len(by_split[0]) > 15:
                # Everything before "By Author" is title+summary
                content_part = by_split[0]
            else:
                content_part = link_text
            
            # Try to separate title from summary by looking for sentence boundaries
            # Title is usually the first sentence/phrase
            sentences = re.split(r'(?<=[.!?])\s+', content_part, maxsplit=1)
            if len(sentences) >= 2 and len(sentences[0]) >= 15:
                title = sentences[0]
                summary = sentences[1][:200]
            else:
                # Use first ~80 chars as title
                if len(content_part) > 80:
                    # Try to break at a word boundary
                    space_idx = content_part.rfind(' ', 0, 80)
                    if space_idx > 30:
                        title = content_part[:space_idx]
                        summary = content_part[space_idx:].strip()[:200]
                    else:
                        title = content_part[:80]
                        summary = content_part[80:].strip()[:200]
                else:
                    title = content_part
        
        # Clean up title
        title = title.strip()
        if not title or len(title) < 10:
            continue
        
        # Remove date patterns from end of title (e.g., "—28 May 2026")
        title = re.sub(r'\s*[—–-]\s*\d{1,2}\s+\w+\s+\d{4}\s*$', '', title).strip()
        
        candidate_articles.append({
            'url': full_url,
            'title': title,
            'summary': summary.strip(),
            'text_length': len(link_text),
            'path': path
        })
    
    # Deduplicate by URL path
    seen_paths = set()
    unique_candidates = []
    for candidate in candidate_articles:
        if candidate['path'] not in seen_paths:
            seen_paths.add(candidate['path'])
            unique_candidates.append(candidate)
    
    # Sanity cap to prevent pathological pages from emitting hundreds of candidates
    unique_candidates = unique_candidates[:30]
    
    # Only treat as a blog homepage if we found multiple same-domain article links
    # (a single link could just be a self-reference; 3+ suggests a listing page)
    if len(unique_candidates) >= 3:
        logging.info(f"Blog homepage pattern detected: {len(unique_candidates)} same-domain article links found on {base_domain}")
        for candidate in unique_candidates:
            articles.append({
                'url': candidate['url'],
                'title': candidate['title'],
                'summary': candidate['summary'],
                'pattern': 'blog_homepage'
            })
            logging.info(f"Found blog article: '{candidate['title'][:60]}...' -> {candidate['url']}")
    else:
        logging.info(f"Blog homepage pattern: Only {len(unique_candidates)} same-domain links found (need 3+), skipping")
    
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