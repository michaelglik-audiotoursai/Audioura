#!/usr/bin/env python3
"""
Step-by-step Diffie-Hellman debugging to match mobile app exactly
"""

import base64
import hashlib
import psycopg2
import os

# RFC 3526 Group 14 parameters (2048-bit)
DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def big_int_to_full_bytes(big_int):
    """Mobile app's _bigIntToFullBytes method"""
    if big_int == 0:
        return bytes([0])
    
    byte_list = []
    temp = big_int
    
    while temp > 0:
        byte_list.insert(0, temp & 0xff)
        temp = temp >> 8
    
    return bytes(byte_list)

def debug_dh_calculation():
    """Debug each step of DH calculation"""
    
    # Test data from mobile app v1.2.8+16
    newsletter_id = 174
    mobile_public_key_hex = "6249147f629130e026ab6732ba525088d15564df5e6e1b262d0fe1fe0899341e11472d92ca4db8e7d1ce89f367a41e0f2fed2d8f481d750a129dc80c2f630b6f409333ede85d667ec581cf0d5a9f3e3b9a9c8dc708ec522ee2176f79cb0e53b6255281f8de761f282fa11e0ad91d35bd39ec1afa0f63cf1cdf55f7cc765f4c1ef163f7c187f5d731f65440635129dbef204a609d345fbd5efd4642d9f54756dc52df18d9a204a197f9877699efbd3419c95ad59e8cd1ed423d5d6736d7ceca88e6382558effa6180f1182568252307a15943af05bd9a98c1a916aa744a71a6ffe950d091ce7a0aaa98a16edb3314b19dd18f2a584f7eb397eeba4c245c291293"
    server_public_key_hex = "581efd62213962de713420d12794ae421bf9e2fe0830584a3284199cbadbec06a0e9986f2530390e9f1da771548a6fbdd0028e434b6430b224fdbb6fe0983a904a3e7ae74a3440a2db097ae097a784b91eed5e30b63214a4885577847f000623de317827481bdd43a8ee9dcc3dab04820782c85fad656b9624b821ae2e6e7c39621b592873e3b796eb2d52c6869fe40672c3a7f556cce80f4c96c798962eab0cfade6d5cc956d4d54225e7776c23f46ccd1e5426b7079ad4ae046c1a945d20a6eb525225cfff9b29c3f88ef2480b9f5de93a793b4c438e391029756db384a687467023eb97ccf837674756e37911d7974acf733c29144bac7e58b1c67a91c510"
    
    print("=== STEP-BY-STEP DH DEBUGGING ===")
    print(f"Newsletter ID: {newsletter_id}")
    print(f"Mobile Public Key (hex): {mobile_public_key_hex[:50]}...")
    print(f"Server Public Key (hex): {server_public_key_hex[:50]}...")
    print()
    
    # Step 1: Get server private key from database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT private_key FROM newsletter_server_keys WHERE newsletter_id = %s",
            (newsletter_id,)
        )
        result = cursor.fetchone()
        if not result:
            print(f"ERROR: No server private key found for newsletter {newsletter_id}")
            return
        
        server_private_key = int(result[0])
        print(f"STEP 1 - Server Private Key: {server_private_key}")
        
    finally:
        cursor.close()
        conn.close()
    
    # Step 2: Parse mobile public key
    mobile_public_key = int(mobile_public_key_hex, 16)
    print(f"STEP 2 - Mobile Public Key (int): {mobile_public_key}")
    
    # Step 3: Verify server public key calculation
    server_public_key_calculated = pow(2, server_private_key, DH_PRIME)
    server_public_key_from_mobile = int(server_public_key_hex, 16)
    
    print(f"STEP 3a - Server Public Key (calculated): {server_public_key_calculated}")
    print(f"STEP 3b - Server Public Key (from mobile): {server_public_key_from_mobile}")
    print(f"STEP 3c - Server keys match: {server_public_key_calculated == server_public_key_from_mobile}")
    
    if server_public_key_calculated != server_public_key_from_mobile:
        print("ERROR: Server public keys don't match! This indicates a problem.")
        return
    
    # Step 4: Calculate shared secret (mobile app perspective)
    # Mobile app calculates: server_public^mobile_private mod P
    # Services calculate: mobile_public^server_private mod P
    # These should be equal due to DH property
    
    shared_secret_services = pow(mobile_public_key, server_private_key, DH_PRIME)
    print(f"STEP 4 - Shared Secret (services calc): {shared_secret_services}")
    
    # Step 5: Convert to bytes using mobile app method
    shared_secret_bytes = big_int_to_full_bytes(shared_secret_services)
    print(f"STEP 5a - Shared Secret Bytes Length: {len(shared_secret_bytes)}")
    print(f"STEP 5b - Shared Secret Bytes (hex): {shared_secret_bytes.hex()}")
    
    # Step 6: Derive AES key
    digest = hashlib.sha256(shared_secret_bytes).digest()
    aes_key = digest[:16]
    print(f"STEP 6a - SHA-256 Digest (hex): {digest.hex()}")
    print(f"STEP 6b - AES Key (first 16 bytes): {aes_key.hex()}")
    
    # Step 7: Analyze encrypted data structure
    encrypted_username = "JhTbwH1+aAY+KYo2878Yo2e0n9Uhrt2LHfY/98c6RW55VpeQl6YjNJF65GDAWtHW"
    encrypted_password = "9kXyhBG0Nu6zZqE7DCgeJj9IIvYDwFPYMM5KtrTdOnE="
    
    username_data = base64.b64decode(encrypted_username)
    password_data = base64.b64decode(encrypted_password)
    
    print(f"STEP 7a - Username encrypted length: {len(username_data)} bytes")
    print(f"STEP 7b - Username IV: {username_data[:16].hex()}")
    print(f"STEP 7c - Username ciphertext: {username_data[16:].hex()}")
    print(f"STEP 7d - Password encrypted length: {len(password_data)} bytes")
    print(f"STEP 7e - Password IV: {password_data[:16].hex()}")
    print(f"STEP 7f - Password ciphertext: {password_data[16:].hex()}")
    
    # Step 8: Check if ciphertext lengths are valid for AES blocks
    username_ciphertext_len = len(username_data) - 16
    password_ciphertext_len = len(password_data) - 16
    
    print(f"STEP 8a - Username ciphertext length: {username_ciphertext_len} (multiple of 16: {username_ciphertext_len % 16 == 0})")
    print(f"STEP 8b - Password ciphertext length: {password_ciphertext_len} (multiple of 16: {password_ciphertext_len % 16 == 0})")
    
    # Step 9: Expected mobile app values for comparison
    print("\n=== EXPECTED MOBILE APP VALUES ===")
    print("Mobile app should log these exact values:")
    print(f"- Shared Secret: {shared_secret_services}")
    print(f"- Shared Secret Bytes: {shared_secret_bytes.hex()}")
    print(f"- AES Key: {aes_key.hex()}")
    print(f"- Username IV: {username_data[:16].hex()}")
    print(f"- Password IV: {password_data[:16].hex()}")
    
    return {
        'server_private_key': server_private_key,
        'mobile_public_key': mobile_public_key,
        'shared_secret': shared_secret_services,
        'shared_secret_bytes': shared_secret_bytes.hex(),
        'aes_key': aes_key.hex(),
        'username_iv': username_data[:16].hex(),
        'password_iv': password_data[:16].hex()
    }

if __name__ == "__main__":
    debug_dh_calculation()