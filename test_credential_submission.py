#!/usr/bin/env python3
"""
Test credential submission using mobile app log data
"""

import requests
import json

def test_credential_submission():
    """Test credential submission with mobile app data"""
    
    # Data from mobile app logs
    payload = {
        "article_id": "9e6fcaec-58d4-4d94-9225-e412c492fd0a",
        "mobile_public_key": "fe4658dbb616a427b6bfc1c7c12cd8d1b7e79820ed1edb2af788377d5a3438aaa6fb0c0ddbbdc5c4834cc5fe97d9d1c60f55458bab8d2822e6249864804ef55aa23a1fd5004f09d58ac831c979f41fdedf4e592ad6459ea5185e658235712f20ef046fdc83f70ae955a66bfc4504e6315b103a228d0ec4e0e81145d378c8b0acf429aacdee0492086610ab1c55bbc89d21f3f2cb90a562beb9f1f20e90229a1c2762b9f99113b85dfc0151ef0981db942cc38cf58f6f8c4d48ed1ed4e7ce539cd9264c09877f5ab12961496cae0e9cb62634bd3f398a18ea7f061aa0e12cb5d6f802b4e158f6ced6428986138a1f3632a24026b9b91e4f701b18b92ccc1d3de5",
        "encrypted_username": "vG/9FfKMO7oNEDej/X3Lp554xj2B+j6rUXqm79Mc0TIM4ZrxpVJE8qZFC9ERXyGU",
        "encrypted_password": "rb/rgRFhSYg3HvOxbFfaKklfreJ8fbYUSecsh8RnOr4=",
        "device_id": "USER-281301397",
        "domain": "bostonglobe.com"
    }
    
    print("=== TESTING CREDENTIAL SUBMISSION ===")
    print(f"Article ID: {payload['article_id']}")
    print(f"Domain: {payload['domain']}")
    print()
    
    try:
        response = requests.post(
            'http://localhost:5017/submit_credentials',
            json=payload,
            timeout=30
        )
        
        print(f"Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("CREDENTIAL SUBMISSION SUCCESSFUL!")
            print(json.dumps(result, indent=2))
        else:
            print("CREDENTIAL SUBMISSION FAILED!")
            try:
                error_result = response.json()
                print(json.dumps(error_result, indent=2))
            except:
                print(f"Response text: {response.text}")
                
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_credential_submission()