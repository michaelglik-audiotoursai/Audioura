#!/usr/bin/env python3
"""
Newsletter Processing Utilities
Extracted from newsletter_processor_service.py for better testability
"""

import psycopg2
import logging
import re
from urllib.parse import urlparse, parse_qs

def get_db_connection():
    """Get database connection with error handling"""
    try:
        return psycopg2.connect(
            host="development-postgres-2-1",
            port=5432,
            database="audiotours",
            user="admin",
            password="password"
        )
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

def clean_url(url):
    """Clean and normalize URL for processing"""
    if not url:
        return ""
    
    # Remove tracking parameters
    url = re.sub(r'[?&]utm_[^&]*', '', url)
    url = re.sub(r'[?&]et_rid=[^&]*', '', url)
    url = re.sub(r'[?&]s_campaign=[^&]*', '', url)
    
    # Clean up multiple ? or &
    url = re.sub(r'\?&', '?', url)
    url = re.sub(r'&+', '&', url)
    url = url.rstrip('?&')
    
    return url.strip()

def extract_all_clickable_urls(html_content):
    """Extract all clickable URLs from HTML content"""
    urls = []
    
    # Extract href attributes
    href_pattern = r'href=["\']([^"\']+)["\']'
    hrefs = re.findall(href_pattern, html_content, re.IGNORECASE)
    urls.extend(hrefs)
    
    # Extract onclick URLs
    onclick_pattern = r'onclick=["\'][^"\']*(?:window\.open|location\.href)[^"\']*["\']([^"\']+)["\']'
    onclick_urls = re.findall(onclick_pattern, html_content, re.IGNORECASE)
    urls.extend(onclick_urls)
    
    # Clean and filter URLs
    cleaned_urls = []
    for url in urls:
        cleaned = clean_url(url)
        if cleaned and cleaned.startswith('http'):
            cleaned_urls.append(cleaned)
    
    return list(set(cleaned_urls))  # Remove duplicates

def health_check():
    """Health check for newsletter processing utilities"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return {"status": "healthy", "database": "connected"}
        else:
            return {"status": "unhealthy", "database": "disconnected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def validate_content_length(content, min_length=100):
    """Validate content meets minimum length requirements"""
    if not content:
        return False, "No content provided"
    
    content_length = len(content.strip())
    if content_length < min_length:
        return False, f"Content too short: {content_length} chars (min: {min_length})"
    
    return True, f"Content valid: {content_length} chars"

def detect_newsletter_platform(url, html_content=""):
    """Detect newsletter platform for specialized processing"""
    url_lower = url.lower()
    html_lower = html_content.lower()
    
    if 'substack.com' in url_lower:
        return 'substack'
    elif 'mailchi.mp' in url_lower or 'mailchimp' in html_lower:
        return 'mailchimp'
    elif 'quora.com' in url_lower:
        return 'quora'
    elif 'bostonglobe.com' in url_lower:
        return 'bostonglobe'
    elif 'spotify.com' in url_lower:
        return 'spotify'
    elif 'podcasts.apple.com' in url_lower:
        return 'apple_podcasts'
    else:
        return 'generic'