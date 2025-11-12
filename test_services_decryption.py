#!/usr/bin/env python3
"""
Test the services decryption endpoint with mobile app data
"""

import requests
import json

def test_services_decryption():
    """Test decryption via services API"""
    
    # Mobile app test data
    device_id = "USER-281301397"
    
    print("=== TESTING SERVICES DECRYPTION API ===")
    print(f"Device ID: {device_id}")
    
    try:
        # Call the decrypt credentials endpoint
        response = requests.post(
            'http://localhost:5017/decrypt_credentials',
            json={'device_id': device_id},
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("DECRYPTION SUCCESSFUL!")
            print(json.dumps(result, indent=2))
        else:
            print("DECRYPTION FAILED!")
            try:
                error_result = response.json()
                print(json.dumps(error_result, indent=2))
            except:
                print(f"Response text: {response.text}")
                
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_services_decryption()