#!/usr/bin/env python3
"""
Apple Podcasts Processor - Handles Apple Podcasts URLs by extracting RSS feeds
"""
import requests
import re
import logging
from urllib.parse import urlparse, parse_qs
import json
import xml.etree.ElementTree as ET

def extract_podcast_id_from_url(apple_url):
    """Extract podcast ID from Apple Podcasts URL"""
    # Pattern: https://podcasts.apple.com/us/podcast/name/id1234567890
    match = re.search(r'/id(\d+)', apple_url)
    if match:
        return match.group(1)
    return None

def get_rss_feed_from_itunes_api(podcast_id):
    """Get RSS feed URL from iTunes API using podcast ID"""
    try:
        api_url = f"https://itunes.apple.com/lookup?id={podcast_id}"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('results') and len(data['results']) > 0:
                return data['results'][0].get('feedUrl')
    except Exception as e:
        logging.error(f"iTunes API error: {e}")
    return None

def extract_episode_content_from_rss(rss_url, episode_id=None):
    """Extract episode content from RSS feed"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; AudioTours/1.0; +http://audiotours.com)'
        }
        response = requests.get(rss_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            # Parse XML using ElementTree
            root = ET.fromstring(response.content)
            
            # Find all episode items
            episodes = root.findall('.//item')
            
            if episode_id:
                logging.info(f"Looking for episode ID: {episode_id} in {len(episodes)} episodes")
                # Find specific episode by ID - check multiple fields
                for i, episode in enumerate(episodes):
                    # Check guid field
                    guid = episode.find('guid')
                    if guid is not None and episode_id in str(guid.text):
                        logging.info(f"Found episode by GUID at index {i}: {guid.text}")
                        return extract_episode_data(episode)
                    
                    # Check enclosure URL (common for podcast episodes)
                    enclosure = episode.find('enclosure')
                    if enclosure is not None:
                        url = enclosure.get('url', '')
                        if episode_id in url:
                            logging.info(f"Found episode by enclosure URL at index {i}: {url}")
                            return extract_episode_data(episode)
                    
                    # Check link field
                    link = episode.find('link')
                    if link is not None and episode_id in str(link.text):
                        logging.info(f"Found episode by link at index {i}: {link.text}")
                        return extract_episode_data(episode)
                
                logging.warning(f"Episode ID {episode_id} not found in RSS feed, using latest episode")
            
            # Return latest episode if no specific episode requested or not found
            if episodes:
                logging.info(f"Using latest episode (index 0) from RSS feed")
                return extract_episode_data(episodes[0])
                
    except Exception as e:
        logging.error(f"RSS parsing error: {e}")
    return None

def clean_text_for_tts(text):
    """Clean text thoroughly for TTS to avoid HTML and reduce costs"""
    import re
    
    if not text:
        return ""
    
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters that might cause TTS issues
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Limit length to 10,000 characters to control costs
    if len(text) > 10000:
        text = text[:10000] + "... Content truncated to control processing costs."
        logging.warning(f"Text truncated to 10,000 characters for cost control")
    
    return text.strip()

def extract_episode_data(episode_item):
    """Extract data from RSS episode item"""
    try:
        title = episode_item.find('title')
        title_text = title.text if title is not None else "Podcast Episode"
        
        description = episode_item.find('description')
        if description is None:
            # Try iTunes summary with namespace
            description = episode_item.find('.//{http://www.itunes.com/dtds/podcast-1.0.dtd}summary')
        
        description_text = ""
        if description is not None:
            raw_desc = description.text or ""
            description_text = clean_text_for_tts(raw_desc)
        
        # Get publication date
        pub_date = episode_item.find('pubDate')
        pub_date_text = pub_date.text if pub_date is not None else ""
        
        # Clean title as well
        clean_title = clean_text_for_tts(title_text)
        
        # Create clean content with proper title separation
        # Use a clear separator to help the orchestrator identify the title
        final_content = f"EPISODE_TITLE: {clean_title}\n\nEPISODE_DESCRIPTION: {description_text}"
        final_content = clean_text_for_tts(final_content)
        
        return {
            'title': clean_title,
            'description': description_text,
            'pub_date': pub_date_text,
            'content': final_content
        }
        
    except Exception as e:
        logging.error(f"Episode data extraction error: {e}")
        return None

def process_apple_podcasts_url(apple_url):
    """Main function to process Apple Podcasts URL and return content"""
    logging.info(f"Processing Apple Podcasts URL: {apple_url}")
    
    # Extract podcast ID
    podcast_id = extract_podcast_id_from_url(apple_url)
    if not podcast_id:
        return {"error": "Could not extract podcast ID from URL"}
    
    logging.info(f"Extracted podcast ID: {podcast_id}")
    
    # Get RSS feed URL
    rss_url = get_rss_feed_from_itunes_api(podcast_id)
    if not rss_url:
        return {"error": "Could not find RSS feed for podcast"}
    
    logging.info(f"Found RSS feed: {rss_url}")
    
    # Extract episode ID if present in URL
    episode_id = None
    if '?i=' in apple_url:
        parsed = urlparse(apple_url)
        query_params = parse_qs(parsed.query)
        if 'i' in query_params:
            episode_id = query_params['i'][0]
    
    # Get episode content
    episode_data = extract_episode_content_from_rss(rss_url, episode_id)
    if not episode_data:
        return {"error": "Could not extract episode content"}
    
    return {
        "success": True,
        "title": episode_data['title'],
        "content": episode_data['content'],
        "description": episode_data['description'],
        "pub_date": episode_data['pub_date']
    }

if __name__ == "__main__":
    # Test with the URL from the issue
    test_url = "https://podcasts.apple.com/us/podcast/magnolia-chip-joanna-gaines-from-house-flipping-to/id1150510297?i=1000731249637"
    result = process_apple_podcasts_url(test_url)
    print(json.dumps(result, indent=2))