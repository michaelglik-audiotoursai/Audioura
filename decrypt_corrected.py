#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2

def decrypt_mobile_credential(encrypted_base64, device_key_hex):
    """Decrypt using EXACT mobile app method with PyCrypto"""
    try:
        # Process key EXACTLY like mobile app
        key_hex = device_key_hex[:32]  # First 32 hex chars (16 bytes)
        key_bytes = bytes.fromhex(key_hex)
        
        print(f"Device key (64 chars): {device_key_hex}")
        print(f"Processed key (32 chars): {key_hex}")
        print(f"Key bytes: {key_bytes.hex()}")
        print(f"Key bytes length: {len(key_bytes)}")
        
        # Decode Base64
        encrypted_data = base64.b64decode(encrypted_base64)
        print(f"Encrypted data length: {len(encrypted_data)} bytes")
        
        # Extract IV (first 16 bytes) and ciphertext (rest)
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]
        
        print(f"IV: {iv.hex()}")
        print(f"IV length: {len(iv)} bytes")
        print(f"Ciphertext: {ciphertext.hex()}")
        print(f"Ciphertext length: {len(ciphertext)} bytes")
        
        # Setup AES-128-CBC cipher
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        
        # Decrypt
        padded_plaintext = cipher.decrypt(ciphertext)
        print(f"Padded plaintext: {padded_plaintext.hex()}")
        
        # Remove PKCS7 padding
        plaintext = unpad(padded_plaintext, AES.block_size)
        print(f"Final plaintext bytes: {plaintext.hex()}")
        
        result = plaintext.decode('utf-8')
        print(f"Decoded text: '{result}'")
        return result
        
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

# Connect to database and test
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
    enc_username, enc_password, device_key = result
    
    print("=== MOBILE APP ENCRYPTION DECRYPTION TEST ===")
    print("Using CORRECTED mobile app key processing method\n")
    
    print("=== Decrypting Boston Globe Username ===")
    username = decrypt_mobile_credential(enc_username, device_key)
    
    print("\n=== Decrypting Boston Globe Password ===")
    password = decrypt_mobile_credential(enc_password, device_key)
    
    print("\n=== FINAL RESULTS ===")
    if username and password:
        print("SUCCESS! Credentials decrypted:")
        print(f"   Domain: bostonglobe.com")
        print(f"   Device: USER-281301397")
        print(f"   Username: '{username}'")
        print(f"   Password: '{password}'")
        print("\nMobile app encryption/decryption is working correctly!")
    else:
        print("FAILED: Could not decrypt credentials")

cursor.close()
conn.close()