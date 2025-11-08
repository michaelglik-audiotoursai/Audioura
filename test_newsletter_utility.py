#!/usr/bin/env python3
"""
Newsletter Testing Utility
Handles URL encoding and daily limit bypass for comprehensive testing
"""
import json
import urllib.parse
import requests
import logging

logging.basicConfig(level=logging.INFO)

class NewsletterTester:
    def __init__(self, base_url="http://localhost:5017"):
        self.base_url = base_url
    
    def encode_url_safely(self, url):
        """Safely encode URL for JSON transmission"""
        try:
            # Parse and re-encode to handle special characters
            parsed = urllib.parse.urlparse(url)
            
            # Encode query parameters properly
            if parsed.query:
                # Parse query string and re-encode
                query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                encoded_query = urllib.parse.urlencode(query_params)
                
                # Reconstruct URL with properly encoded query
                encoded_url = urllib.parse.urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path,
                    parsed.params, encoded_query, parsed.fragment
                ))
            else:
                encoded_url = url
            
            return encoded_url
        except Exception as e:
            logging.error(f"URL encoding failed: {e}")
            return url
    
    def create_test_payload(self, url, user_id="test_user", max_articles=5, test_mode=True):
        """Create properly formatted test payload"""
        encoded_url = self.encode_url_safely(url)
        
        payload = {
            "newsletter_url": encoded_url,
            "user_id": user_id,
            "max_articles": max_articles,
            "test_mode": test_mode  # Bypass daily limits
        }
        
        return payload
    
    def test_newsletter(self, url, user_id="test_user", max_articles=5):
        """Test newsletter processing with proper encoding and daily limit bypass"""
        print(f"=== TESTING NEWSLETTER ===")
        print(f"Original URL: {url}")
        
        # Create payload with proper encoding and test mode
        payload = self.create_test_payload(url, user_id, max_articles, test_mode=True)
        encoded_url = payload["newsletter_url"]
        
        print(f"Encoded URL: {encoded_url}")
        print(f"Test Mode: {payload['test_mode']} (bypasses daily limits)")
        
        try:
            # Send request
            response = requests.post(
                f"{self.base_url}/process_newsletter",
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=120
            )
            
            print(f"Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ SUCCESS: {result.get('articles_created', 0)} articles created")
                if 'newsletter_id' in result:
                    print(f"Newsletter ID: {result['newsletter_id']}")
                return result
            else:
                try:
                    error_data = response.json()
                    error_type = error_data.get('error_type', 'unknown')
                    message = error_data.get('message', 'Unknown error')
                    
                    if error_type == 'daily_limit_reached':
                        print(f"❌ DAILY LIMIT ERROR (should not happen in test mode): {message}")
                    else:
                        print(f"❌ ERROR ({error_type}): {message}")
                    
                    return error_data
                except:
                    print(f"❌ HTTP ERROR: {response.status_code}")
                    print(f"Response: {response.text[:200]}...")
                    return {"error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            print(f"❌ REQUEST FAILED: {e}")
            return {"error": str(e)}
    
    def test_multiple_urls(self, urls):
        """Test multiple URLs with proper handling"""
        results = {}
        
        for i, url in enumerate(urls, 1):
            print(f"\n{'='*60}")
            print(f"TEST {i}/{len(urls)}")
            print(f"{'='*60}")
            
            result = self.test_newsletter(url, f"test_user_{i}")
            results[url] = result
            
            # Brief pause between tests
            import time
            time.sleep(1)
        
        return results

def main():
    """Test problematic URLs with proper encoding and daily limit bypass"""
    tester = NewsletterTester()
    
    # Test URLs that previously had issues
    test_urls = [
        # Quora URL with special characters
        "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717",
        
        # Spotify URL for content expansion testing
        "https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3?si=e01TiIuARxqSIqVnaaaYVQ",
        
        # Working MailChimp URL
        "https://mailchi.mp/cb820171cc62/newton-has-decided-election-night-2025-results?e=f2ed12d013"
    ]
    
    print("NEWSLETTER TESTING UTILITY")
    print("=" * 60)
    print("Features:")
    print("- Proper URL encoding for special characters")
    print("- Daily limit bypass for testing")
    print("- Comprehensive error handling")
    print("=" * 60)
    
    results = tester.test_multiple_urls(test_urls)
    
    print(f"\n{'='*60}")
    print("SUMMARY RESULTS")
    print(f"{'='*60}")
    
    for url, result in results.items():
        status = "✅ SUCCESS" if result.get('status') == 'success' else "❌ FAILED"
        articles = result.get('articles_created', 0)
        print(f"{status}: {url[:50]}... ({articles} articles)")
    
    return results

if __name__ == "__main__":
    results = main()