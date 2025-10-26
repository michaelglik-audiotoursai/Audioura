#!/usr/bin/env python3
"""
Test the new tour editing endpoints
"""
import requests
import json

BASE_URL = "http://192.168.1.20:5005"

def test_endpoint(method, url, data=None):
    """Test an endpoint and return the response"""
    print(f"\n=== Testing {method} {url} ===")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        
        print(f"Status: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)[:500]}...")
            return result
        else:
            print(f"Response: {response.text[:200]}...")
            return response.text
            
    except Exception as e:
        print(f"ERROR: {e}")
        return None

def main():
    print("Testing Tour Editing Endpoints")
    
    # Test 1: Get tour edit info
    test_endpoint("GET", f"{BASE_URL}/tour/21/edit-info")
    
    # Test 2: Create custom tour
    test_endpoint("POST", f"{BASE_URL}/tour/21/create-custom", {"user_id": "test_user"})
    
    # Test 3: Update tour stop
    test_endpoint("POST", f"{BASE_URL}/tour/21/update-stop", {
        "stop_number": 1,
        "new_text": "This is updated text for stop 1",
        "audio_format": "mp3"
    })
    
    # Test 4: Search tours (should include custom)
    test_endpoint("GET", f"{BASE_URL}/search-tours?query=egyptian")
    
    # Test 5: Tours near (should include custom)
    test_endpoint("GET", f"{BASE_URL}/tours-near/42.3393/-71.0942")

if __name__ == "__main__":
    main()