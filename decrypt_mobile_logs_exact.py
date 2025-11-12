#!/usr/bin/env python3
"""
Decrypt using exact values from mobile app logs v1.2.8.19
"""

import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import psycopg2
import os

# RFC 3526 Group 14 parameters
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

def decrypt_with_mobile_logs():
    """Decrypt using exact values from mobile app logs"""
    
    # Exact values from mobile app logs v1.2.8.19
    server_public_key_hex = "581efd62213962de713420d12794ae421bf9e2fe0830584a3284199cbadbec06a0e9986f2530390e9f1da771548a6fbdd0028e434b6430b224fdbb6fe0983a904a3e7ae74a3440a2db097ae097a784b91eed5e30b63214a4885577847f000623de317827481bdd43a8ee9dcc3dab04820782c85fad656b9624b821ae2e6e7c39621b592873e3b796eb2d52c6869fe40672c3a7f556cce80f4c96c798962eab0cfade6d5cc956d4d54225e7776c23f46ccd1e5426b7079ad4ae046c1a945d20a6eb525225cfff9b29c3f88ef2480b9f5de93a793b4c438e391029756db384a687467023eb97ccf837674756e37911d7974acf733c29144bac7e58b1c67a91c510"
    mobile_public_key_hex = "fe4658dbb616a427b6bfc1c7c12cd8d1b7e79820ed1edb2af788377d5a3438aaa6fb0c0ddbbdc5c4834cc5fe97d9d1c60f55458bab8d2822e6249864804ef55aa23a1fd5004f09d58ac831c979f41fdedf4e592ad6459ea5185e658235712f20ef046fdc83f70ae955a66bfc4504e6315b103a228d0ec4e0e81145d378c8b0acf429aacdee0492086610ab1c55bbc89d21f3f2cb90a562beb9f1f20e90229a1c2762b9f99113b85dfc0151ef0981db942cc38cf58f6f8c4d48ed1ed4e7ce539cd9264c09877f5ab12961496cae0e9cb62634bd3f398a18ea7f061aa0e12cb5d6f802b4e158f6ced6428986138a1f3632a24026b9b91e4f701b18b92ccc1d3de5"
    encrypted_username = "vG/9FfKMO7oNEDej/X3Lp554xj2B+j6rUXqm79Mc0TIM4ZrxpVJE8qZFC9ERXyGU"
    encrypted_password = "rb/rgRFhSYg3HvOxbFfaKklfreJ8fbYUSecsh8RnOr4="
    
    # Known plaintext from logs
    expected_username = "glikfamily@gmail.com"
    expected_password = "Eight2Four"
    
    print("=== DECRYPTION WITH MOBILE APP LOGS ===")
    print(f"Expected Username: {expected_username}")
    print(f"Expected Password: {expected_password}")
    print()
    
    # Get server private key for newsletter 169
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )
    cursor = conn.cursor()
    
    cursor.execute("SELECT private_key FROM newsletter_server_keys WHERE newsletter_id = 169")
    result = cursor.fetchone()
    server_private_key = int(result[0])
    
    cursor.close()
    conn.close()
    
    print(f"Server Private Key: {server_private_key}")
    
    # Parse keys
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    print(f"Shared Secret: {shared_secret}")
    
    # Derive AES key
    shared_secret_bytes = shared_secret.to_bytes(256, byteorder='big')
    digest = hashlib.sha256(shared_secret_bytes).digest()
    aes_key = digest[:16]
    
    print(f"Shared Secret Bytes (hex): {shared_secret_bytes.hex()}")
    print(f"AES Key: {aes_key.hex()}")
    print()
    
    # Decrypt username
    try:
        username_data = base64.b64decode(encrypted_username)
        username_iv = username_data[:16]
        username_ciphertext = username_data[16:]
        
        print(f"Username IV: {username_iv.hex()}")
        print(f"Username Ciphertext: {username_ciphertext.hex()}")
        
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(username_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        username_padded = decryptor.update(username_ciphertext) + decryptor.finalize()
        
        padding_length = username_padded[-1]
        print(f"Username Padding Length: {padding_length}")
        
        if 1 <= padding_length <= 16:
            username_decrypted = username_padded[:-padding_length].decode('utf-8')
            print(f"Username Decrypted: '{username_decrypted}'")
            print(f"Username Match: {username_decrypted == expected_username}")
        else:
            print(f"Invalid username padding: {padding_length}")
            
    except Exception as e:
        print(f"Username decryption failed: {e}")
    
    print()
    
    # Decrypt password
    try:
        password_data = base64.b64decode(encrypted_password)
        password_iv = password_data[:16]
        password_ciphertext = password_data[16:]
        
        print(f"Password IV: {password_iv.hex()}")
        print(f"Password Ciphertext: {password_ciphertext.hex()}")
        
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(password_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        password_padded = decryptor.update(password_ciphertext) + decryptor.finalize()
        
        padding_length = password_padded[-1]
        print(f"Password Padding Length: {padding_length}")
        
        if 1 <= padding_length <= 16:
            password_decrypted = password_padded[:-padding_length].decode('utf-8')
            print(f"Password Decrypted: '{password_decrypted}'")
            print(f"Password Match: {password_decrypted == expected_password}")
        else:
            print(f"Invalid password padding: {padding_length}")
            
    except Exception as e:
        print(f"Password decryption failed: {e}")

if __name__ == "__main__":
    decrypt_with_mobile_logs()