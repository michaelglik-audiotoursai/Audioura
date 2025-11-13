#!/usr/bin/env python3
"""
Test Boston Globe Authentication with Subscription URL
"""

import sys
import logging
from boston_globe_session_auth import BostonGlobeSessionAuth

def test_subscription_url():
    """Test authentication with a subscription-required URL"""
    
    # One of the failed URLs from the newsletter
    test_url = "https://click.email.bostonglobe.com/?qs=39dc4f12df993629c5e269dd17e0b352d8b847531dd79d7e8c69be0317cc32b5cc8a071de7d5e3dcf673869d27589ed9cdff15774a54efdbbdfcb3dd13af7991"
    
    print(f"Testing Boston Globe authentication with subscription URL:")
    print(f"URL: {test_url}")
    print("-" * 80)
    
    auth = BostonGlobeSessionAuth()
    
    try:
        # Authenticate with test credentials
        print("Authenticating with Boston Globe...")
        success = auth.authenticate_once("glikfamily@gmail.com", "Eight2Four")
        
        if not success:
            print("❌ Authentication failed")
            return False
            
        print("✅ Authentication successful")
        
        # Test article extraction
        print(f"Extracting content from subscription URL...")
        result = auth.extract_article(test_url)
        
        if result['success']:
            content_length = len(result['content'])
            print(f"✅ Content extracted successfully: {content_length} characters")
            print(f"Preview: {result['content'][:300]}...")
            
            if content_length > 1000:
                print("🎉 SUCCESS: Premium content extracted (>1000 chars)")
                return True
            else:
                print("⚠️  Content extracted but may not be premium article")
                return False
        else:
            print(f"❌ Content extraction failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False
        
    finally:
        auth.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = test_subscription_url()
    sys.exit(0 if success else 1)