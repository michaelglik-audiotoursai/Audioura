#!/usr/bin/env python3
"""
Test Boston Globe authentication with a specific article
"""

import logging
from boston_globe_content_extractor import BostonGlobeContentExtractor

def test_specific_article():
    """Test with a specific Boston Globe article"""
    extractor = BostonGlobeContentExtractor()
    
    # Test credentials
    username = "glikfamily@gmail.com"
    password = "Eight2Four"
    
    # Try a specific article URL
    test_urls = [
        "https://www.bostonglobe.com/2024/11/13/business/former-mayor-setti-warren-dead-55/",
        "https://www.bostonglobe.com/2024/11/13/metro/",
        "https://www.bostonglobe.com/2024/11/12/business/"
    ]
    
    for test_url in test_urls:
        print(f"\n{'='*60}")
        print(f"Testing URL: {test_url}")
        print('='*60)
        
        result = extractor.authenticate_and_extract(test_url, username, password)
        
        print(f"Success: {result['success']}")
        
        if result["success"]:
            content = result['content']
            print(f"Content length: {len(content)} characters")
            print(f"Content preview (first 500 chars):")
            print(content[:500])
            print(f"\nContent preview (last 200 chars):")
            print(content[-200:])
            break  # Stop on first success
        else:
            print(f"Error: {result['error']}")
            
        # Create new extractor instance for next test
        extractor = BostonGlobeContentExtractor()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_specific_article()