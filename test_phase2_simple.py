#!/usr/bin/env python3
"""
Simple Phase 2 Boston Globe Test
"""
import requests
import json

def test_phase2_simple():
    """Simple test of Phase 2 deployment"""
    
    print("Testing Phase 2 Boston Globe Authentication")
    print("=" * 50)
    
    # Test newsletter processing
    print("\n1. Testing newsletter processing...")
    newsletter_url = "https://mailchi.mp/bostonglobe/trendlines-trumps-obesity-drug-deal-has-lots-of-unknowns?e=a4f20567f8"
    
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "TEST-PHASE2-USER",
        "max_articles": 5,
        "test_mode": True
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=payload,
            timeout=180
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"SUCCESS: Newsletter processed")
            print(f"  Articles created: {result.get('articles_created', 0)}")
            print(f"  Subscription required: {result.get('articles_requiring_subscription', 0)}")
            print(f"  Newsletter ID: {result.get('newsletter_id')}")
            
            newsletter_id = result.get('newsletter_id')
            
            if result.get('articles_requiring_subscription', 0) > 0:
                print("  Found subscription articles - Phase 2 detection working!")
                return newsletter_id
            else:
                print("  No subscription articles found")
                return newsletter_id
                
        else:
            print(f"FAILED: {response.status_code}")
            print(f"Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def test_browser_automation():
    """Test browser automation with Boston Globe"""
    print("\n2. Testing browser automation...")
    
    try:
        # Test a simple Boston Globe article
        test_url = "https://www.bostonglobe.com/2024/11/12/business/trump-obesity-drug-deal/"
        credentials = {
            'username': 'glikfamily@gmail.com',
            'password': 'Eight2Four'
        }
        
        from browser_automation_login import extract_content_with_login
        
        print(f"  Testing URL: {test_url}")
        print("  Using provided credentials...")
        
        result = extract_content_with_login(test_url, credentials)
        
        if result.get('success'):
            content = result['content']
            print(f"  SUCCESS: Authentication worked!")
            print(f"  Content length: {len(content)} chars")
            print(f"  Title: {result.get('title', 'Unknown')[:50]}...")
            return True
        else:
            error = result.get('error', 'Unknown error')
            print(f"  FAILED: {error}")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

if __name__ == "__main__":
    print("Phase 2 Deployment Test")
    print("=" * 30)
    
    # Test 1: Newsletter processing
    newsletter_id = test_phase2_simple()
    
    # Test 2: Browser automation
    if newsletter_id:
        auth_success = test_browser_automation()
        
        if auth_success:
            print("\nPHASE 2 TEST RESULTS:")
            print("  Deployment: SUCCESS")
            print("  Newsletter processing: SUCCESS") 
            print("  Browser authentication: SUCCESS")
            print("  Ready for full Phase 2 testing!")
        else:
            print("\nPHASE 2 TEST RESULTS:")
            print("  Deployment: SUCCESS")
            print("  Newsletter processing: SUCCESS")
            print("  Browser authentication: NEEDS INVESTIGATION")
    else:
        print("\nPHASE 2 TEST RESULTS:")
        print("  Deployment: PARTIAL")
        print("  Newsletter processing: FAILED")
        print("  Need to check container logs")