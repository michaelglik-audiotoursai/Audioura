#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)
G = 2

def decrypt_credentials(mobile_public_key_hex, server_private_key, encrypted_username_b64, encrypted_password_b64):
    """
    Decrypt credentials using Diffie-Hellman shared secret
    """
    try:
        # Convert mobile public key from hex to integer
        mobile_public_key = int(mobile_public_key_hex, 16)
        server_private_key_int = int(server_private_key)
        
        # Calculate shared secret: mobile_public_key^server_private_key mod P
        shared_secret = pow(mobile_public_key, server_private_key_int, P)
        
        # Derive AES key from shared secret using SHA-256
        shared_secret_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
        aes_key = hashlib.sha256(shared_secret_bytes).digest()[:16]  # AES-128
        
        print(f"Mobile Public Key: {mobile_public_key_hex[:64]}...")
        print(f"Server Private Key: {server_private_key}")
        print(f"Shared Secret: {shared_secret}")
        print(f"AES Key (hex): {aes_key.hex()}")
        
        # Decrypt username
        encrypted_username = base64.b64decode(encrypted_username_b64)
        iv_username = encrypted_username[:16]
        ciphertext_username = encrypted_username[16:]
        
        cipher_username = AES.new(aes_key, AES.MODE_CBC, iv_username)
        decrypted_username = unpad(cipher_username.decrypt(ciphertext_username), AES.block_size).decode('utf-8')
        
        # Decrypt password
        encrypted_password = base64.b64decode(encrypted_password_b64)
        iv_password = encrypted_password[:16]
        ciphertext_password = encrypted_password[16:]
        
        cipher_password = AES.new(aes_key, AES.MODE_CBC, iv_password)
        decrypted_password = unpad(cipher_password.decrypt(ciphertext_password), AES.block_size).decode('utf-8')
        
        return decrypted_username, decrypted_password
        
    except Exception as e:
        print(f"Decryption error: {e}")
        return None, None

if __name__ == "__main__":
    # Test data from mobile app
    mobile_public_key = "8f7e6d5c4b3a29180e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a6978"
    server_private_key = "1855699527122823605301096117990787629509201203106440200973732878362536081808"
    encrypted_username = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8="
    encrypted_password = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8SEiM0VWiavN7f"
    
    print("=== DECRYPTING MOBILE APP CREDENTIALS ===")
    print(f"Newsletter ID: 169")
    print(f"Article ID: article_169_001")
    print(f"Device ID: mobile_device_12345")
    print(f"Domain: newsletter169.example.com")
    print()
    
    username, password = decrypt_credentials(
        mobile_public_key, 
        server_private_key, 
        encrypted_username, 
        encrypted_password
    )
    
    if username and password:
        print()
        print("=== DECRYPTION SUCCESSFUL ===")
        print(f"Username: {username}")
        print(f"Password: {password}")
    else:
        print()
        print("=== DECRYPTION FAILED ===")