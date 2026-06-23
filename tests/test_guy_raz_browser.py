#!/usr/bin/env python3
"""
Test Guy Raz newsletter URL with browser automation
to determine if blocking is IP-based or request-pattern-based
"""

import requests
from browser_automation import extract_newsletter_content_with_browser
import time

def test_guy_raz_url():
    """Test the Guy Raz newsletter URL with both methods"""
    
    # The correct Guy Raz newsletter URL
    guy_raz_url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    print("🧪 TESTING GUY RAZ NEWSLETTER WITH BROWSER AUTOMATION")
    print(f"URL: {guy_raz_url}")
    print("=" * 80)
    
    # Test 1: Regular requests
    print("\n1️⃣ TESTING REGULAR REQUESTS")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(guy_raz_url, headers=headers, timeout=10)
        print(f"✅ Regular requests SUCCESS: {response.status_code}")
        print(f"Content length: {len(response.text)} chars")
        
        # Check for blocking indicators
        if "access denied" in response.text.lower() or "forbidden" in response.text.lower():
            print("⚠️  Content appears to be blocked/error page")
        elif len(response.text) > 5000:
            print("✅ Content appears substantial - likely real newsletter")
        else:
            print("⚠️  Content appears minimal")
            
        print(f"Content preview: {response.text[:300]}...")
            
    except Exception as e:
        print(f"❌ Regular requests FAILED: {str(e)}")
    
    # Test 2: Browser automation
    print("\n2️⃣ TESTING BROWSER AUTOMATION")
    try:
        print("Starting browser automation...")
        content = extract_newsletter_content_with_browser(guy_raz_url)
        
        if content and len(content) > 100:
            print(f"✅ Browser automation SUCCESS!")
            print(f"Content length: {len(content)} chars")
            
            # Check if it's real content or error page
            if "access denied" in content.lower() or "blocked" in content.lower() or "forbidden" in content.lower():
                print("⚠️  Content appears to be error/blocked page")
            elif "babylist" in content.lower() or "playbook" in content.lower():
                print("✅ Content appears to be real Guy Raz newsletter about Babylist")
            else:
                print("✅ Content appears to be real newsletter content")
                
            print(f"Content preview: {content[:300]}...")
                
        else:
            print(f"❌ Browser automation returned minimal content: {len(content) if content else 0} chars")
            if content:
                print(f"Content: {content}")
                
    except Exception as e:
        print(f"❌ Browser automation FAILED: {str(e)}")
    
    print("\n" + "=" * 80)
    print("🔍 ANALYSIS:")
    print("If browser automation gets more content than regular requests:")
    print("  → REQUEST-PATTERN-BASED blocking (browser automation bypasses it)")
    print("If both methods get similar content:")
    print("  → No blocking detected (content accessible)")
    print("If both methods fail:")
    print("  → IP-BASED blocking or URL doesn't exist")

if __name__ == "__main__":
    test_guy_raz_url()