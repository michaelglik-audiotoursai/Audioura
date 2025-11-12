#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2

def decrypt_credential(encrypted_data, encryption_key):
    """Decrypt credential with multiple padding strategies"""
    try:
        # Convert hex key to bytes (first 16 bytes for AES-128)
        key_bytes = bytes.fromhex(encryption_key)[:16]
        
        # Decode base64
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract IV and ciphertext
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        
        # Decrypt
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(ciphertext)
        
        # Try unpadding
        try:
            decrypted = unpad(decrypted_padded, AES.block_size)
            return decrypted.decode('utf-8')
        except:
            # Try manual padding removal
            padding_length = decrypted_padded[-1]
            if padding_length <= 16:
                decrypted = decrypted_padded[:-padding_length]
                return decrypted.decode('utf-8')
            else:
                # No padding, return as is
                return decrypted_padded.decode('utf-8').rstrip('\x00')
                
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

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
    enc_username, enc_password, key = result
    
    print("BOSTON GLOBE CREDENTIALS:")
    print(f"Username: {decrypt_credential(enc_username, key)}")
    print(f"Password: {decrypt_credential(enc_password, key)}")
else:
    print("No credentials found")

cursor.close()
conn.close()