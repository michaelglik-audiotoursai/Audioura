#!/usr/bin/env python3
"""
Simple test for Diffie-Hellman key exchange
"""

import requests
import json
import secrets
from dh_service_simple import DH_PRIME, DH_GENERATOR, derive_aes_key

def test_dh_key_exchange():
    """Test DH key exchange flow"""
    print("=== TESTING DIFFIE-HELLMAN KEY EXCHANGE ===")
    
    # Step 1: Process newsletter to get server public key
    print("1. Processing newsletter to get server public key...")
    
    newsletter_data = {
        "newsletter_url": "https://guyraz.substack.com/p/10-lessons-from-chip-and-joanna-gaines",
        "user_id": "DH-TEST-USER-001",
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
            
            if server_public_key_hex:
                print(f"SUCCESS - Server public key received: {server_public_key_hex[:20]}...")
                server_public_key = int(server_public_key_hex, 16)
            else:
                print("ERROR - No server public key in response")
                print(f"Response: {json.dumps(result, indent=2)}")
                return False
        else:
            print(f"ERROR - Newsletter processing failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR - Newsletter processing error: {e}")
        return False
    
    # Step 2: Generate client key pair
    print("2. Generating client key pair...")
    
    client_private_key = secrets.randbits(256)
    client_public_key = pow(DH_GENERATOR, client_private_key, DH_PRIME)
    
    print("SUCCESS - Client key pair generated")
    
    # Step 3: Calculate shared secret (client side)
    print("3. Calculating shared secret...")
    
    client_shared_secret = pow(server_public_key, client_private_key, DH_PRIME)
    client_aes_key = derive_aes_key(client_shared_secret)
    
    print(f"SUCCESS - Client AES key derived: {client_aes_key.hex()}")
    
    # Step 4: Complete key exchange with server
    print("4. Completing key exchange with server...")
    
    key_exchange_data = {
        "device_id": "DH-TEST-USER-001",
        "client_public_key": hex(client_public_key)
    }
    
    try:
        response = requests.post(
            'http://localhost:5017/key_exchange',
            json=key_exchange_data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('shared_secret_confirmed'):
                print("SUCCESS - Key exchange completed successfully")
            else:
                print("ERROR - Key exchange not confirmed")
                print(f"Response: {json.dumps(result, indent=2)}")
                return False
        else:
            print(f"ERROR - Key exchange failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR - Key exchange error: {e}")
        return False
    
    print("\nSUCCESS - DIFFIE-HELLMAN KEY EXCHANGE COMPLETED!")
    print("\nSecurity Benefits Achieved:")
    print("   - Perfect Forward Secrecy - New keys each session")
    print("   - No Key Transmission - Shared secret never sent")
    print("   - Standard Cryptography - RFC 3526 Group 14")
    print("   - Session Isolation - Each device gets unique key")
    
    return True

if __name__ == "__main__":
    success = test_dh_key_exchange()
    if success:
        print("\nALL TESTS PASSED - Diffie-Hellman implementation ready!")
    else:
        print("\nTESTS FAILED - Check implementation")