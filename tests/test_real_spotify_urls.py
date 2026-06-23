#!/usr/bin/env python3
"""
Test Real Spotify URLs from Guy Raz Newsletter
"""
import sys
import os
sys.path.append('/app')

from browser_automation import get_browser
from selenium.webdriver.common.by import By
import time

def test_real_spotify_url(url):
    """Test actual Spotify URL from the newsletter"""
    browser = get_browser()
    
    try:
        print(f"🔍 Testing REAL Spotify URL from newsletter:")
        print(f"URL: {url}")
        print("-" * 60)
        
        browser.driver.get(url)
        time.sleep(5)
        
        title = browser.driver.title
        current_url = browser.driver.current_url
        page_source = browser.driver.page_source
        
        print(f"📄 Page Title: {title}")
        print(f"🔗 Final URL: {current_url}")
        print(f"📊 Page Length: {len(page_source)} characters")
        
        # Check for key content
        key_checks = {
            "Couldn't find that podcast": "Couldn't find that podcast" in page_source,
            "Sign up to get unlimited": "Sign up to get unlimited" in page_source,
            "episode-title": "episode-title" in page_source,
            "episode-description": "episode-description" in page_source,
            "How I Built This": "How I Built This" in page_source,
            "Guy Raz": "Guy Raz" in page_source,
            "Chip and Joanna": "Chip and Joanna" in page_source or "chip" in page_source.lower()
        }
        
        print("🔍 Content Analysis:")
        for check, found in key_checks.items():
            status = "✅" if found else "❌"
            print(f"   {status} {check}: {found}")
        
        # Extract text content
        body_text = browser.driver.find_element(By.TAG_NAME, "body").text
        print(f"📝 Body Text Length: {len(body_text)} characters")
        
        # Show first 300 characters of text
        print("📖 First 300 characters of extracted text:")
        print("-" * 40)
        print(body_text[:300])
        print("-" * 40)
        
        # Save full content for analysis
        episode_id = url.split('/episode/')[-1].split('?')[0]
        filename = f"/app/real_spotify_{episode_id}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Real Spotify URL Test: {url}\n")
            f.write(f"Title: {title}\n")
            f.write(f"Final URL: {current_url}\n")
            f.write(f"Page Length: {len(page_source)}\n")
            f.write(f"Text Length: {len(body_text)}\n\n")
            f.write("=== EXTRACTED TEXT ===\n")
            f.write(body_text)
        
        print(f"💾 Full content saved to: {filename}")
        
        return {
            "title": title,
            "text_length": len(body_text),
            "has_episode_content": key_checks["episode-title"] or key_checks["How I Built This"],
            "is_error_page": key_checks["Couldn't find that podcast"]
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("🧪 Testing REAL Spotify URLs from Guy Raz Newsletter")
    print("=" * 70)
    
    # Real URLs from the database
    real_urls = [
        "https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y?si=0L4hS4wHRLWdVdJFcAkVbA",
        "https://open.spotify.com/episode/4mXY5t0BnZyPHDzCkZpkyl?si=Gc1w67wpSKaPDjGz4_Fwyg"
    ]
    
    for i, url in enumerate(real_urls, 1):
        print(f"\n🎯 TEST {i}/2:")
        result = test_real_spotify_url(url)
        
        if result:
            print(f"✅ Test completed!")
            print(f"   Text extracted: {result['text_length']} characters")
            print(f"   Has episode content: {result['has_episode_content']}")
            print(f"   Is error page: {result['is_error_page']}")
        else:
            print("❌ Test failed")
        
        print("=" * 70)

if __name__ == "__main__":
    main()