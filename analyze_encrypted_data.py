#!/usr/bin/env python3
"""
Analyze the encrypted data structure to understand the format
"""

import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def analyze_encrypted_data():
    """Analyze the structure of encrypted data from mobile app"""
    
    encrypted_username = "JhTbwH1+aAY+KYo2878Yo2e0n9Uhrt2LHfY/98c6RW55VpeQl6YjNJF65GDAWtHW"
    encrypted_password = "9kXyhBG0Nu6zZqE7DCgeJj9IIvYDwFPYMM5KtrTdOnE="
    
    print("=== ENCRYPTED DATA ANALYSIS ===")
    
    # Decode Base64
    username_data = base64.b64decode(encrypted_username)
    password_data = base64.b64decode(encrypted_password)
    
    print(f"Username encrypted (Base64): {encrypted_username}")
    print(f"Username decoded length: {len(username_data)} bytes")
    print(f"Username decoded (hex): {username_data.hex()}")
    print()
    
    print(f"Password encrypted (Base64): {encrypted_password}")
    print(f"Password decoded length: {len(password_data)} bytes")
    print(f"Password decoded (hex): {password_data.hex()}")
    print()
    
    # Analyze structure
    if len(username_data) >= 16:
        username_iv = username_data[:16]
        username_ciphertext = username_data[16:]
        
        print(f"Username IV: {username_iv.hex()}")
        print(f"Username ciphertext: {username_ciphertext.hex()}")
        print(f"Username ciphertext length: {len(username_ciphertext)} (blocks: {len(username_ciphertext) // 16})")
        print()
    
    if len(password_data) >= 16:
        password_iv = password_data[:16]
        password_ciphertext = password_data[16:]
        
        print(f"Password IV: {password_iv.hex()}")
        print(f"Password ciphertext: {password_ciphertext.hex()}")
        print(f"Password ciphertext length: {len(password_ciphertext)} (blocks: {len(password_ciphertext) // 16})")
        print()
    
    # Test with different AES keys to see if any work
    test_keys = [
        ("Newsletter 169 Key", "dde7c33d9b5887b44f414df7ab3db3e1"),
        ("Test Key 1", "b627c9429ce1627a56c55493f335f3a6"),  # From mobile app logs
        ("Test Key 2", "55b47536949b0f74161fd7ec3ffeac64"),  # From Newsletter 174
    ]
    
    print("=== TESTING DIFFERENT AES KEYS ===")
    
    for key_name, key_hex in test_keys:
        print(f"\nTesting {key_name}: {key_hex}")
        
        try:
            aes_key = bytes.fromhex(key_hex)
            
            # Test username decryption
            try:
                cipher = Cipher(algorithms.AES(aes_key), modes.CBC(username_iv), backend=default_backend())
                decryptor = cipher.decryptor()
                padded_plaintext = decryptor.update(username_ciphertext) + decryptor.finalize()
                
                # Check padding
                padding_length = padded_plaintext[-1]
                print(f"  Username padding length: {padding_length}")
                
                if 1 <= padding_length <= 16:
                    # Verify padding
                    valid_padding = all(padded_plaintext[-(i+1)] == padding_length for i in range(padding_length))
                    if valid_padding:
                        plaintext = padded_plaintext[:-padding_length]
                        username = plaintext.decode('utf-8')
                        print(f"  Username decrypted: '{username}'")
                    else:
                        print(f"  Username: Invalid PKCS7 padding")
                else:
                    print(f"  Username: Invalid padding length")
                    
            except Exception as e:
                print(f"  Username decryption failed: {e}")
            
            # Test password decryption
            try:
                cipher = Cipher(algorithms.AES(aes_key), modes.CBC(password_iv), backend=default_backend())
                decryptor = cipher.decryptor()
                padded_plaintext = decryptor.update(password_ciphertext) + decryptor.finalize()
                
                # Check padding
                padding_length = padded_plaintext[-1]
                print(f"  Password padding length: {padding_length}")
                
                if 1 <= padding_length <= 16:
                    # Verify padding
                    valid_padding = all(padded_plaintext[-(i+1)] == padding_length for i in range(padding_length))
                    if valid_padding:
                        plaintext = padded_plaintext[:-padding_length]
                        password = plaintext.decode('utf-8')
                        print(f"  Password decrypted: '{password}'")
                    else:
                        print(f"  Password: Invalid PKCS7 padding")
                else:
                    print(f"  Password: Invalid padding length")
                    
            except Exception as e:
                print(f"  Password decryption failed: {e}")
                
        except Exception as e:
            print(f"  Key error: {e}")

if __name__ == "__main__":
    analyze_encrypted_data()