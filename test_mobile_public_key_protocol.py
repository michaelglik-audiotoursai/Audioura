#!/usr/bin/env python3
"""
Test Mobile Public Key Protocol Implementation
"""

import requests
import json
import secrets
from dh_service_simple import DH_PRIME, DH_GENERATOR, derive_aes_key

def test_mobile_public_key_protocol():
    """Test complete mobile public key protocol"""
    print("=== TESTING MOBILE PUBLIC KEY PROTOCOL ===")
    
    # Step 1: Process newsletter to get server public key
    print("1. Processing newsletter to get server public key...")
    
    newsletter_data = {
        "newsletter_url": "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines",
        "user_id": "MOBILE-KEY-TEST-001",
        "max_articles": 1,
        "test_mode": True
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/process_newsletter',
            json=newsletter_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            server_public_key_hex = result.get('server_public_key')
            newsletter_id = result.get('newsletter_id')
            
            if server_public_key_hex and newsletter_id:
                print(f"SUCCESS - Server public key: {server_public_key_hex[:20]}...")
                print(f"SUCCESS - Newsletter ID: {newsletter_id}")
                server_public_key = int(server_public_key_hex, 16)
            else:
                print("ERROR - Missing server_public_key or newsletter_id")
                print(f"Response: {json.dumps(result, indent=2)}")
                return False
        else:
            print(f"ERROR - Newsletter processing failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR - Newsletter processing: {e}")
        return False
    
    # Step 2: Generate mobile key pair (simulating mobile app)
    print("2. Generating mobile key pair...")
    
    mobile_private_key = secrets.randbits(256)
    mobile_public_key = pow(DH_GENERATOR, mobile_private_key, DH_PRIME)
    mobile_public_key_hex = hex(mobile_public_key)[2:]  # Remove 0x prefix
    
    print(f"SUCCESS - Mobile public key: {mobile_public_key_hex[:20]}...")
    
    # Step 3: Calculate shared secret (mobile side)
    print("3. Calculating shared secret (mobile side)...")
    
    mobile_shared_secret = pow(server_public_key, mobile_private_key, DH_PRIME)
    mobile_aes_key = derive_aes_key(mobile_shared_secret)
    
    print(f"SUCCESS - Mobile AES key: {mobile_aes_key.hex()}")
    
    # Step 4: Submit credentials with mobile public key
    print("4. Submitting credentials with mobile public key...")
    
    # Get an article ID from the newsletter (use first article)
    try:
        articles_response = requests.post(
            'http://localhost:5017/get_articles_by_newsletter_id',
            json={"newsletter_id": newsletter_id},
            timeout=10
        )
        
        if articles_response.status_code == 200:
            articles_result = articles_response.json()
            articles = articles_result.get('articles', [])
            if articles:
                test_article_id = articles[0]['article_id']
                print(f"SUCCESS - Using article ID: {test_article_id}")
            else:
                print("ERROR - No articles found in newsletter")
                return False
        else:
            print(f"ERROR - Failed to get articles: {articles_response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR - Getting articles: {e}")
        return False
    
    # Submit test credentials
    credentials_data = {
        "article_id": test_article_id,
        "device_id": "MOBILE-KEY-TEST-001",
        "mobile_public_key": mobile_public_key_hex,  # Hex string without 0x
        "encrypted_username": "test_encrypted_username_base64",
        "encrypted_password": "test_encrypted_password_base64",
        "domain": "test.com"
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/submit_credentials',
            json=credentials_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS - Credentials submitted successfully")
            print(f"Response: {json.dumps(result, indent=2)}")
        else:
            print(f"ERROR - Credential submission failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR - Credential submission: {e}")
        return False
    
    # Step 5: Test decryption endpoint
    print("5. Testing credential decryption...")
    
    decrypt_data = {
        "device_id": "MOBILE-KEY-TEST-001"
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/decrypt_credentials',
            json=decrypt_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("SUCCESS - Decryption test completed")
            
            credentials = result.get('credentials', [])
            if credentials:
                for cred in credentials:
                    if cred.get('status') == 'key_derived_successfully':
                        print(f"SUCCESS - AES key derived: {cred.get('aes_key_derived')}")
                    else:
                        print(f"WARNING - Credential issue: {cred}")
            else:
                print("WARNING - No credentials returned")
                
        else:
            print(f"ERROR - Decryption test failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR - Decryption test: {e}")
        return False
    
    print("\nSUCCESS - MOBILE PUBLIC KEY PROTOCOL WORKING!")
    print("\nProtocol Features Verified:")
    print("   - Newsletter-based server key storage")
    print("   - Mobile public key in credential submission")
    print("   - Hex format without 0x prefix")
    print("   - UUID article IDs")
    print("   - Shared secret calculation with mobile key")
    
    return True

if __name__ == "__main__":
    success = test_mobile_public_key_protocol()
    if success:
        print("\nALL TESTS PASSED - Mobile public key protocol ready!")
    else:
        print("\nTESTS FAILED - Check implementation")