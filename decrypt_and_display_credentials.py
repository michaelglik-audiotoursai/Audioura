#!/usr/bin/env python3
"""
Decrypt and display stored subscription credentials for verification
"""
import psycopg2
import os
from dh_service_simple import (
    get_server_private_key_by_newsletter, 
    get_newsletter_id_from_article,
    DH_GENERATOR, DH_PRIME
)
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import hashlib

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def decrypt_credentials_full(device_id):
    """Decrypt and display actual username/password for verification"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get stored credentials
    cursor.execute("""
        SELECT article_id, domain, mobile_public_key, encrypted_username, encrypted_password
        FROM user_subscription_credentials 
        WHERE device_id = %s
        ORDER BY created_at DESC
    """, (device_id,))
    
    credentials = cursor.fetchall()
    cursor.close()
    conn.close()
    
    if not credentials:
        print(f"No credentials found for device: {device_id}")
        return
    
    print(f"Found {len(credentials)} credential(s) for device: {device_id}")
    print("=" * 60)
    
    for article_id, domain, mobile_public_key_hex, enc_username_b64, enc_password_b64 in credentials:
        print(f"\nArticle ID: {article_id}")
        print(f"Domain: {domain}")
        
        try:
            # Get newsletter_id for this article
            newsletter_id = get_newsletter_id_from_article(article_id)
            if not newsletter_id:
                print("ERROR: Cannot find newsletter for this article")
                continue
            
            print(f"Newsletter ID: {newsletter_id}")
            
            # Get server private key
            server_private_key = get_server_private_key_by_newsletter(newsletter_id)
            if not server_private_key:
                print("ERROR: No server private key found for newsletter")
                continue
            
            # Convert mobile public key from hex
            mobile_public_key = int(mobile_public_key_hex, 16)
            
            # Calculate shared secret using DH
            shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
            
            # Derive AES key from shared secret
            aes_key = hashlib.sha256(str(shared_secret).encode()).digest()[:16]  # AES-128
            
            print(f"AES Key (hex): {aes_key.hex()}")
            
            # Decrypt username
            try:
                enc_username_bytes = base64.b64decode(enc_username_b64)
                iv_username = enc_username_bytes[:16]
                ciphertext_username = enc_username_bytes[16:]
                
                cipher_username = AES.new(aes_key, AES.MODE_CBC, iv_username)
                decrypted_username = unpad(cipher_username.decrypt(ciphertext_username), AES.block_size)
                username = decrypted_username.decode('utf-8')
                
                print(f"✅ USERNAME: {username}")
                
            except Exception as e:
                print(f"❌ Username decryption failed: {e}")
            
            # Decrypt password
            try:
                enc_password_bytes = base64.b64decode(enc_password_b64)
                iv_password = enc_password_bytes[:16]
                ciphertext_password = enc_password_bytes[16:]
                
                cipher_password = AES.new(aes_key, AES.MODE_CBC, iv_password)
                decrypted_password = unpad(cipher_password.decrypt(ciphertext_password), AES.block_size)
                password = decrypted_password.decode('utf-8')
                
                print(f"✅ PASSWORD: {password}")
                
            except Exception as e:
                print(f"❌ Password decryption failed: {e}")
                
        except Exception as e:
            print(f"❌ Decryption error: {e}")
        
        print("-" * 40)

if __name__ == "__main__":
    device_id = "USER-281301397"
    decrypt_credentials_full(device_id)