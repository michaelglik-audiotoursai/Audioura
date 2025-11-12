#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2
import hashlib

def decrypt_with_key_variations(encrypted_data, encryption_key):
    """Try different key formats"""
    
    # Decode base64
    encrypted_bytes = base64.b64decode(encrypted_data)
    
    # Key variations to try
    key_variations = [
        bytes.fromhex(encryption_key)[:16],  # First 16 bytes of hex
        bytes.fromhex(encryption_key)[:32],  # First 32 bytes of hex  
        hashlib.sha256(encryption_key.encode()).digest()[:16],  # SHA256 hash of key
        encryption_key.encode()[:16],  # Direct string encoding
    ]
    
    for i, key_bytes in enumerate(key_variations):
        try:
            if len(encrypted_bytes) < 16:
                continue
                
            # Extract IV and ciphertext
            iv = encrypted_bytes[:16]
            ciphertext = encrypted_bytes[16:]
            
            # Try AES-128
            if len(key_bytes) >= 16:
                cipher = AES.new(key_bytes[:16], AES.MODE_CBC, iv)
                decrypted_padded = cipher.decrypt(ciphertext)
                
                # Try different unpadding methods
                try:
                    decrypted = unpad(decrypted_padded, AES.block_size)
                    result = decrypted.decode('utf-8')
                    print(f"SUCCESS with key variation {i}: {result}")
                    return result
                except:
                    pass
                    
            # Try AES-256 if key is long enough
            if len(key_bytes) >= 32:
                cipher = AES.new(key_bytes[:32], AES.MODE_CBC, iv)
                decrypted_padded = cipher.decrypt(ciphertext)
                
                try:
                    decrypted = unpad(decrypted_padded, AES.block_size)
                    result = decrypted.decode('utf-8')
                    print(f"SUCCESS with AES-256 key variation {i}: {result}")
                    return result
                except:
                    pass
                    
        except Exception as e:
            continue
            
    print("All key variations failed")
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
    
    print("TRYING TO DECRYPT BOSTON GLOBE CREDENTIALS:")
    print(f"Key: {key}")
    print()
    
    print("Decrypting username...")
    username = decrypt_with_key_variations(enc_username, key)
    
    print("Decrypting password...")
    password = decrypt_with_key_variations(enc_password, key)
    
    print("\nFINAL RESULTS:")
    print(f"Username: {username}")
    print(f"Password: {password}")
else:
    print("No credentials found")

cursor.close()
conn.close()