#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)

def decrypt_credentials(mobile_public_key_hex, server_private_key, encrypted_username_b64, encrypted_password_b64):
    """
    Decrypt credentials using Diffie-Hellman shared secret
    """
    # Convert mobile public key from hex to integer
    mobile_public_key = int(mobile_public_key_hex, 16)
    server_private_key_int = int(server_private_key)
    
    # Calculate shared secret: mobile_public_key^server_private_key mod P
    shared_secret = pow(mobile_public_key, server_private_key_int, P)
    
    # Derive AES key from shared secret using SHA-256
    shared_secret_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
    aes_key = hashlib.sha256(shared_secret_bytes).digest()[:16]  # AES-128
    
    print(f"AES Key: {aes_key.hex()}")
    
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

if __name__ == "__main__":
    # Real encrypted data from mobile app
    mobile_public_key = "f0c9487562db956e2d7864ca27f1cc1c82ecee1fea251dfa16be285f652a84943fef4adb7f70a89db1f6f690a7150375286be91eac1ae6a653e15fe0e7d35d1762cc55bd7953cb67508e0be0b9aa75484b73a2dabc74ad8e16b5ec1726b0ec5b707f788c244cf1f3d2e24c757eba3aca958280ad20c8e5c9cb0f8239d5daa1440ac6586304c2e249e10389955a2b97dcbd5fb5bd801bececc84b291944eb61e4f3036468a06a45142b2451ed9d8034f5a444fb71d1003796e12e13e137b6a62a978cad0e2710c07c7d4d604a1241108db8ccdaeb5418a932a7ae90cd5225e79654e4682fc4adb1b6671ca6d5cca922e7c844923bb0e2451a8ee19283ebd44de2"
    server_private_key = "1855699527122823605301096117990787629509201203106440200973732878362536081808"
    encrypted_username = "3e65LIqasqcP0WbV3BOducAsU41BXG3ilz1I+Ht79tw="
    encrypted_password = "rNV+l0rc9eQJOw7Torg2bZcflyuTZWCdrdss8gncUQQ="
    
    print("=== DECRYPTING REAL MOBILE APP CREDENTIALS ===")
    print(f"Device ID: test-device-12345")
    print(f"Article ID: 169")
    print(f"Domain: vew.marketing.select.com")
    print()
    
    username, password = decrypt_credentials(
        mobile_public_key, 
        server_private_key, 
        encrypted_username, 
        encrypted_password
    )
    
    print("=== DECRYPTION SUCCESSFUL ===")
    print(f"Username: {username}")
    print(f"Password: {password}")