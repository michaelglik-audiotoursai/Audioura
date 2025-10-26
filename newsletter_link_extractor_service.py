import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

SERVICE_VERSION = "1.2.2.82"

class NewsletterLinkExtractor:
    def __init__(self):
        self.visited_urls = set()
        self.max_depth = 2  # Prevent circular dependency
    
    def extract_newsletter_links(self, newsletter_text, user_id):
        """Extract meaningful article links from newsletter"""
        # Extract all links
        all_links = self.extract_links(newsletter_text)
        
        # Filter for article links
        article_links = self.filter_article_links(all_links)
        
        # Check for multi-level links (links that lead to more links)
        expanded_links = self.expand_link_pages(article_links)
        
        # Return links for mobile app to process
        return {
            "user_id": user_id,
            "newsletter_source": self.extract_newsletter_source(newsletter_text),
            "article_links": expanded_links,
            "total_found": len(expanded_links)
        }
    
    def extract_links(self, text):
        """Aggressively extract all possible URLs from newsletter text"""
        links = []
        
        # Extract from HTML href attributes (if any HTML remains)
        html_links = re.findall(r'href=["\']([^"\'>]+)["\']', text, re.IGNORECASE)
        links.extend(html_links)
        
        # Extract plain URLs (most common after copy/paste)
        url_patterns = [
            r'http[s]?://[^\s<>"\[\]{}|\\^`]+',  # Standard URLs
            r'www\.[^\s<>"\[\]{}|\\^`]+',        # www URLs
            r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[^\s<>"\[\]{}|\\^`]*'  # domain.com/path
        ]
        
        for pattern in url_patterns:
            found_urls = re.findall(pattern, text, re.IGNORECASE)
            links.extend(found_urls)
        
        # Look for domain patterns in text (even without http)
        domain_pattern = r'\b([a-zA-Z0-9.-]+\.(com|org|net|edu|gov|co\.uk|ca|au)\b[^\s]*?)'
        domains = re.findall(domain_pattern, text, re.IGNORECASE)
        for domain, tld in domains:
            full_domain = domain
            if not full_domain.startswith('http'):
                full_domain = 'https://' + full_domain
            links.append(full_domain)
        
        # Clean and deduplicate
        clean_links = []
        for link in links:
            # Ensure it starts with http
            if not link.startswith('http'):
                if link.startswith('www.'):
                    link = 'https://' + link
                elif '.' in link:
                    link = 'https://' + link
            
            if link.startswith('http') and len(link) > 10:
                clean_links.append(link)
        
        return list(set(clean_links))
    
    def filter_article_links(self, links):
        """Filter out ads, menus, social media links"""
        exclude_patterns = [
            r'unsubscribe', r'privacy', r'terms', r'contact', r'subscribe',
            r'facebook\.com', r'twitter\.com', r'instagram\.com', r'linkedin\.com',
            r'youtube\.com', r'advertisement', r'ads\.', r'doubleclick',
            r'googleads', r'\.jpg$', r'\.png$', r'\.gif$', r'mailto:', r'tel:',
            r'/search\?', r'/category/', r'/tag/', r'/author/', r'#comment',
            r'/login', r'/register', r'/signup', r'/cart', r'/checkout'
        ]
        
        article_links = []
        for link in links:
            if not any(re.search(pattern, link, re.IGNORECASE) for pattern in exclude_patterns):
                if self.is_likely_article(link):
                    article_links.append(link)
        
        return article_links
    
    def is_likely_article(self, url):
        """Check if URL likely points to an article"""
        article_indicators = [
            r'/article/', r'/story/', r'/news/', r'/\d{4}/\d{2}/\d{2}/',
            r'-\d+\.html$', r'\.html$', r'/post/', r'/blog/', r'/press-release/',
            r'/report/', r'/analysis/', r'/opinion/', r'/editorial/'
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in article_indicators)
    
    def expand_link_pages(self, links, depth=0):
        """Check if links lead to pages with more article links"""
        if depth >= self.max_depth:
            return links
        
        expanded_links = []
        
        for link in links:
            if link in self.visited_urls:
                continue
                
            self.visited_urls.add(link)
            
            try:
                # Check if this is a direct article or a link page
                if self.is_direct_article(link):
                    expanded_links.append(link)
                else:
                    # This might be a link page, extract more links
                    sub_links = self.extract_links_from_page(link)
                    if sub_links:
                        # Recursively expand (with depth limit)
                        expanded_links.extend(
                            self.expand_link_pages(sub_links, depth + 1)
                        )
                    else:
                        # No sub-links found, treat as article
                        expanded_links.append(link)
                        
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error processing {link}: {e}")
                expanded_links.append(link)  # Include anyway
        
        return list(set(expanded_links))  # Remove duplicates
    
    def is_direct_article(self, url):
        """Quick check if URL is likely a direct article"""
        try:
            response = requests.head(url, timeout=5)
            content_type = response.headers.get('content-type', '')
            
            # If it's HTML and has article indicators, likely direct article
            if 'text/html' in content_type:
                return any(indicator in url.lower() for indicator in 
                          ['article', 'story', 'news', 'post', 'blog'])
            
            return False
        except:
            return True  # Assume it's an article if we can't check
    
    def extract_links_from_page(self, url):
        """Extract article links from a page that might contain multiple links"""
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for article links in the page
            page_links = []
            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href'])
                if self.is_likely_article(full_url):
                    page_links.append(full_url)
            
            return self.filter_article_links(page_links)
            
        except Exception as e:
            print(f"Error extracting links from {url}: {e}")
            return []
    
    def extract_newsletter_source(self, newsletter_text):
        """Extract newsletter source from text"""
        lines = newsletter_text.split('\n')[:10]
        for line in lines:
            if any(keyword in line.lower() for keyword in ['from:', 'sender:', 'newsletter:']):
                return line.strip()
            if '@' in line and len(line.split()) < 5:
                return line.strip()
        
        return "Unknown Newsletter"

if __name__ == "__main__":
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    extractor = NewsletterLinkExtractor()
    
    @app.route('/extract_newsletter_links', methods=['POST'])
    def extract_newsletter_links():
        data = request.json
        result = extractor.extract_newsletter_links(
            data['newsletter_text'], 
            data['user_id']
        )
        return jsonify(result)
    
    app.run(host='0.0.0.0', port=5014)