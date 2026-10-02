#!/usr/bin/env python3
"""
Test Multiple Spotify URLs to identify patterns
"""
import sys
import os

import pytest
pytest.importorskip("selenium")  # LOCAL-544: skip when optional dep missing

sys.path.append('/app')

from browser_automation import get_browser
import time

def test_spotify_url(url, description):
    """Test a single Spotify URL and return key indicators"""
    browser = get_browser()
    
    try:
        print(f"\n🔍 Testing: {description}")
        print(f"URL: {url}")
        
        browser.driver.get(url)
        time.sleep(3)
        
        title = browser.driver.title
        current_url = browser.driver.current_url
        page_source = browser.driver.page_source
        
        # Check key indicators
        indicators = {
            "couldn't_find": "Couldn't find that podcast" in page_source,
            "sign_up": "Sign up to get unlimited" in page_source,
            "episode_title": "episode-title" in page_source,
            "episode_description": "episode-description" in page_source,
            "redirected": current_url != url
        }
        
        print(f"  Title: {title}")
        print(f"  Page Length: {len(page_source)} chars")
        print(f"  Redirected: {indicators['redirected']}")
        episode_title = indicators['episode_title']
        episode_description = indicators['episode_description']
        not_found = indicators["couldn't_find"]
        sign_up = indicators['sign_up']
        print(f"  Content Found: Episode={episode_title}, Description={episode_description}")
        print(f"  Error Messages: NotFound={not_found}, SignUp={sign_up}")
        
        return indicators
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

def main():
    print("🧪 Testing Multiple Spotify URLs")
    print("=" * 60)
    
    # Test different types of Spotify URLs
    test_urls = [
        ("https://open.spotify.com/episode/4VqMqcy0wPAECv9M1s3kGy", "Guy Raz Episode (Original)"),
        ("https://open.spotify.com/show/6E709HRH7XaiZrMfgtNCun", "How I Built This Show Page"),
        ("https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y", "Different Episode ID"),
        ("https://open.spotify.com/", "Spotify Home Page")
    ]
    
    results = []
    for url, description in test_urls:
        result = test_spotify_url(url, description)
        results.append((description, result))
    
    print("\n" + "=" * 60)
    print("📊 SUMMARY:")
    for description, result in results:
        if result:
            status = "✅ Episode Content" if result['episode_title'] else "❌ No Episode Content"
            print(f"{description}: {status}")
        else:
            print(f"{description}: ❌ Error")
    
    print("\n💡 ANALYSIS:")
    print("If all episode URLs show 'Couldn't find that podcast', this suggests:")
    print("1. Spotify requires authentication for episode content")
    print("2. Episodes may be region-restricted")
    print("3. Browser automation is detected and blocked")

if __name__ == "__main__":
    main()