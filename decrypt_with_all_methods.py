#!/usr/bin/env python3
"""
Test decryption with all key derivation methods to find the correct one
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

def try_decrypt(encrypted_data_b64, aes_key, label):
    """Try to decrypt with given AES key"""
    try:
        encrypted_bytes = base64.b64decode(encrypted_data_b64)
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        result = decrypted.decode('utf-8')
        
        print(f"✅ {label}: SUCCESS - '{result}'")
        return result
    except Exception as e:
        print(f"❌ {label}: FAILED - {str(e)}")
        return None

def test_all_decryption_methods():
    """Test all key derivation methods to find the correct one"""
    
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
    
    print(f"Testing decryption for device: {device_id}")
    print(f"Domain: {domain}")
    print("=" * 60)
    
    # Get newsletter_id and server private key
    newsletter_id = get_newsletter_id_from_article(article_id)
    server_private_key = get_server_private_key_by_newsletter(newsletter_id)
    
    # Convert mobile public key from hex
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret using DH
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    
    # Test different key derivation methods
    keys = {
        "Method 1 (SHA-256 string)": hashlib.sha256(str(shared_secret).encode()).digest()[:16],
        "Method 2 (SHA-256 bytes BE)": hashlib.sha256(shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')).digest()[:16],
        "Method 3 (SHA-256 hex string)": hashlib.sha256(hex(shared_secret)[2:].encode()).digest()[:16],
        "Method 4 (Direct modulo)": (shared_secret % (2**128)).to_bytes(16, 'big')
    }
    
    print("TESTING USERNAME DECRYPTION:")
    print("-" * 40)
    for method, key in keys.items():
        try_decrypt(enc_username_b64, key, method)
    
    print("\nTESTING PASSWORD DECRYPTION:")
    print("-" * 40)
    for method, key in keys.items():
        try_decrypt(enc_password_b64, key, method)

if __name__ == "__main__":
    test_all_decryption_methods()