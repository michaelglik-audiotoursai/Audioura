#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2

def decrypt_credential(encrypted_base64, key_bytes):
    """Decrypt using mobile app's exact method with PyCrypto"""
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV (first 16 bytes) and ciphertext (rest)
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # Setup AES-128-CBC cipher
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    
    # Decrypt
    padded_plaintext = cipher.decrypt(ciphertext)
    
    # Remove PKCS7 padding
    plaintext = unpad(padded_plaintext, AES.block_size)
    
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
    
    print("BOSTON GLOBE CREDENTIALS SUCCESSFULLY DECRYPTED:")
    print(f"Domain: bostonglobe.com")
    print(f"Username: {decrypt_credential(enc_username, key_bytes)}")
    print(f"Password: {decrypt_credential(enc_password, key_bytes)}")
else:
    print("No credentials found")

cursor.close()
conn.close()