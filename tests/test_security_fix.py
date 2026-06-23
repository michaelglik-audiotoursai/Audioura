#!/usr/bin/env python3
"""
Test Security Fix - Credential Verification
Tests that fake credentials are rejected
"""

import requests
import json

def test_fake_credentials():
    """Test that fake credentials are rejected"""
    print("=== Testing Security Fix: Fake Credentials ===")
    
    # Get a Boston Globe article that requires subscription
    response = requests.post("http://localhost:5017/get_articles_by_newsletter_id", 
                           json={"newsletter_id": 183, "user_id": "FAKE-USER-TEST"})
    
    if response.status_code == 200:
        articles = response.json()['articles']
        bg_articles = [a for a in articles if a.get('subscription_domain') == 'bostonglobe.com' and a.get('subscription_required')]
        
        if bg_articles:
            test_article = bg_articles[0]
            print(f"Testing with article: {test_article['article_id']}")
            print(f"Article requires subscription: {test_article['subscription_required']}")
            
            # Try to submit fake credentials (this should fail now)
            fake_creds = {
                "article_id": test_article['article_id'],
                "device_id": "FAKE-USER-TEST", 
                "mobile_public_key": "fake_key",
                "encrypted_username": "fake_encrypted_user",
                "encrypted_password": "fake_encrypted_pass",
                "domain": "bostonglobe.com"
            }
            
            print("\nAttempting to submit fake credentials...")
            cred_response = requests.post("http://localhost:5017/submit_credentials", json=fake_creds)
            
            print(f"Response status: {cred_response.status_code}")
            print(f"Response: {cred_response.json()}")
            
            if cred_response.status_code == 400:
                print("SECURITY FIX WORKING: Fake credentials rejected!")
            else:
                print("SECURITY ISSUE: Fake credentials accepted!")
        else:
            print("No Boston Globe articles found for testing")
    else:
        print(f"Failed to get articles: {response.status_code}")

def test_verified_credentials_check():
    """Test that only verified credentials grant access"""
    print("\n=== Testing Verified Credentials Check ===")
    
    # Check current user with verified credentials
    response = requests.post("http://localhost:5017/get_articles_by_newsletter_id",
                           json={"newsletter_id": 183, "user_id": "USER-281301397"})
    
    if response.status_code == 200:
        articles = response.json()['articles']
        bg_articles = [a for a in articles if a.get('subscription_domain') == 'bostonglobe.com']
        
        print(f"Found {len(bg_articles)} Boston Globe articles")
        for article in bg_articles[:2]:  # Show first 2
            print(f"  Article {article['article_id']}: subscription_required = {article['subscription_required']}")
    
    # Check fake user (should require subscription)
    response = requests.post("http://localhost:5017/get_articles_by_newsletter_id",
                           json={"newsletter_id": 183, "user_id": "FAKE-USER-TEST"})
    
    if response.status_code == 200:
        articles = response.json()['articles']
        bg_articles = [a for a in articles if a.get('subscription_domain') == 'bostonglobe.com']
        
        print(f"\nFake user sees {len(bg_articles)} Boston Globe articles")
        for article in bg_articles[:2]:  # Show first 2
            print(f"  Article {article['article_id']}: subscription_required = {article['subscription_required']}")

if __name__ == "__main__":
    test_fake_credentials()
    test_verified_credentials_check()