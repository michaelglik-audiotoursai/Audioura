#!/usr/bin/env python3
"""
Fixed credential decryption with proper byte length handling
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

def decrypt_credentials_correct(encrypted_data_b64, aes_key):
    """Decrypt using exact mobile app specification"""
    try:
        # Decode base64
        combined = base64.b64decode(encrypted_data_b64)
        
        # Extract IV (first 16 bytes) and encrypted data
        iv = combined[:16]
        encrypted = combined[16:]
        
        # Decrypt using AES-128-CBC
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        padded_plaintext = cipher.decrypt(encrypted)
        
        # Remove PKCS7 padding (padding value is in last byte)
        padding_length = padded_plaintext[-1]
        plaintext = padded_plaintext[:-padding_length]
        
        return plaintext.decode('utf-8')
    except Exception as e:
        raise Exception(f"Decryption failed: {e}")

def test_fixed_decryption():
    """Test decryption with proper byte length handling"""
    
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
    
    print(f"Testing fixed decryption for device: {device_id}")
    print(f"Domain: {domain}")
    print("=" * 60)
    
    # Get newsletter_id and server private key
    newsletter_id = get_newsletter_id_from_article(article_id)
    server_private_key = get_server_private_key_by_newsletter(newsletter_id)
    
    # Convert mobile public key from hex (no 0x prefix)
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret using DH
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    
    print(f"Shared Secret: {str(shared_secret)[:50]}...")
    
    # Calculate required byte length for shared secret
    bit_length = shared_secret.bit_length()
    byte_length = (bit_length + 7) // 8
    print(f"Shared secret bit length: {bit_length}")
    print(f"Required byte length: {byte_length}")
    
    # CORRECTED KEY DERIVATION per mobile app specification:
    # 1. Convert shared secret to bytes (use actual length, not fixed 32)
    shared_secret_bytes = shared_secret.to_bytes(byte_length, byteorder='big')
    
    # 2. SHA-256 hash of those bytes
    hash_digest = hashlib.sha256(shared_secret_bytes).digest()
    
    # 3. Take first 16 bytes as AES-128 key
    aes_key = hash_digest[:16]
    
    print(f"AES Key (hex): {aes_key.hex()}")
    
    # Test decryption
    print("\nTesting Username Decryption:")
    print("-" * 40)
    try:
        username = decrypt_credentials_correct(enc_username_b64, aes_key)
        print(f"✅ USERNAME: {username}")
    except Exception as e:
        print(f"❌ Username decryption failed: {e}")
    
    print("\nTesting Password Decryption:")
    print("-" * 40)
    try:
        password = decrypt_credentials_correct(enc_password_b64, aes_key)
        print(f"✅ PASSWORD: {password}")
    except Exception as e:
        print(f"❌ Password decryption failed: {e}")

if __name__ == "__main__":
    test_fixed_decryption()