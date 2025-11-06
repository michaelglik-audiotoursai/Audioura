#!/usr/bin/env python3

import requests
import json

def test_quora_newsletter_full():
    """Test Quora newsletter processing with higher article limit"""
    
    url = "http://localhost:5017/process_newsletter"
    
    # The actual Quora newsletter URL
    newsletter_url = "https://jokesfunnystories.quora.com/?__nsrc__=4&__snid3__=92061427717"
    
    payload = {
        "newsletter_url": newsletter_url,
        "user_id": "test_user", 
        "max_articles": 20  # Increased limit to get more articles
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Testing Quora newsletter with max_articles=20: {newsletter_url}")
    print("Sending request...")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "success":
                print(f"SUCCESS: {result.get('message', 'Newsletter processed')}")
                if 'newsletter_id' in result:
                    print(f"Newsletter ID: {result['newsletter_id']}")
                    print(f"Articles Found: {result.get('articles_found', 0)}")
                    print(f"Articles Created: {result.get('articles_created', 0)}")
            else:
                print(f"ERROR: {result.get('message', 'Unknown error')}")
                print(f"Error Type: {result.get('error_type', 'unknown')}")
        else:
            print(f"HTTP ERROR: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    test_quora_newsletter_full()