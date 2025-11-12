#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)

def try_different_key_derivations():
    mobile_public_key = "f0c9487562db956e2d7864ca27f1cc1c82ecee1fea251dfa16be285f652a84943fef4adb7f70a89db1f6f690a7150375286be91eac1ae6a653e15fe0e7d35d1762cc55bd7953cb67508e0be0b9aa75484b73a2dabc74ad8e16b5ec1726b0ec5b707f788c244cf1f3d2e24c757eba3aca958280ad20c8e5c9cb0f8239d5daa1440ac6586304c2e249e10389955a2b97dcbd5fb5bd801bececc84b291944eb61e4f3036468a06a45142b2451ed9d8034f5a444fb71d1003796e12e13e137b6a62a978cad0e2710c07c7d4d604a1241108db8ccdaeb5418a932a7ae90cd5225e79654e4682fc4adb1b6671ca6d5cca922e7c844923bb0e2451a8ee19283ebd44de2"
    server_private_key = "1855699527122823605301096117990787629509201203106440200973732878362536081808"
    encrypted_username = "3e65LIqasqcP0WbV3BOducAsU41BXG3ilz1I+Ht79tw="
    
    mobile_public_key_int = int(mobile_public_key, 16)
    server_private_key_int = int(server_private_key)
    shared_secret = pow(mobile_public_key_int, server_private_key_int, P)
    
    print("=== TRYING DIFFERENT KEY DERIVATION METHODS ===")
    
    # Method 1: SHA-256 first 16 bytes (current)
    shared_secret_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
    key1 = hashlib.sha256(shared_secret_bytes).digest()[:16]
    print(f"Method 1 (SHA-256[:16]): {key1.hex()}")
    
    # Method 2: Full SHA-256 hash (32 bytes)
    key2 = hashlib.sha256(shared_secret_bytes).digest()
    print(f"Method 2 (SHA-256 full): {key2.hex()}")
    
    # Method 3: Shared secret as hex string then hash
    shared_secret_hex = hex(shared_secret)[2:]  # Remove 0x prefix
    key3 = hashlib.sha256(shared_secret_hex.encode()).digest()[:16]
    print(f"Method 3 (hex string): {key3.hex()}")
    
    # Method 4: Direct shared secret bytes (first 16)
    key4 = shared_secret_bytes[:16]
    print(f"Method 4 (direct bytes): {key4.hex()}")
    
    # Method 5: MD5 hash
    key5 = hashlib.md5(shared_secret_bytes).digest()
    print(f"Method 5 (MD5): {key5.hex()}")
    
    # Try each key
    username_data = base64.b64decode(encrypted_username)
    iv = username_data[:16]
    ciphertext = username_data[16:]
    
    for i, key in enumerate([key1, key2[:16], key3, key4, key5], 1):
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(ciphertext)
            
            # Try without unpadding first
            try:
                text = decrypted.decode('utf-8').rstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10')
                print(f"Method {i} SUCCESS (no unpad): '{text}'")
            except:
                pass
            
            # Try with unpadding
            try:
                text = unpad(decrypted, AES.block_size).decode('utf-8')
                print(f"Method {i} SUCCESS (with unpad): '{text}'")
            except:
                pass
                
        except Exception as e:
            pass

if __name__ == "__main__":
    try_different_key_derivations()