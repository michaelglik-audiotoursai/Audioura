#!/usr/bin/env python3
"""
URL Encoding Helper for Testing
Handles special characters in URLs for proper JSON formatting
"""
import urllib.parse
import json

def encode_url_for_json(url):
    """Encode URL to handle special characters in JSON"""
    # Parse URL to handle special characters properly
    parsed = urllib.parse.urlparse(url)
    
    # Encode query parameters properly
    if parsed.query:
        query_params = urllib.parse.parse_qs(parsed.query)
        encoded_query = urllib.parse.urlencode(query_params, doseq=True)
        encoded_url = urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, encoded_query, parsed.fragment
        ))
    else:
        encoded_url = url
    
    return encoded_url

def create_test_payload(url, user_id="test_user", max_articles=5):
    """Create properly formatted JSON payload for testing"""
    encoded_url = encode_url_for_json(url)
    
    payload = {
        "newsletter_url": encoded_url,
        "user_id": user_id,
        "max_articles": max_articles
    }
    
    return json.dumps(payload, indent=2)

if __name__ == "__main__":
    # Test problematic Quora URL
    quora_url = "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717"
    
    print("Original URL:", quora_url)
    print("Encoded URL:", encode_url_for_json(quora_url))
    print("\nJSON Payload:")
    print(create_test_payload(quora_url, "test_user_quora"))