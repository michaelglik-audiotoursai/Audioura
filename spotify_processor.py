#!/usr/bin/env python3
"""
Spotify Processor - Handles Spotify URLs by extracting episode content
"""
import requests
import re
import logging
from urllib.parse import urlparse
import json

def extract_episode_id_from_spotify_url(spotify_url):
    """Extract episode ID from Spotify URL"""
    # Pattern: https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y
    match = re.search(r'/episode/([a-zA-Z0-9]+)', spotify_url)
    if match:
        return match.group(1)
    return None

def get_spotify_episode_content(episode_id):
    """Get episode content from Spotify Web API or web scraping"""
    try:
        # Try web scraping approach since Spotify Web API requires authentication
        episode_url = f"https://open.spotify.com/episode/{episode_id}"
        
        # Enhanced headers to mimic real browser behavior
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
        response = requests.get(episode_url, headers=headers, timeout=10, allow_redirects=True)
        
        logging.info(f"Spotify response status: {response.status_code}, final URL: {response.url}")
        
        if response.status_code == 200:
            # Extract content from HTML
            content = response.text
            
            # Try to extract episode title and description from HTML
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', content)
            title = title_match.group(1) if title_match else "Spotify Episode"
            
            # Enhanced description extraction patterns
            desc_patterns = [
                r'<meta name="description" content="([^"]+)"',
                r'<meta property="og:description" content="([^"]+)"',
                r'<meta property="twitter:description" content="([^"]+)"',
                r'"description":"([^"]+)"',
                r'"summary":"([^"]+)"',
                r'data-testid="episode-description"[^>]*>([^<]+)<',
                r'class="[^"]*description[^"]*"[^>]*>([^<]+)<'
            ]
            
            description = ""
            for pattern in desc_patterns:
                desc_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if desc_match:
                    description = desc_match.group(1).strip()
                    # Clean up common prefixes
                    description = description.replace('Listen to this episode from How I Built This with Guy Raz | Wondery+ on Spotify. ', '')
                    if len(description) > 50:  # Only use if substantial content
                        break
            
            # Clean HTML entities
            import html
            title = html.unescape(title)
            description = html.unescape(description)
            
            # Clean title and description
            clean_title = title.replace(' | Podcast on Spotify', '').replace(' - Spotify', '').strip()
            clean_description = description.strip()
            
            # Log what we extracted
            logging.info(f"Extracted title: '{clean_title}' ({len(clean_title)} chars)")
            logging.info(f"Extracted description: '{clean_description[:100]}...' ({len(clean_description)} chars)")
            
            # Format content with clear title separation like Apple Podcasts processor
            formatted_content = f"EPISODE_TITLE: {clean_title}\n\nEPISODE_DESCRIPTION: {clean_description}"
            
            return {
                'title': clean_title,
                'description': clean_description,
                'content': formatted_content
            }
            
        else:
            logging.error(f"Spotify request failed with status {response.status_code}")
                
    except Exception as e:
        logging.error(f"Spotify episode extraction error: {e}")
    
    return None

def process_spotify_url(spotify_url):
    """Main function to process Spotify URL and return content"""
    logging.info(f"Processing Spotify URL: {spotify_url}")
    
    # Extract episode ID
    episode_id = extract_episode_id_from_spotify_url(spotify_url)
    if not episode_id:
        return {"error": "Could not extract episode ID from Spotify URL"}
    
    logging.info(f"Extracted Spotify episode ID: {episode_id}")
    
    # Try regular scraping first
    episode_data = get_spotify_episode_content(episode_id)
    
    # If regular scraping fails or returns insufficient content, try browser automation
    if not episode_data or len(episode_data.get('content', '')) < 100:
        logging.info("Regular scraping failed, trying browser automation...")
        try:
            from browser_automation import extract_spotify_with_browser
            browser_result = extract_spotify_with_browser(spotify_url)
            
            if browser_result.get('success') and len(browser_result.get('content', '')) >= 100:
                logging.info(f"Browser automation SUCCESS: {len(browser_result['content'])} chars")
                return browser_result
            else:
                logging.warning(f"Browser automation also failed: {browser_result.get('error', 'Insufficient content')}")
        except Exception as e:
            logging.error(f"Browser automation error: {e}")
    
    # Return regular scraping result (even if insufficient)
    if episode_data:
        return {
            "success": True,
            "title": episode_data['title'],
            "content": episode_data['content'],
            "description": episode_data['description']
        }
    
    return {"error": "Could not extract episode content from Spotify"}

if __name__ == "__main__":
    # Test with the URL from the issue
    test_url = "https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y?si=0L4hS4wHRLWdVdJFcAkVbA"
    result = process_spotify_url(test_url)
    print(json.dumps(result, indent=2))
    
    # Clean up browser if used
    try:
        from browser_automation import _browser
        if _browser:
            _browser.close()
    except:
        pass