#!/usr/bin/env python3
"""
Credential Decryption Utility
Decrypts stored subscription credentials for testing purposes
"""

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2
import os

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def decrypt_credential(encrypted_data, encryption_key):
    """Decrypt credential using AES-128"""
    try:
        # Convert hex key to bytes
        key_bytes = bytes.fromhex(encryption_key)[:16]  # AES-128 uses 16 bytes
        
        # Decode base64 encrypted data
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract IV (first 16 bytes) and ciphertext
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        
        # Decrypt
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(ciphertext)
        
        # Remove padding
        decrypted = unpad(decrypted_padded, AES.block_size)
        
        return decrypted.decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get latest credentials for USER-281301397
    cursor.execute("""
        SELECT usc.device_id, usc.domain, usc.encrypted_username, usc.encrypted_password,
               dek.encryption_key, usc.created_at
        FROM user_subscription_credentials usc
        JOIN device_encryption_keys dek ON usc.device_id = dek.device_id
        WHERE usc.device_id = 'USER-281301397'
        ORDER BY usc.created_at DESC
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    if not result:
        print("No credentials found for USER-281301397")
        return
    
    device_id, domain, enc_username, enc_password, encryption_key, created_at = result
    
    print(f"Decrypting credentials for {device_id} ({domain})")
    print(f"Submitted at: {created_at}")
    print(f"Encryption key: {encryption_key}")
    print()
    
    # Decrypt username
    username = decrypt_credential(enc_username, encryption_key)
    password = decrypt_credential(enc_password, encryption_key)
    
    print("DECRYPTED CREDENTIALS:")
    print(f"Domain: {domain}")
    print(f"Username: {username}")
    print(f"Password: {password}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()