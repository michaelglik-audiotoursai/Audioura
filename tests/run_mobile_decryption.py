#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def decrypt_mobile_credential(encrypted_base64, device_key_hex):
    """Decrypt using exact mobile app method with PyCrypto"""
    # Process key exactly like mobile app
    key_hex = device_key_hex[:32]  # First 32 hex chars
    key_bytes = bytes.fromhex(key_hex)
    
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV and ciphertext
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # AES-128-CBC decrypt
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)
    
    # Remove PKCS7 padding
    plaintext = unpad(padded_plaintext, AES.block_size)
    
    return plaintext.decode('utf-8')

# Test with generated credentials
device_key = "e178f9137714b6466e4c138dc2980bb4be06fba3448ddd4b04a354f3e177d480"

# Test credentials from mobile app generator
encrypted_username = "ABEiM0RVZneImaq7zN3u//toREe7OnHpXZgDPgWf+uI="
encrypted_password = "ABEiM0RVZneImaq7zN3u/+Ntk6yv09q7pj1qYzKBhaM="

print("=== TESTING MOBILE APP ENCRYPTION/DECRYPTION ===")
print(f"Device key: {device_key}")
print(f"Encrypted username: {encrypted_username}")
print(f"Encrypted password: {encrypted_password}")

try:
    username = decrypt_mobile_credential(encrypted_username, device_key)
    print(f"SUCCESS - Decrypted username: '{username}'")
except Exception as e:
    print(f"FAILED - Username decryption error: {e}")

try:
    password = decrypt_mobile_credential(encrypted_password, device_key)
    print(f"SUCCESS - Decrypted password: '{password}'")
except Exception as e:
    print(f"FAILED - Password decryption error: {e}")

print("\n=== EXPECTED RESULTS ===")
print("Username should be: 'testuser123'")
print("Password should be: 'testpass456'")

# Now test with Boston Globe credentials
print("\n=== TESTING BOSTON GLOBE CREDENTIALS ===")
boston_username = "c1tbCx/NyyRwX4w/U+WhkJHW5VHaU1HgnzxzHzrZGfb84fp34Zwfp9ztuyPwRj1G"
boston_password = "L+v7YYe4lt1NNSAeeVkLCEFa8mLXw3mbL3txl0YuNEw="

try:
    boston_user = decrypt_mobile_credential(boston_username, device_key)
    print(f"SUCCESS - Boston Globe username: '{boston_user}'")
except Exception as e:
    print(f"FAILED - Boston Globe username error: {e}")

try:
    boston_pass = decrypt_mobile_credential(boston_password, device_key)
    print(f"SUCCESS - Boston Globe password: '{boston_pass}'")
except Exception as e:
    print(f"FAILED - Boston Globe password error: {e}")