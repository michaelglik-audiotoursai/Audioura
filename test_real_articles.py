#!/usr/bin/env python3
"""
Test Boston Globe authentication with real article URLs
"""

import logging
from boston_globe_diagnostic import BostonGlobeDiagnostic

def test_real_articles():
    """Test with actual Boston Globe article URLs"""
    auth = BostonGlobeDiagnostic()
    
    # Authenticate once
    success = auth.authenticate_once("glikfamily@gmail.com", "Eight2Four")
    if not success:
        print("Authentication failed")
        return
        
    # Real Boston Globe article URLs (recent ones)
    test_urls = [
        "https://www.bostonglobe.com/2024/11/13/metro/former-newton-mayor-setti-warren-dies-55/",
        "https://www.bostonglobe.com/2024/11/13/business/massachusetts-unemployment-rate-rises-october/",
        "https://www.bostonglobe.com/2024/11/12/sports/patriots-bears-preview/"
    ]
    
    for url in test_urls:
        print(f"\n{'='*80}")
        print(f"Testing: {url}")
        print('='*80)
        
        result = auth.diagnose_page(url)
        
        if result["success"]:
            print(f"Title: {result['page_info']['title']}")
            print(f"URL: {result['page_info']['url']}")
            print(f"Total text: {result['total_text_length']} chars")
            
            # Check if we found article content
            content_found = False
            for selector, data in result["content_analysis"].items():
                if "error" not in data and data['text_length'] > 100:
                    print(f"✅ Content found with {selector}: {data['text_length']} chars")
                    print(f"   Preview: {data['preview']}")
                    content_found = True
                    
            if not content_found:
                print("❌ No substantial article content found")
                print(f"Page preview: {result['text_preview']}")
                
            # Check paywall status
            paywall_active = any(result["paywall_check"].values())
            print(f"Paywall detected: {paywall_active}")
            
        else:
            print(f"❌ Diagnostic failed: {result['error']}")
            
    auth.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_real_articles()