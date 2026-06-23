#!/usr/bin/env python3
"""
Test Boston Globe Authentication in Container
"""
from browser_automation_login import extract_content_with_login

def test_boston_globe_auth():
    """Test Boston Globe authentication"""
    
    # Test credentials
    credentials = {
        'username': 'glikfamily@gmail.com',
        'password': 'Eight2Four'
    }
    
    # Test with a Boston Globe article
    test_url = "https://www.bostonglobe.com/2024/11/12/business/"
    
    print(f"Testing Boston Globe authentication...")
    print(f"URL: {test_url}")
    print(f"Username: {credentials['username']}")
    
    try:
        result = extract_content_with_login(test_url, credentials)
        
        if result.get('success'):
            content = result['content']
            title = result.get('title', 'Unknown')
            
            print(f"SUCCESS: Authentication worked!")
            print(f"Title: {title[:100]}...")
            print(f"Content length: {len(content)} characters")
            print(f"Content preview: {content[:300]}...")
            
            return True
        else:
            error = result.get('error', 'Unknown error')
            print(f"FAILED: {error}")
            
            # Provide debugging info
            if 'login failed' in error.lower():
                print("DIAGNOSIS: Login credentials or process failed")
                print("- Check if credentials are correct")
                print("- Check if Boston Globe login page changed")
                print("- Check for 2FA or captcha requirements")
            elif 'content' in error.lower():
                print("DIAGNOSIS: Login worked but content extraction failed")
                print("- Article may still be behind paywall")
                print("- Page structure may have changed")
            else:
                print("DIAGNOSIS: Technical error")
                print("- Browser automation issue")
                print("- Network connectivity problem")
            
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        print("DIAGNOSIS: Module or dependency issue")
        return False

if __name__ == "__main__":
    test_boston_globe_auth()