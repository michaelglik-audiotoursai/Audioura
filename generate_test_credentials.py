#!/usr/bin/env python3
"""
Generate test credentials using exact mobile app encryption method
"""

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

def mobile_encrypt(plaintext, key_bytes, fixed_iv=None):
    """
    Encrypt using exact mobile app method
    """
    # Convert to UTF-8 bytes
    plaintext_bytes = plaintext.encode('utf-8')
    
    # Add PKCS7 padding
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext_bytes) + padder.finalize()
    
    # Use fixed IV for reproducible testing
    if fixed_iv:
        iv = bytes.fromhex(fixed_iv)
    else:
        import os
        iv = os.urandom(16)
    
    # AES-128-CBC encrypt
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # Combine IV + ciphertext and Base64 encode
    combined = iv + ciphertext
    return base64.b64encode(combined).decode('utf-8')

def mobile_decrypt(encrypted_base64, key_bytes):
    """
    Decrypt using exact mobile app method
    """
    # Decode Base64
    encrypted_data = base64.b64decode(encrypted_base64)
    
    # Extract IV and ciphertext
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # AES-128-CBC decrypt
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    
    # Remove PKCS7 padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    
    return plaintext.decode('utf-8')

def main():
    print("=== MOBILE APP TEST CREDENTIAL GENERATOR ===")
    
    # Test parameters
    device_key = "e178f9137714b6466e4c138dc2980bb4be06fba3448ddd4b04a354f3e177d480"
    key_hex = device_key[:32]  # First 32 hex chars
    key_bytes = bytes.fromhex(key_hex)
    
    print(f"Device key: {device_key}")
    print(f"Processed key: {key_hex}")
    print(f"Key bytes: {key_bytes.hex()}")
    
    # Test credentials
    username = "testuser123"
    password = "testpass456"
    
    # Use fixed IV for reproducible results
    fixed_iv = "00112233445566778899aabbccddeeff"
    
    print(f"\nTest values:")
    print(f"Username: '{username}'")
    print(f"Password: '{password}'")
    print(f"Fixed IV: {fixed_iv}")
    
    # Encrypt credentials
    print(f"\n=== ENCRYPTION PROCESS ===")
    
    print(f"\n--- Username Encryption ---")
    username_utf8 = username.encode('utf-8')
    print(f"UTF-8 bytes: {list(username_utf8)}")
    print(f"UTF-8 hex: {username_utf8.hex()}")
    
    encrypted_username = mobile_encrypt(username, key_bytes, fixed_iv)
    print(f"Encrypted (Base64): {encrypted_username}")
    
    print(f"\n--- Password Encryption ---")
    password_utf8 = password.encode('utf-8')
    print(f"UTF-8 bytes: {list(password_utf8)}")
    print(f"UTF-8 hex: {password_utf8.hex()}")
    
    encrypted_password = mobile_encrypt(password, key_bytes, fixed_iv)
    print(f"Encrypted (Base64): {encrypted_password}")
    
    # Verify by decrypting
    print(f"\n=== VERIFICATION (DECRYPT) ===")
    
    decrypted_username = mobile_decrypt(encrypted_username, key_bytes)
    decrypted_password = mobile_decrypt(encrypted_password, key_bytes)
    
    print(f"Decrypted username: '{decrypted_username}'")
    print(f"Decrypted password: '{decrypted_password}'")
    
    username_match = decrypted_username == username
    password_match = decrypted_password == password
    
    print(f"\nUsername match: {username_match}")
    print(f"Password match: {password_match}")
    
    if username_match and password_match:
        print(f"\n✅ SUCCESS: Encryption/decryption working correctly!")
        print(f"\n=== TEST CREDENTIALS FOR SERVICES ===")
        print(f"Device Key: {device_key}")
        print(f"Encrypted Username: {encrypted_username}")
        print(f"Encrypted Password: {encrypted_password}")
        print(f"Expected Username: {username}")
        print(f"Expected Password: {password}")
    else:
        print(f"\n❌ FAILED: Encryption/decryption not working!")

if __name__ == "__main__":
    main()