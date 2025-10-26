#!/usr/bin/env python3
"""
Test script for user tracking integration
"""
import requests
import json
import time

def test_user_integration():
    print("Testing User Tracking Integration")
    print("=" * 50)
    
    # Test 1: Add user
    print("1. Adding test user...")
    user_id = "test_user_123"
    
    response = requests.post(
        "http://localhost:5003/user",
        headers={"Content-Type": "application/json"},
        json={
            "secret_id": user_id,
            "coordinates": {"lat": 42.325417, "lng": -71.202111}
        }
    )
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test 2: Generate tour with user tracking
    print("\n2. Generating tour with user tracking...")
    
    tour_data = {
        "location": "Boston Common",
        "tour_type": "walking",
        "total_stops": 5,
        "user_id": user_id,
        "request_string": "Please generate a walking tour of Boston Common"
    }
    
    response = requests.post(
        "http://localhost:5002/generate-complete-tour",
        headers={"Content-Type": "application/json"},
        json=tour_data
    )
    
    if response.status_code == 200:
        job_data = response.json()
        job_id = job_data["job_id"]
        print(f"   Job ID: {job_id}")
        
        # Wait a bit for processing to start
        time.sleep(5)
        
        # Check status
        status_response = requests.get(f"http://localhost:5002/status/{job_id}")
        if status_response.status_code == 200:
            status = status_response.json()
            print(f"   Status: {status['status']}")
            print(f"   Progress: {status['progress']}")
        
    else:
        print(f"   Error: {response.status_code} - {response.text}")
    
    # Test 3: Check user data
    print("\n3. Checking user tracking data...")
    
    response = requests.get(f"http://localhost:5003/user/{user_id}")
    if response.status_code == 200:
        user_data = response.json()
        print(f"   User ID: {user_data['secret_id']}")
        print(f"   Total Records: {user_data['total_records']}")
        print(f"   Coordinates: {len(user_data['coordinates'])} records")
        print(f"   Tours: {len(user_data['tours'])} records")
        
        if user_data['tours']:
            for i, tour in enumerate(user_data['tours']):
                print(f"     Tour {i+1}: {tour['tour_id']} - {tour['request_string'][:50]}...")
    else:
        print(f"   Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_user_integration()