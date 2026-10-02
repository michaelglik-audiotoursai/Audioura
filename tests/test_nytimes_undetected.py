#!/usr/bin/env python3
"""
Test NY Times Undetected Chrome Authentication
"""

import requests
import json
import pytest

@pytest.mark.service
def test_nytimes_article_reprocessing():
    """Test reprocessing NY Times article with authentication"""
    
    # First, let's check the current content of the Mark Kelly article
    print("Testing NY Times article reprocessing with undetected Chrome...")
    
    # Get current article content
    response = requests.get("http://localhost:5012/download/8d0cd606-f985-4759-9886-ed68340bc3b1?user_id=USER-281301397")
    
    if response.status_code == 200:
        print(f"Article download successful: {len(response.content)} bytes")
        
        # Save for inspection
        with open("mark_kelly_before_auth.zip", "wb") as f:
            f.write(response.content)
        print("Saved as mark_kelly_before_auth.zip")
        
        # Check if it contains paywall text
        content_str = str(response.content)
        if "preview view of this article" in content_str:
            print("Article contains paywall preview - authentication needed")
            return True
        else:
            print("Article appears to have full content")
            return False
    else:
        print(f"Article download failed: HTTP {response.status_code}")
        return False

if __name__ == "__main__":
    test_nytimes_article_reprocessing()