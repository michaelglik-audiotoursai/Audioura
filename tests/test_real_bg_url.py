#!/usr/bin/env python3
"""
Test Boston Globe authentication with real authenticated URL
"""

import logging
from boston_globe_diagnostic import BostonGlobeDiagnostic

def test_real_bg_url():
    """Test with the real authenticated Boston Globe URL"""
    auth = BostonGlobeDiagnostic()
    
    # Authenticate once
    success = auth.authenticate_once("glikfamily@gmail.com", "Eight2Four")
    if not success:
        print("❌ Authentication failed")
        return
        
    # Test with the real URL provided
    test_url = "https://www.bostonglobe.com/2025/11/12/business/harvard-students-easy-classes/?event=event12"
    
    print(f"Testing real authenticated URL: {test_url}")
    
    result = auth.diagnose_page(test_url)
    
    if result["success"]:
        print(f"✅ Page loaded successfully")
        print(f"Title: {result['page_info']['title']}")
        print(f"Total text: {result['total_text_length']} chars")
        
        # Find best content selector
        best_selector = None
        best_length = 0
        
        for selector, data in result["content_analysis"].items():
            if "error" not in data and data['text_length'] > best_length:
                best_selector = selector
                best_length = data['text_length']
                
        if best_selector and best_length > 200:
            print(f"✅ Article content found!")
            print(f"Best selector: {best_selector}")
            print(f"Content length: {best_length} chars")
            print(f"Preview: {result['content_analysis'][best_selector]['preview']}")
        else:
            print("❌ No substantial article content found")
            print("Available content:")
            for selector, data in result["content_analysis"].items():
                if "error" not in data and data['text_length'] > 0:
                    print(f"  {selector}: {data['text_length']} chars")
                    
        # Show paywall status
        paywall_indicators = result["paywall_check"]
        active_indicators = [k for k, v in paywall_indicators.items() if v]
        if active_indicators:
            print(f"⚠️  Paywall indicators: {', '.join(active_indicators)}")
        else:
            print("✅ No paywall detected")
            
    else:
        print(f"❌ Diagnostic failed: {result['error']}")
        
    auth.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_real_bg_url()