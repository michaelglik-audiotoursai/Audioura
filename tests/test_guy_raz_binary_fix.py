#!/usr/bin/env python3

import requests
import json

def test_guy_raz_binary_fix():
    """Test Guy Raz newsletter with binary content fix"""
    
    url = "http://localhost:5017/process_newsletter"
    
    # The problematic Guy Raz newsletter URL
    newsletter_url = "https://guyraz.substack.com/p/the-babylist-playbook-how-one-mom?utm_source=post-email-title&publication_id=2607539"
    
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "test_user", 
        "max_articles": 5
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Testing Guy Raz newsletter with binary fix: {newsletter_url}")
    print("Sending request...")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            
            if result.get("status") == "success":
                print(f"SUCCESS: {result.get('message', 'Newsletter processed')}")
                print(f"Newsletter ID: {result.get('newsletter_id')}")
                print(f"Articles Created: {result.get('articles_created', 0)}")
                print(f"Articles Failed: {result.get('articles_failed', 0)}")
            else:
                print(f"ERROR: {result.get('message', 'Unknown error')}")
                print(f"Error Type: {result.get('error_type', 'unknown')}")
        else:
            print(f"HTTP ERROR: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_guy_raz_binary_fix()