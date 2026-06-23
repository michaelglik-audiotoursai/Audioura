#!/usr/bin/env python3
"""
Test Spotify Content Expansion Fix
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from spotify_processor import process_spotify_url
import json

def test_spotify_expansion():
    """Test the Spotify content expansion fix"""
    print("=== TESTING SPOTIFY CONTENT EXPANSION FIX ===")
    
    # Test URL that was reported as truncated
    test_url = "https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3?si=e01TiIuARxqSIqVnaaaYVQ"
    
    print(f"Testing URL: {test_url}")
    print("Processing...")
    
    result = process_spotify_url(test_url)
    
    print(f"\nRESULTS:")
    print(f"Success: {result.get('success', False)}")
    print(f"Error: {result.get('error', 'None')}")
    
    content = result.get('content', '')
    description = result.get('description', '')
    
    print(f"Content length: {len(content)} chars")
    print(f"Description length: {len(description)} chars")
    
    if result.get('expanded'):
        print("✅ CONTENT WAS EXPANDED")
    else:
        print("❌ Content was not expanded")
    
    # Check for truncation indicators
    if "... Show more" in content or "Show more" in content:
        print("❌ STILL TRUNCATED - Content expansion failed")
        return False
    elif len(content) > 500:
        print("✅ SUBSTANTIAL CONTENT - Expansion likely successful")
        return True
    else:
        print("⚠️  SHORT CONTENT - May still be truncated")
        return False

if __name__ == "__main__":
    success = test_spotify_expansion()
    exit(0 if success else 1)