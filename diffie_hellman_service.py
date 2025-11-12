#!/usr/bin/env python3
"""
Diffie-Hellman Key Exchange Service
Implements secure key exchange for subscription credentials
"""

import secrets
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
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
    # Generate 256-bit private key
    private_key = secrets.randbits(256)
    
    # Calculate public key: g^private mod p
    public_key = pow(DH_GENERATOR, private_key, DH_PRIME)
    
    return private_key, public_key

def calculate_shared_secret(client_public_key_hex, server_private_key):
    """Calculate DH shared secret"""
    client_public_key = int(client_public_key_hex, 16)
    
    # Calculate shared secret: client_public^server_private mod p
    shared_secret = pow(client_public_key, server_private_key, DH_PRIME)
    
    return shared_secret

def derive_aes_key(shared_secret):
    """Derive AES-128 key from shared secret using SHA-256"""
    # Convert shared secret to 32-byte representation
    shared_secret_bytes = shared_secret.to_bytes(256, byteorder='big')
    
    # Derive AES key using SHA-256
    digest = hashlib.sha256(shared_secret_bytes).digest()
    
    # Use first 16 bytes for AES-128
    aes_key = digest[:16]
    
    return aes_key

def store_server_private_key(device_id, server_private_key):
    """Store server private key for device session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Store or update server private key
        cursor.execute("""
            INSERT INTO dh_server_keys (device_id, private_key, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (device_id) 
            UPDATE SET private_key = %s, created_at = NOW()
        """, (device_id, str(server_private_key), str(server_private_key)))
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_server_private_key(device_id):
    """Get stored server private key for device"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT private_key FROM dh_server_keys 
            WHERE device_id = %s
        """, (device_id,))
        
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
        # Store AES key as hex
        aes_key_hex = aes_key.hex()
        
        cursor.execute("""
            INSERT INTO dh_aes_keys (device_id, aes_key, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (device_id)
            UPDATE SET aes_key = %s, created_at = NOW()
        """, (device_id, aes_key_hex, aes_key_hex))
        
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def get_device_aes_key(device_id):
    """Get derived AES key for device"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT aes_key FROM dh_aes_keys 
            WHERE device_id = %s
        """, (device_id,))
        
        result = cursor.fetchone()
        if result:
            return bytes.fromhex(result[0])
        return None
    finally:
        cursor.close()
        conn.close()

def decrypt_dh_credential(encrypted_base64, aes_key):
    """Decrypt credential using DH-derived AES key"""
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV and ciphertext
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # AES-128-CBC decrypt
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)
    
    # Remove PKCS7 padding
    plaintext = unpad(padded_plaintext, AES.block_size)
    
    return plaintext.decode('utf-8')

def decrypt_credentials(device_id, encrypted_username, encrypted_password):
    """Decrypt credentials using DH-derived key"""
    # Get derived AES key for this device
    aes_key = get_device_aes_key(device_id)
    
    if not aes_key:
        raise ValueError(f"No AES key found for device {device_id}")
    
    # Decrypt credentials
    username = decrypt_dh_credential(encrypted_username, aes_key)
    password = decrypt_dh_credential(encrypted_password, aes_key)
    
    return username, password

# Database schema creation
def create_dh_tables():
    """Create DH key exchange tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Server private keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dh_server_keys (
                device_id VARCHAR(255) PRIMARY KEY,
                private_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Derived AES keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dh_aes_keys (
                device_id VARCHAR(255) PRIMARY KEY,
                aes_key VARCHAR(32) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        conn.commit()
        print("DH tables created successfully")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Create tables
    create_dh_tables()
    
    # Test DH key exchange
    print("=== DIFFIE-HELLMAN KEY EXCHANGE TEST ===")
    
    # Generate server key pair
    server_private, server_public = generate_server_keypair()
    print(f"Server public key: {hex(server_public)}")
    
    # Simulate client key pair (for testing)
    client_private = secrets.randbits(256)
    client_public = pow(DH_GENERATOR, client_private, DH_PRIME)
    print(f"Client public key: {hex(client_public)}")
    
    # Calculate shared secrets (both sides)
    server_shared = calculate_shared_secret(hex(client_public), server_private)
    client_shared = pow(server_public, client_private, DH_PRIME)
    
    print(f"Shared secrets match: {server_shared == client_shared}")
    
    # Derive AES keys
    server_aes = derive_aes_key(server_shared)
    client_aes = derive_aes_key(client_shared)
    
    print(f"AES keys match: {server_aes == client_aes}")
    print(f"AES key: {server_aes.hex()}")