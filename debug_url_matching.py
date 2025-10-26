#!/usr/bin/env python3
"""
Debug URL matching to see why it's not finding newsletter ID 38
"""
import psycopg2
import os
from urllib.parse import urlparse, urlunparse
import re

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def clean_url(url):
    parsed = urlparse(url)
    clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    return clean

def debug_url_matching():
    """Debug the URL matching logic"""
    newsletter_url = "https://apisecurity.io/issue-279-tax-records-leak-hacked-service-robots-frostbyte-at-us-stores-layer-7-api-attacks/"
    clean_newsletter_url = clean_url(newsletter_url)
    
    print(f"=== DEBUG URL MATCHING ===")
    print(f"Original URL: {newsletter_url}")
    print(f"Clean URL: {clean_newsletter_url}")
    print()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Strategy 1: Exact match (clean URL)
    print("Strategy 1: Exact match (clean URL)")
    cursor.execute("SELECT id, url FROM newsletters WHERE url = %s", (clean_newsletter_url,))
    result = cursor.fetchone()
    print(f"Result: {result}")
    print()
    
    # Strategy 2: Exact match (original URL)
    print("Strategy 2: Exact match (original URL)")
    cursor.execute("SELECT id, url FROM newsletters WHERE url = %s", (newsletter_url,))
    result = cursor.fetchone()
    print(f"Result: {result}")
    print()
    
    # Strategy 3: Fuzzy matching by extracting key parts
    print("Strategy 3: Fuzzy matching by key parts")
    url_parts = re.findall(r'issue-\\d+|[a-z0-9-]{10,}', newsletter_url.lower())
    print(f"URL parts found: {url_parts}")
    if url_parts:
        key_part = url_parts[0]
        print(f"Using key part: {key_part}")
        cursor.execute("SELECT id, url FROM newsletters WHERE url ILIKE %s", (f"%{key_part}%",))
        result = cursor.fetchone()
        print(f"Result: {result}")
    print()
    
    # Strategy 4: Domain + path matching
    print("Strategy 4: Domain + path matching")
    parsed = urlparse(newsletter_url)
    domain = parsed.netloc
    path_parts = [p for p in parsed.path.split('/') if p and len(p) > 3]
    print(f"Domain: {domain}")
    print(f"Path parts: {path_parts}")
    if path_parts:
        cursor.execute("SELECT id, url FROM newsletters WHERE url LIKE %s AND url LIKE %s", 
                     (f"%{domain}%", f"%{path_parts[-1]}%"))
        result = cursor.fetchone()
        print(f"Result: {result}")
    print()
    
    # Check all issue-279 newsletters
    print("All issue-279 newsletters:")
    cursor.execute("SELECT id, url FROM newsletters WHERE url LIKE '%issue-279%'")
    results = cursor.fetchall()
    for result in results:
        print(f"ID {result[0]}: {result[1]}")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    debug_url_matching()