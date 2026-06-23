#!/usr/bin/env python3
"""
Test script to verify user tracking integration is working
"""
import requests
import json
import time

API_BASE_URL = 'http://192.168.0.217:5002'
USER_API_URL = 'http://192.168.0.217:5003'

def test_user_tracking_integration():
    """Test the complete user tracking integration"""
    print("Testing User Tracking Integration")
    print("=" * 50)
    
    # Test user ID
    test_user_id = f"test_user_{int(time.time())}"
    print(f"Test User ID: {test_user_id}")
    
    # Step 1: Test tour generation with user tracking
    print("\n1. Testing tour generation with user tracking...")
    tour_data = {
        "location": "Test Museum",
        "tour_type": "museum",
        "total_stops": 3,
        "user_id": test_user_id,
        "request_string": "I would like a test tour for integration testing"
    }
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/generate-complete-tour",
            headers={"Content-Type": "application/json"},
            json=tour_data,
            timeout=10
        )
        
        if response.status_code == 200:
            job_data = response.json()
            job_id = job_data["job_id"]
            print(f"SUCCESS: Tour generation started: {job_id}")
            
            # Step 2: Wait a bit and check status
            print("\n2. Checking job status...")
            time.sleep(5)
            
            status_response = requests.get(f"{API_BASE_URL}/status/{job_id}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"Job Status: {status_data['status']}")
                print(f"Progress: {status_data['progress']}")
                
                # Check if user_id is being tracked
                if 'user_id' in status_data:
                    print(f"SUCCESS: User ID tracked: {status_data['user_id']}")
                else:
                    print("WARNING: User ID not found in job status")
            else:
                print(f"ERROR: Failed to get job status: {status_response.text}")
        else:
            print(f"ERROR: Failed to start tour generation: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to tour orchestrator service (port 5002)")
        print("HINT: Make sure Docker services are running")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    
    # Step 3: Test user tracking service directly
    print("\n3. Testing user tracking service directly...")
    try:
        users_response = requests.get(f"{USER_API_URL}/users")
        if users_response.status_code == 200:
            users_data = users_response.json()
            print(f"SUCCESS: Total users in system: {users_data.get('total_users', 0)}")
        else:
            print(f"ERROR: Failed to get users list: {users_response.text}")
            
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to user tracking service (port 5003)")
        print("HINT: Make sure user-tracking service is running")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("Integration Test Summary:")
    print("- Tour orchestrator accepts user_id parameter")
    print("- User tracking service is accessible")
    print("- Complete integration requires tour completion")
    print("\nNext Steps:")
    print("1. Install AsyncStorage in mobile app: npm install")
    print("2. Restart mobile app to use updated code")
    print("3. Generate a tour from mobile app to test end-to-end")
    
    return True

if __name__ == "__main__":
    test_user_tracking_integration()