#!/usr/bin/env python3
"""
Test browser automation on blocked babylist-playbook URL
to determine if blocking is IP-based or request-pattern-based
"""

import pytest
pytest.importorskip("selenium")  # LOCAL-544: skip when optional dep missing

import requests
from browser_automation import extract_newsletter_content_with_browser
import time

def test_blocked_url():
    """Test the blocked babylist-playbook URL with both methods"""
    
    # The blocked URL from previous tests
    blocked_url = "https://babylist-playbook.ck.page/posts/the-best-baby-gear-of-2024"
    
    print("🧪 TESTING BLOCKED URL WITH BROWSER AUTOMATION")
    print(f"URL: {blocked_url}")
    print("=" * 80)
    
    # Test 1: Regular requests (should fail)
    print("\n1️⃣ TESTING REGULAR REQUESTS (Expected: BLOCKED)")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(blocked_url, headers=headers, timeout=10)
        print(f"✅ Regular requests SUCCESS: {response.status_code}")
        print(f"Content length: {len(response.text)} chars")
        if len(response.text) < 1000:
            print(f"Content preview: {response.text[:500]}...")
        else:
            print("Content appears substantial")
            
    except Exception as e:
        print(f"❌ Regular requests FAILED: {str(e)}")
    
    # Test 2: Browser automation (the real test)
    print("\n2️⃣ TESTING BROWSER AUTOMATION")
    try:
        print("Starting browser automation...")
        content = extract_newsletter_content_with_browser(blocked_url)
        
        if content and len(content) > 100:
            print(f"✅ Browser automation SUCCESS!")
            print(f"Content length: {len(content)} chars")
            print(f"Content preview: {content[:200]}...")
            
            # Check if it's real content or error page
            if "access denied" in content.lower() or "blocked" in content.lower() or "forbidden" in content.lower():
                print("⚠️  Content appears to be error/blocked page")
            else:
                print("✅ Content appears to be real newsletter content")
                
        else:
            print(f"❌ Browser automation returned minimal content: {len(content) if content else 0} chars")
            if content:
                print(f"Content: {content}")
                
    except Exception as e:
        print(f"❌ Browser automation FAILED: {str(e)}")
    
    print("\n" + "=" * 80)
    print("🔍 ANALYSIS:")
    print("If browser automation succeeds where regular requests fail:")
    print("  → REQUEST-PATTERN-BASED blocking (can be bypassed)")
    print("If both methods fail:")
    print("  → IP-BASED blocking (cannot be bypassed with browser automation)")
    print("If both methods succeed:")
    print("  → No blocking detected (previous issue was temporary)")

if __name__ == "__main__":
    test_blocked_url()