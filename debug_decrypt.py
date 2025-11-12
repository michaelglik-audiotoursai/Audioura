#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
import psycopg2

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
    
    print(f"Hex key (64 chars): {hex_key}")
    print(f"First 32 chars: {hex_key[:32]}")
    
    # Process key exactly like mobile app: first 32 hex chars (16 bytes)
    key_bytes = bytes.fromhex(hex_key[:32])
    print(f"Key bytes (16): {key_bytes.hex()}")
    
    # Debug username decryption
    print(f"\nUsername encrypted (base64): {enc_username}")
    encrypted_data = base64.b64decode(enc_username)
    print(f"Encrypted data length: {len(encrypted_data)}")
    print(f"Encrypted data (hex): {encrypted_data.hex()}")
    
    # Extract IV and ciphertext
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    print(f"IV (16 bytes): {iv.hex()}")
    print(f"Ciphertext ({len(ciphertext)} bytes): {ciphertext.hex()}")
    
    # Decrypt
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(ciphertext)
    print(f"Decrypted (hex): {decrypted.hex()}")
    print(f"Decrypted (raw): {decrypted}")
    
    # Try to decode as UTF-8
    try:
        text = decrypted.decode('utf-8')
        print(f"Decoded text: '{text}'")
    except Exception as e:
        print(f"UTF-8 decode error: {e}")
        
    # Check padding manually
    if len(decrypted) > 0:
        last_byte = decrypted[-1]
        print(f"Last byte (padding?): {last_byte}")
        if last_byte <= 16:
            try:
                unpadded = decrypted[:-last_byte]
                text = unpadded.decode('utf-8')
                print(f"Manual unpadded text: '{text}'")
            except Exception as e:
                print(f"Manual unpad error: {e}")

cursor.close()
conn.close()