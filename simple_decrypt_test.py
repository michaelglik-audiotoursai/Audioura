#!/usr/bin/env python3
"""
Simple test to decrypt credentials using existing working functions
"""
import requests
import json

def test_decrypt_credentials():
    """Test credential decryption using the working endpoint"""
    
    # Use the working decrypt endpoint
    response = requests.post(
        'http://localhost:5017/decrypt_credentials',
        json={'device_id': 'USER-281301397'},
        headers={'Content-Type': 'application/json'}
    )
    
    if response.status_code == 200:
        data = response.json()
        print("Decryption Test Results:")
        print("=" * 50)
        print(f"Device ID: {data['device_id']}")
        print(f"Status: {data['status']}")
        
        for cred in data['credentials']:
            print(f"\nArticle ID: {cred['article_id']}")
            print(f"Domain: {cred['domain']}")
            print(f"Newsletter ID: {cred['newsletter_id']}")
            print(f"AES Key Derived: {cred['aes_key_derived']}")
            print(f"Status: {cred['status']}")
            
            if 'error' in cred:
                print(f"Error: {cred['error']}")
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_decrypt_credentials()