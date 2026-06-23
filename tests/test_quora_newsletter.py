#!/usr/bin/env python3

import requests
import json

def test_quora_newsletter():
    """Test Quora newsletter processing"""
    
    url = "http://localhost:5017/process_newsletter"
    
    # The actual Quora newsletter URL
    newsletter_url = "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717"
    
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "test_user", 
        "max_articles": 5
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Testing Quora newsletter: {newsletter_url}")
    print("Sending request...")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"✅ SUCCESS: {result.get('message', 'Newsletter processed')}")
                if 'newsletter_id' in result:
                    print(f"Newsletter ID: {result['newsletter_id']}")
            else:
                print(f"❌ ERROR: {result.get('message', 'Unknown error')}")
                print(f"Error Type: {result.get('error_type', 'unknown')}")
        else:
            print(f"❌ HTTP ERROR: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ REQUEST ERROR: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_quora_newsletter()