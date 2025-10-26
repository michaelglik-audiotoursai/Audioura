#!/usr/bin/env python3
"""
Test the user tracking fix
"""
import requests
import time

def test_tracking_fix():
    print("Testing User Tracking Fix")
    print("=" * 30)
    
    # Test with the actual user ID
    user_id = "txzs7duahw03g8l0"
    
    # Generate a test tour
    tour_data = {
        "location": "Test Museum Boston",
        "tour_type": "walking",
        "total_stops": 3,
        "user_id": user_id,
        "request_string": "Test tour for tracking verification"
    }
    
    print(f"1. Starting tour for user: {user_id}")
    response = requests.post(
        'http://192.168.0.217:5002/generate-complete-tour',
        headers={'Content-Type': 'application/json'},
        json=tour_data
    )
    
    if response.status_code == 200:
        job_id = response.json()['job_id']
        print(f"   Job started: {job_id}")
        
        # Wait a bit for processing
        print("2. Waiting for processing...")
        time.sleep(10)
        
        # Check user data
        print("3. Checking user tracking...")
        user_response = requests.get(f'http://192.168.0.217:5003/user/{user_id}')
        
        if user_response.status_code == 200:
            user_data = user_response.json()
            tours_count = len(user_data.get('tours', []))
            print(f"   User found: {tours_count} tours recorded")
            
            if tours_count > 0:
                print("   SUCCESS: User tracking is working!")
                for tour in user_data.get('tours', []):
                    print(f"   - {tour.get('request_string', 'N/A')}")
            else:
                print("   WARNING: No tours found yet (may need more time)")
        else:
            print(f"   ERROR: User not found: {user_response.status_code}")
    else:
        print(f"   ERROR: Tour generation failed: {response.status_code}")

if __name__ == "__main__":
    test_tracking_fix()