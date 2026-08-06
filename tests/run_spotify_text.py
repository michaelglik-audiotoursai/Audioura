#!/usr/bin/env python3
"""
Test Spotify Text Extraction - Verify browser automation getText() functionality
"""
import sys
import os
sys.path.append('/app')

from browser_automation import test_spotify_text_extraction

def main():
    # Test with one Spotify URL from Guy Raz newsletter
    spotify_url = "https://open.spotify.com/episode/4VqMqcy0wPAECv9M1s3kGy"
    
    print("🧪 Testing Spotify Text Extraction with Browser Automation")
    print(f"URL: {spotify_url}")
    print("-" * 60)
    
    result = test_spotify_text_extraction(spotify_url)
    
    print("-" * 60)
    if result.get('success'):
        print("✅ Test completed successfully!")
        print(f"Content length: {len(result.get('content', ''))} bytes")
        
        # Check if content meets 100-byte minimum
        if len(result.get('content', '')) >= 100:
            print("✅ Content meets 100-byte minimum requirement")
        else:
            print("❌ Content below 100-byte minimum")
            
    else:
        print("❌ Test failed")

if __name__ == "__main__":
    main()