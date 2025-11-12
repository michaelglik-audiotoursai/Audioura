#!/usr/bin/env python3
"""
Decrypt mobile app credentials using the correct server private key (Newsletter 169)
"""

import base64
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# RFC 3526 Group 14 parameters (2048-bit)
DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)

def big_int_to_full_bytes(big_int):
    """Mobile app's _bigIntToFullBytes method"""
    if big_int == 0:
        return bytes([0])
    
    byte_list = []
    temp = big_int
    
    while temp > 0:
        byte_list.insert(0, temp & 0xff)
        temp = temp >> 8
    
    return bytes(byte_list)

def decrypt_aes_cbc_exact(encrypted_data_b64, aes_key):
    """Exact mobile app decryption"""
    try:
        # Decode Base64
        combined_data = base64.b64decode(encrypted_data_b64)
        
        if len(combined_data) < 16:
            raise ValueError("Encrypted data too short (missing IV)")
        
        # Extract IV (first 16 bytes) and ciphertext (remaining)
        iv = combined_data[:16]
        ciphertext = combined_data[16:]
        
        # Setup AES-128-CBC decryption
        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        
        # Decrypt
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Remove PKCS7 padding
        padding_length = padded_plaintext[-1]
        if padding_length > 16 or padding_length == 0:
            raise ValueError(f"Invalid PKCS7 padding length: {padding_length}")
        
        # Verify padding
        for i in range(padding_length):
            if padded_plaintext[-(i+1)] != padding_length:
                raise ValueError("Invalid PKCS7 padding")
        
        plaintext = padded_plaintext[:-padding_length]
        return plaintext.decode('utf-8')
        
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")

def decrypt_with_correct_key():
    """Decrypt using Newsletter 169's server private key"""
    
    # Correct server private key (Newsletter 169)
    server_private_key = 1855699527122823605301096117990787629509201203106440200973732878362536081808
    
    # Mobile app data
    mobile_public_key_hex = "6249147f629130e026ab6732ba525088d15564df5e6e1b262d0fe1fe0899341e11472d92ca4db8e7d1ce89f367a41e0f2fed2d8f481d750a129dc80c2f630b6f409333ede85d667ec581cf0d5a9f3e3b9a9c8dc708ec522ee2176f79cb0e53b6255281f8de761f282fa11e0ad91d35bd39ec1afa0f63cf1cdf55f7cc765f4c1ef163f7c187f5d731f65440635129dbef204a609d345fbd5efd4642d9f54756dc52df18d9a204a197f9877699efbd3419c95ad59e8cd1ed423d5d6736d7ceca88e6382558effa6180f1182568252307a15943af05bd9a98c1a916aa744a71a6ffe950d091ce7a0aaa98a16edb3314b19dd18f2a584f7eb397eeba4c245c291293"
    encrypted_username = "JhTbwH1+aAY+KYo2878Yo2e0n9Uhrt2LHfY/98c6RW55VpeQl6YjNJF65GDAWtHW"
    encrypted_password = "9kXyhBG0Nu6zZqE7DCgeJj9IIvYDwFPYMM5KtrTdOnE="
    
    print("=== DECRYPTION WITH CORRECT SERVER KEY ===")
    print(f"Using Newsletter 169 server private key: {server_private_key}")
    print()
    
    # Parse mobile public key
    mobile_public_key = int(mobile_public_key_hex, 16)
    
    # Calculate shared secret: mobile_public^server_private mod prime
    shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
    print(f"Shared secret: {shared_secret}")
    
    # Derive AES key using exact mobile app method
    shared_secret_bytes = big_int_to_full_bytes(shared_secret)
    digest = hashlib.sha256(shared_secret_bytes).digest()
    aes_key = digest[:16]
    
    print(f"Shared secret bytes length: {len(shared_secret_bytes)}")
    print(f"Shared secret bytes (hex): {shared_secret_bytes.hex()}")
    print(f"AES key: {aes_key.hex()}")
    print()
    
    # Decrypt credentials
    try:
        username = decrypt_aes_cbc_exact(encrypted_username, aes_key)
        password = decrypt_aes_cbc_exact(encrypted_password, aes_key)
        
        print("*** DECRYPTION SUCCESSFUL! ***")
        print(f"Username: {username}")
        print(f"Password: {password}")
        
        return True, username, password
        
    except Exception as e:
        print(f"DECRYPTION FAILED: {str(e)}")
        return False, None, None

if __name__ == "__main__":
    decrypt_with_correct_key()