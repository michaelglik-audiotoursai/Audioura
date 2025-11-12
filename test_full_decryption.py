#!/usr/bin/env python3
"""
Test full credential decryption with proper key derivation matching mobile app
"""
import psycopg2
import os
import hashlib
import base64
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

def test_decryption():
    """Test credential decryption with different key derivation methods"""
    
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
    
    print(f"Article ID: {article_id}")
    print(f"Domain: {domain}")
    print(f"Mobile Public Key: {mobile_public_key_hex[:50]}...")
    print(f"Encrypted Username: {enc_username_b64}")
    print(f"Encrypted Password: {enc_password_b64}")
    
    # Get newsletter_id and server private key
    newsletter_id = get_newsletter_id_from_article(article_id)
    server_private_key = get_server_private_key_by_newsletter(newsletter_id)
    
    print(f"Newsletter ID: {newsletter_id}")
    print(f"Server Private Key: {server_private_key}")
    
    # Convert mobile public key from hex
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret using DH
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    
    print(f"Shared Secret: {shared_secret}")
    
    # Try different key derivation methods
    print("\n=== Testing Key Derivation Methods ===")
    
    # Method 1: SHA-256 of shared secret string
    key1 = hashlib.sha256(str(shared_secret).encode()).digest()[:16]
    print(f"Method 1 (SHA-256 string): {key1.hex()}")
    
    # Method 2: SHA-256 of shared secret bytes (big endian)
    shared_secret_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
    key2 = hashlib.sha256(shared_secret_bytes).digest()[:16]
    print(f"Method 2 (SHA-256 bytes BE): {key2.hex()}")
    
    # Method 3: SHA-256 of shared secret hex string
    shared_secret_hex = hex(shared_secret)[2:]  # Remove 0x prefix
    key3 = hashlib.sha256(shared_secret_hex.encode()).digest()[:16]
    print(f"Method 3 (SHA-256 hex string): {key3.hex()}")
    
    # Method 4: Direct shared secret modulo (simple method)
    key4 = (shared_secret % (2**128)).to_bytes(16, 'big')
    print(f"Method 4 (Direct modulo): {key4.hex()}")
    
    print(f"\nEncrypted data lengths:")
    print(f"Username: {len(base64.b64decode(enc_username_b64))} bytes")
    print(f"Password: {len(base64.b64decode(enc_password_b64))} bytes")

if __name__ == "__main__":
    test_decryption()