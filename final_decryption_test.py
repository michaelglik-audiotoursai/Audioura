#!/usr/bin/env python3
"""
Final decryption test with exact mobile app specification (32-byte padding)
"""
import psycopg2
import os
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from dh_service_simple import (
    get_server_private_key_by_newsletter, 
    get_newsletter_id_from_article,
    DH_GENERATOR, DH_PRIME
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def decrypt_credentials_final(encrypted_data_b64, aes_key):
    """Decrypt using exact mobile app specification"""
    try:
        # Decode base64
        combined = base64.b64decode(encrypted_data_b64)
        
        print(f"Combined data length: {len(combined)} bytes")
        
        # Extract IV (first 16 bytes) and encrypted data
        iv = combined[:16]
        encrypted = combined[16:]
        
        print(f"IV: {iv.hex()}")
        print(f"Encrypted data length: {len(encrypted)} bytes")
        
        # Decrypt using AES-128-CBC
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        padded_plaintext = cipher.decrypt(encrypted)
        
        print(f"Padded plaintext: {padded_plaintext.hex()}")
        
        # Remove PKCS7 padding (padding value is in last byte)
        padding_length = padded_plaintext[-1]
        print(f"Padding length: {padding_length}")
        
        plaintext = padded_plaintext[:-padding_length]
        
        result = plaintext.decode('utf-8')
        print(f"Decrypted result: '{result}' (length: {len(result)})")
        
        return result
    except Exception as e:
        print(f"Decryption error details: {e}")
        raise Exception(f"Decryption failed: {e}")

def test_final_decryption():
    """Test with both byte length methods"""
    
    device_id = "USER-281301397"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get stored credentials
    cursor.execute("""
        SELECT article_id, domain, mobile_public_key, encrypted_username, encrypted_password
        FROM user_subscription_credentials 
        WHERE device_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (device_id,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not result:
        print("No credentials found")
        return
    
    article_id, domain, mobile_public_key_hex, enc_username_b64, enc_password_b64 = result
    
    print(f"Testing final decryption for device: {device_id}")
    print(f"Domain: {domain}")
    print(f"Encrypted username: {enc_username_b64}")
    print(f"Encrypted password: {enc_password_b64}")
    print("=" * 60)
    
    # Get newsletter_id and server private key
    newsletter_id = get_newsletter_id_from_article(article_id)
    server_private_key = get_server_private_key_by_newsletter(newsletter_id)
    
    # Convert mobile public key from hex (no 0x prefix)
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret using DH
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    
    print(f"Shared Secret: {str(shared_secret)[:50]}...")
    
    # Try both methods as per mobile app spec
    
    # Method 1: Pad to exactly 32 bytes (mobile app specification)
    print("\n=== METHOD 1: 32-byte padding (mobile app spec) ===")
    try:
        # Calculate byte length and pad to 32 if needed
        bit_length = shared_secret.bit_length()
        byte_length = (bit_length + 7) // 8
        
        if byte_length <= 32:
            # Pad with leading zeros to 32 bytes
            shared_secret_bytes = shared_secret.to_bytes(32, byteorder='big')
        else:
            # Use actual length if > 32 bytes
            shared_secret_bytes = shared_secret.to_bytes(byte_length, byteorder='big')
        
        hash_digest = hashlib.sha256(shared_secret_bytes).digest()
        aes_key = hash_digest[:16]
        
        print(f"Byte length: {len(shared_secret_bytes)}")
        print(f"AES Key (hex): {aes_key.hex()}")
        
        print("\nTesting Username:")
        username = decrypt_credentials_final(enc_username_b64, aes_key)
        
        print("\nTesting Password:")
        password = decrypt_credentials_final(enc_password_b64, aes_key)
        
        print(f"\n✅ FINAL RESULTS:")
        print(f"Username: '{username}'")
        print(f"Password: '{password}'")
        
    except Exception as e:
        print(f"Method 1 failed: {e}")
    
    # Method 2: Use actual byte length
    print(f"\n=== METHOD 2: Actual byte length ({byte_length} bytes) ===")
    try:
        shared_secret_bytes = shared_secret.to_bytes(byte_length, byteorder='big')
        hash_digest = hashlib.sha256(shared_secret_bytes).digest()
        aes_key = hash_digest[:16]
        
        print(f"AES Key (hex): {aes_key.hex()}")
        
        username = decrypt_credentials_final(enc_username_b64, aes_key)
        password = decrypt_credentials_final(enc_password_b64, aes_key)
        
        print(f"\n✅ METHOD 2 RESULTS:")
        print(f"Username: '{username}'")
        print(f"Password: '{password}'")
        
    except Exception as e:
        print(f"Method 2 failed: {e}")

if __name__ == "__main__":
    test_final_decryption()