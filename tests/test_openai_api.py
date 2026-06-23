#!/usr/bin/env python3
import os
import requests
import json

def test_openai_api():
    api_key = os.environ.get("OPENAI_API_KEY")
    print(f"API Key present: {bool(api_key)}")
    
    if not api_key:
        print("ERROR: No API key found")
        return False
    
    print(f"API Key starts with: {api_key[:20]}...")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "List 2 real points of interest in Newton Center, MA"}
        ],
        "max_tokens": 100
    }
    
    try:
        print("Making API call...")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            print(f"SUCCESS: {content}")
            return True
        else:
            print(f"ERROR Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    test_openai_api()