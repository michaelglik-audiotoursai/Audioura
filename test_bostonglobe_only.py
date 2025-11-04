#!/usr/bin/env python3
"""
Test Boston Globe email processing only
"""
import requests
import json

def test_bostonglobe():
    url = "https://view.email.bostonglobe.com/?qs=f5c5b263a361410773c7a0e695d276d61955798a94e17c8781cf3bcb26491dc1a43af8ddcd9bb3db4e9ad7a1d2a8cfb0eadf7fce21a8ebe84926d5498aeb789055a55cc54c9e3943fdf0e945c7e2066f3e0fd9eaa2c23a46e46c6745319389d8"
    
    print("Testing Boston Globe Email")
    print(f"URL: {url}")
    
    payload = {
        "newsletter_url": url,
        "user_id": "test_user",
        "max_articles": 10
    }
    
    try:
        response = requests.post("http://localhost:5017/process_newsletter", json=payload, timeout=300)
        print(f"Status Code: {response.status_code}")
        
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_bostonglobe()