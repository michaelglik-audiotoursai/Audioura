#!/usr/bin/env python3
"""
Test NY Times Authentication
"""
import sys
sys.path.append('/app')

from nytimes_session_auth import NYTimesSessionAuth

def test_nytimes_auth():
    """Test NY Times authentication with stored credentials"""
    
    # Test credentials
    username = "glikfamily@gmail.com"
    password = "Eight6Nine8"
    test_url = "https://www.nytimes.com/2025/11/23/us/politics/kash-patel-girlfriend-fbi-protection.html"
    
    print(f"Testing NY Times authentication...")
    print(f"Username: {username}")
    print(f"Test URL: {test_url}")
    
    auth = NYTimesSessionAuth()
    
    try:
        # Test authentication
        print("\n1. Testing authentication...")
        success = auth.authenticate_once(username, password)
        
        if success:
            print("✅ Authentication successful!")
            
            # Test article extraction
            print("\n2. Testing article extraction...")
            result = auth.extract_article(test_url)
            
            if result['success']:
                print(f"✅ Article extraction successful!")
                print(f"Title: {result['title']}")
                print(f"Content length: {len(result['content'])} chars")
                print(f"Content preview: {result['content'][:200]}...")
            else:
                print(f"❌ Article extraction failed: {result['error']}")
        else:
            print("❌ Authentication failed!")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
    finally:
        auth.close()

if __name__ == "__main__":
    test_nytimes_auth()