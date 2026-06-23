#!/usr/bin/env python3
"""
Final test of Boston Globe authentication - standalone
"""

import logging
from boston_globe_session_auth import BostonGlobeSessionAuth

def test_final_bg_auth():
    """Final test of Boston Globe authentication"""
    
    print("🔐 FINAL BOSTON GLOBE AUTHENTICATION TEST")
    print("=" * 60)
    
    # Test with your real authenticated URL
    test_url = "https://www.bostonglobe.com/2025/11/12/business/harvard-students-easy-classes/?event=event12"
    username = "glikfamily@gmail.com"
    password = "Eight2Four"
    
    print(f"Testing URL: {test_url}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password)}")
    
    # Create authenticator
    auth = BostonGlobeSessionAuth()
    
    try:
        # Step 1: Authenticate
        print("\n📝 Step 1: Authenticating...")
        success = auth.authenticate_once(username, password)
        
        if not success:
            print("❌ Authentication failed")
            return
            
        print("✅ Authentication successful!")
        
        # Step 2: Extract article
        print("\n📄 Step 2: Extracting article content...")
        result = auth.extract_article(test_url)
        
        if result['success']:
            content = result['content']
            print(f"✅ Content extraction successful!")
            print(f"📊 Content length: {len(content)} characters")
            print(f"📝 Content preview (first 300 chars):")
            print("-" * 40)
            print(content[:300])
            print("-" * 40)
            print(f"📝 Content preview (last 200 chars):")
            print(content[-200:])
            print("-" * 40)
            
            # Success metrics
            print(f"\n🎯 SUCCESS METRICS:")
            print(f"   • Authentication: ✅ Working")
            print(f"   • Content Length: {len(content)} chars")
            print(f"   • Quality: {'✅ High' if len(content) > 1000 else '⚠️ Medium' if len(content) > 500 else '❌ Low'}")
            
        else:
            print(f"❌ Content extraction failed: {result['error']}")
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        
    finally:
        auth.close()
        print(f"\n🔒 Authentication session closed")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_final_bg_auth()