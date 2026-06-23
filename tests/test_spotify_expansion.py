#!/usr/bin/env python3
"""
Test Spotify Content Expansion
Tests the enhanced Spotify processor with 'Show more' button functionality
"""
import json
import logging
from spotify_processor import process_spotify_url

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_spotify_expansion():
    """Test Spotify content expansion with the problematic URL"""
    
    # The URL from the issue that has truncated content with "Show more"
    test_url = "https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3?si=e01TiIuARxqSIqVnaaaYVQ"
    
    print("SPOTIFY CONTENT EXPANSION TEST")
    print("=" * 60)
    print(f"Testing URL: {test_url}")
    print()
    
    # Process the URL with enhanced expansion
    result = process_spotify_url(test_url)
    
    print("RESULTS:")
    print("-" * 30)
    
    if result.get('success'):
        print(f"✅ SUCCESS: Content extracted successfully")
        print(f"Title: {result.get('title', 'N/A')}")
        print(f"Content length: {len(result.get('content', ''))} characters")
        print(f"Description length: {len(result.get('description', ''))} characters")
        
        if result.get('expanded'):
            print(f"🔄 EXPANSION: Content was expanded using 'Show more' functionality")
        
        print(f"\nContent preview:")
        print(f"{result.get('content', '')[:300]}...")
        
        # Save full result for analysis
        with open('debug_spotify_expansion_result.json', 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n📄 Full result saved to: debug_spotify_expansion_result.json")
        
    else:
        print(f"❌ FAILED: {result.get('error', 'Unknown error')}")
        print(f"Error type: {result.get('error_type', 'N/A')}")
        
        if 'content_length' in result:
            print(f"Content length: {result['content_length']} chars")
        
        # Save error result for debugging
        with open('debug_spotify_expansion_error.json', 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n📄 Error details saved to: debug_spotify_expansion_error.json")
    
    print("\nDEBUG FILES CREATED:")
    print("- debug_spotify_raw_response.html (raw HTML from Spotify)")
    print("- debug_spotify_extraction.txt (extraction details)")
    print("- debug_spotify_expansion_result.json (final result)")
    
    return result

def test_comparison():
    """Compare before and after expansion results"""
    print("\n" + "=" * 60)
    print("CONTENT EXPANSION COMPARISON")
    print("=" * 60)
    
    # Test the same URL that should have "Show more" functionality
    test_url = "https://open.spotify.com/episode/3VJHfEUYl7tHUll4vfu1D3?si=e01TiIuARxqSIqVnaaaYVQ"
    
    result = test_spotify_expansion()
    
    if result.get('success'):
        content_length = len(result.get('content', ''))
        description_length = len(result.get('description', ''))
        
        print(f"\nCONTENT ANALYSIS:")
        print(f"- Total content: {content_length} characters")
        print(f"- Description: {description_length} characters")
        
        # Check for truncation indicators
        content = result.get('content', '')
        description = result.get('description', '')
        
        truncation_indicators = ["...", "Show more", "Read more", "See more"]
        found_indicators = []
        
        for indicator in truncation_indicators:
            if indicator in content or indicator in description:
                found_indicators.append(indicator)
        
        if found_indicators:
            print(f"⚠️  TRUNCATION DETECTED: Found indicators: {found_indicators}")
            print("   Content may still be truncated despite expansion attempts")
        else:
            print(f"✅ NO TRUNCATION: Content appears to be fully expanded")
        
        # Quality assessment
        if content_length > 500:
            print(f"✅ QUALITY: Good content length ({content_length} chars)")
        elif content_length > 200:
            print(f"⚠️  QUALITY: Moderate content length ({content_length} chars)")
        else:
            print(f"❌ QUALITY: Poor content length ({content_length} chars)")
    
    return result

if __name__ == "__main__":
    try:
        result = test_comparison()
        
        print(f"\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
        if result.get('success'):
            print("✅ Spotify content expansion test PASSED")
        else:
            print("❌ Spotify content expansion test FAILED")
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        logging.error(f"Test exception: {e}")
    
    finally:
        # Clean up browser
        try:
            from browser_automation import _browser
            if _browser:
                _browser.close()
                print("🧹 Browser cleaned up")
        except:
            pass