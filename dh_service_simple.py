#!/usr/bin/env python3
"""
Simple Diffie-Hellman Service without PyCrypto dependency
Uses only standard library for basic functionality
"""

import secrets
import hashlib
import base64
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
DH_GENERATOR = 2

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def generate_server_keypair():
    """Generate server DH key pair"""
    private_key = secrets.randbits(256)
    public_key = pow(DH_GENERATOR, private_key, DH_PRIME)
    return private_key, public_key

def calculate_shared_secret(client_public_key_hex, server_private_key):
    """Calculate DH shared secret"""
    client_public_key = int(client_public_key_hex, 16)
    shared_secret = pow(client_public_key, server_private_key, DH_PRIME)
    return shared_secret

def derive_aes_key(shared_secret):
    """Derive AES-128 key from shared secret using SHA-256"""
    shared_secret_bytes = shared_secret.to_bytes(256, byteorder='big')
    digest = hashlib.sha256(shared_secret_bytes).digest()
    aes_key = digest[:16]
    return aes_key

def store_server_private_key(newsletter_id, server_private_key):
    """Store server private key for newsletter session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS newsletter_server_keys (
                newsletter_id INTEGER PRIMARY KEY,
                private_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        cursor.execute("""
            INSERT INTO newsletter_server_keys (newsletter_id, private_key, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (newsletter_id) DO UPDATE SET 
                private_key = EXCLUDED.private_key, 
                created_at = NOW()
        """, (newsletter_id, str(server_private_key)))
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_server_private_key_by_newsletter(newsletter_id):
    """Get stored server private key for newsletter"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT private_key FROM newsletter_server_keys 
            WHERE newsletter_id = %s
        """, (newsletter_id,))
        
        result = cursor.fetchone()
        if result:
            return int(result[0])
        return None
    finally:
        cursor.close()
        conn.close()

def store_device_aes_key(device_id, aes_key):
    """Store derived AES key for device"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dh_aes_keys (
                device_id VARCHAR(255) PRIMARY KEY,
                aes_key VARCHAR(32) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        aes_key_hex = aes_key.hex()
        
        cursor.execute("""
            INSERT INTO dh_aes_keys (device_id, aes_key, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (device_id) DO UPDATE SET 
                aes_key = EXCLUDED.aes_key, 
                created_at = NOW()
        """, (device_id, aes_key_hex))
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_newsletter_id_from_article(article_id):
    """Get newsletter_id from article_id via newsletters_article_link table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT nal.newsletters_id 
            FROM newsletters_article_link nal
            WHERE nal.article_requests_id = %s
            LIMIT 1
        """, (article_id,))
        
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    finally:
        cursor.close()
        conn.close()

def decrypt_credentials_with_mobile_key(newsletter_id, mobile_public_key_hex, encrypted_username, encrypted_password):
    """Decrypt credentials using mobile public key and newsletter server private key"""
    import base64
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    
    # Get server private key for this newsletter
    server_private_key = get_server_private_key_by_newsletter(newsletter_id)
    if not server_private_key:
        raise ValueError(f"No server private key found for newsletter {newsletter_id}")
    
    # Parse mobile public key (hex string without 0x prefix)
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret: mobile_public^server_private mod prime
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    
    # Derive AES key using exact mobile app method
    shared_secret_bytes = shared_secret.to_bytes(256, byteorder='big')
    digest = hashlib.sha256(shared_secret_bytes).digest()
    aes_key = digest[:16]  # AES-128
    
    try:
        # Decrypt username
        username_data = base64.b64decode(encrypted_username)
        username_iv = username_data[:16]
        username_ciphertext = username_data[16:]
        
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(username_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        username_padded = decryptor.update(username_ciphertext) + decryptor.finalize()
        
        # Remove PKCS7 padding
        padding_length = username_padded[-1]
        if padding_length > 16 or padding_length == 0:
            raise ValueError(f"Invalid username padding: {padding_length}")
        username = username_padded[:-padding_length].decode('utf-8')
        
        # Decrypt password
        password_data = base64.b64decode(encrypted_password)
        password_iv = password_data[:16]
        password_ciphertext = password_data[16:]
        
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(password_iv), backend=default_backend())
        decryptor = cipher.decryptor()
        password_padded = decryptor.update(password_ciphertext) + decryptor.finalize()
        
        # Remove PKCS7 padding
        padding_length = password_padded[-1]
        if padding_length > 16 or padding_length == 0:
            raise ValueError(f"Invalid password padding: {padding_length}")
        password = password_padded[:-padding_length].decode('utf-8')
        
        return {
            'success': True,
            'username': username,
            'password': password,
            'aes_key': aes_key.hex(),
            'shared_secret': str(shared_secret)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'aes_key': aes_key.hex(),
            'shared_secret': str(shared_secret)
        }