#!/usr/bin/env python3
"""
Test Enhanced Spotify Content Extraction
"""
import sys
import os
sys.path.append('/app')

from browser_automation import extract_spotify_with_browser

def main():
    # Test with real Spotify URL from Guy Raz newsletter
    real_spotify_url = "https://open.spotify.com/episode/3kFbvWAO7PzT4XC7bpUF9y?si=0L4hS4wHRLWdVdJFcAkVbA"
    
    print("🧪 Testing Enhanced Spotify Content Extraction")
    print(f"URL: {real_spotify_url}")
    print("=" * 70)
    
    result = extract_spotify_with_browser(real_spotify_url)
    
    if result.get('success'):
        print("✅ SUCCESS! Rich episode content extracted!")
        print(f"📄 Title: {result['title']}")
        print(f"📝 Description Length: {len(result['description'])} characters")
        print(f"📊 Total Content: {len(result['content'])} characters")
        print(f"🔍 Content Type: {result.get('content_type', 'standard')}")
        print(f"📖 Full Text Length: {result.get('full_text_length', 0)} characters")
        
        print("\\n📋 Content Preview:")
        print("-" * 50)
        print(result['content'][:500] + "..." if len(result['content']) > 500 else result['content'])
        print("-" * 50)
        
        # Check if meets 100-byte minimum
        if len(result['content']) >= 100:
            print("✅ Content meets 100-byte minimum requirement!")
        else:
            print("❌ Content below 100-byte minimum")
            
    else:
        print("❌ FAILED!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        print(f"Error Type: {result.get('error_type', 'unknown')}")

if __name__ == "__main__":
    main()