#!/usr/bin/env python3
"""
Detailed Spotify Text Analysis - Show exactly what getText() captures
"""
import sys
import os
sys.path.append('/app')

from browser_automation import get_browser
from selenium.webdriver.common.by import By

def analyze_spotify_text(spotify_url):
    """Detailed analysis of Spotify text extraction"""
    browser = get_browser()
    
    if not browser.driver:
        print("❌ Browser not initialized")
        return
    
    try:
        print(f"🔍 Loading Spotify URL: {spotify_url}")
        browser.driver.get(spotify_url)
        
        # Wait for page load
        import time
        time.sleep(5)
        
        # Get full page text
        body_element = browser.driver.find_element(By.TAG_NAME, "body")
        full_text = body_element.text
        
        print(f"📄 Full page text length: {len(full_text)} characters")
        print("=" * 60)
        
        # Show first 500 characters
        print("🔤 First 500 characters of extracted text:")
        print("-" * 40)
        print(full_text[:500])
        print("-" * 40)
        
        # Look for keywords that might indicate episode content
        keywords = ["roger martin", "charismatic", "chip", "joanna", "episode", "podcast"]
        found_keywords = []
        
        for keyword in keywords:
            if keyword.lower() in full_text.lower():
                found_keywords.append(keyword)
        
        print(f"🔍 Found keywords: {found_keywords}")
        
        # Save full text for analysis
        episode_id = spotify_url.split('/episode/')[-1].split('?')[0]
        filename = f"/app/spotify_full_text_{episode_id}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(full_text)
        
        print(f"💾 Saved full text to: {filename}")
        
        # Try to find specific content sections
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        substantial_lines = [line for line in lines if len(line) > 50]
        
        print(f"📝 Total lines: {len(lines)}")
        print(f"📝 Substantial lines (>50 chars): {len(substantial_lines)}")
        
        if substantial_lines:
            print("📋 First few substantial lines:")
            for i, line in enumerate(substantial_lines[:5]):
                print(f"  {i+1}. {line[:100]}...")
        
        return {
            "full_text": full_text,
            "length": len(full_text),
            "keywords_found": found_keywords,
            "substantial_lines": len(substantial_lines)
        }
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        return None

def main():
    spotify_url = "https://open.spotify.com/episode/4VqMqcy0wPAECv9M1s3kGy"
    
    print("🧪 Detailed Spotify Text Analysis")
    print("=" * 60)
    
    result = analyze_spotify_text(spotify_url)
    
    if result:
        print("=" * 60)
        print("✅ Analysis completed!")
        print(f"Total text extracted: {result['length']} characters")
        print(f"Keywords found: {result['keywords_found']}")
        print(f"Substantial content lines: {result['substantial_lines']}")

if __name__ == "__main__":
    main()