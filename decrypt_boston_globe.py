#!/usr/bin/env python3
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import psycopg2

def decrypt_credential(encrypted_base64, key_bytes):
    """Decrypt using mobile app's exact method"""
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV (first 16 bytes) and ciphertext (rest)
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # Setup AES-128-CBC cipher
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    decryptor = cipher.decryptor()
    
    # Decrypt
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    
    # Remove PKCS7 padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    
    return plaintext.decode('utf-8')

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    database='audiotours', 
    user='admin',
    password='password123',
    port='5433'
)

cursor = conn.cursor()
cursor.execute("""
    SELECT usc.encrypted_username, usc.encrypted_password, dek.encryption_key
    FROM user_subscription_credentials usc
    JOIN device_encryption_keys dek ON usc.device_id = dek.device_id
    WHERE usc.device_id = 'USER-281301397'
    ORDER BY usc.created_at DESC LIMIT 1
""")

result = cursor.fetchone()
if result:
    enc_username, enc_password, hex_key = result
    
    # Process key exactly like mobile app: first 32 hex chars (16 bytes)
    key_bytes = bytes.fromhex(hex_key[:32])
    
    print("BOSTON GLOBE CREDENTIALS DECRYPTED:")
    print(f"Domain: bostonglobe.com")
    print(f"Username: {decrypt_credential(enc_username, key_bytes)}")
    print(f"Password: {decrypt_credential(enc_password, key_bytes)}")
else:
    print("No credentials found")

cursor.close()
conn.close()