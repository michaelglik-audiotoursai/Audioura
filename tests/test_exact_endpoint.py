#!/usr/bin/env python3
import requests
import json

def test_endpoint():
    url = "http://localhost:5005/tours-near/42.3086718/-71.1942855?radius=50"
    
    try:
        print(f"Testing: {url}")
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {len(data.get('tours', []))} items")
            for item in data.get('tours', [])[:3]:  # Show first 3
                print(f"  - {item.get('name')} ({item.get('type')})")
        else:
            print(f"Error: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_endpoint()