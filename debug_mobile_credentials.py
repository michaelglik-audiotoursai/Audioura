#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def debug_encrypted_data():
    """
    Debug the encrypted data to understand the format
    """
    encrypted_username = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8="
    encrypted_password = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8SEiM0VWiavN7f"
    
    print("=== DEBUGGING ENCRYPTED DATA ===")
    
    # Decode base64
    username_bytes = base64.b64decode(encrypted_username)
    password_bytes = base64.b64decode(encrypted_password)
    
    print(f"Username encrypted length: {len(username_bytes)} bytes")
    print(f"Username hex: {username_bytes.hex()}")
    print(f"Password encrypted length: {len(password_bytes)} bytes") 
    print(f"Password hex: {password_bytes.hex()}")
    
    # Check if data is properly padded (multiple of 16)
    print(f"Username length % 16: {len(username_bytes) % 16}")
    print(f"Password length % 16: {len(password_bytes) % 16}")
    
    # Check if first 16 bytes could be IV
    if len(username_bytes) >= 16:
        iv_username = username_bytes[:16]
        ciphertext_username = username_bytes[16:]
        print(f"Username IV: {iv_username.hex()}")
        print(f"Username ciphertext: {ciphertext_username.hex()}")
        print(f"Username ciphertext length: {len(ciphertext_username)}")
    
    if len(password_bytes) >= 16:
        iv_password = password_bytes[:16]
        ciphertext_password = password_bytes[16:]
        print(f"Password IV: {iv_password.hex()}")
        print(f"Password ciphertext: {ciphertext_password.hex()}")
        print(f"Password ciphertext length: {len(ciphertext_password)}")

if __name__ == "__main__":
    debug_encrypted_data()