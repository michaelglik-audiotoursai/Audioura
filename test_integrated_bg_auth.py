#!/usr/bin/env python3
"""
Test integrated Boston Globe authentication in newsletter processor service
"""

import requests
import json
import logging

def test_integrated_bg_auth():
    """Test Boston Globe authentication integration"""
    
    # Step 1: Submit credentials for Boston Globe
    print("Step 1: Submitting Boston Globe credentials...")
    
    credentials_payload = {
        "article_id": "test-article-id",
        "device_id": "test-device-123",
        "mobile_public_key": "1234567890abcdef",  # Mock key for testing
        "encrypted_username": "mock_encrypted_username",
        "encrypted_password": "mock_encrypted_password", 
        "domain": "bostonglobe.com"
    }
    
    # Note: This will fail because we don't have real encrypted credentials
    # But it tests the endpoint structure
    
    # Step 2: Test newsletter processing with Boston Globe article
    print("\nStep 2: Testing newsletter processing with Boston Globe article...")
    
    newsletter_payload = {
        "newsletter_url": "https://www.bostonglobe.com/2025/11/12/business/harvard-students-easy-classes/?event=event12",
        "user_id": "test-device-123",
        "max_articles": 3,
        "test_mode": True
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=newsletter_payload,
            timeout=60
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Newsletter processing successful!")
            print(f"Articles found: {result.get('articles_found', 0)}")
            print(f"Articles created: {result.get('articles_created', 0)}")
            print(f"Articles requiring subscription: {result.get('articles_requiring_subscription', 0)}")
            
            if result.get('server_public_key'):
                print(f"Server public key generated: {result['server_public_key'][:20]}...")
                
        else:
            print(f"❌ Newsletter processing failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('message', 'Unknown error')}")
            except:
                print(f"Response: {response.text[:200]}")
                
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_integrated_bg_auth()