#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)

def big_int_to_full_bytes(big_int):
    if big_int == 0:
        return bytes([0])
    bytes_list = []
    temp = big_int
    while temp > 0:
        bytes_list.insert(0, temp & 0xff)
        temp = temp >> 8
    return bytes(bytes_list)

def try_decrypt(aes_key, encrypted_data_b64, label):
    try:
        encrypted_data = base64.b64decode(encrypted_data_b64)
        if len(encrypted_data) < 16:
            return f"{label}: Data too short"
        
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]
        
        if len(ciphertext) % 16 != 0:
            return f"{label}: Invalid ciphertext length {len(ciphertext)}"
        
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)
        
        # Try with unpadding
        try:
            result = unpad(decrypted, AES.block_size).decode('utf-8')
            return f"{label}: SUCCESS - '{result}'"
        except:
            # Try without unpadding
            try:
                result = decrypted.decode('utf-8').rstrip('\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10')
                return f"{label}: SUCCESS (no unpad) - '{result}'"
            except:
                return f"{label}: Decrypted but not valid UTF-8"
    except Exception as e:
        return f"{label}: ERROR - {str(e)}"

def decrypt_credentials():
    # Data from mobile app logs
    mobile_public_key = "6249147f629130e026ab6732ba525088d15564df5e6e1b262d0fe1fe0899341e11472d92ca4db8e7d1ce89f367a41e0f2fed2d8f481d750a129dc80c2f630b6f409333ede85d667ec581cf0d5a9f3e3b9a9c8dc708ec522ee2176f79cb0e53b6255281f8de761f282fa11e0ad91d35bd39ec1afa0f63cf1cdf55f7cc765f4c1ef163f7c187f5d731f65440635129dbef204a609d345fbd5efd4642d9f54756dc52df18d9a204a197f9877699efbd3419c95ad59e8cd1ed423d5d6736d7ceca88e6382558effa6180f1182568252307a15943af05bd9a98c1a916aa744a71a6ffe950d091ce7a0aaa98a16edb3314b19dd18f2a584f7eb397eeba4c245c291293"
    server_private_key = "23341236479817520700106440276798823353781619641231018265294860013864666580890"
    encrypted_username = "JhTbwH1+aAY+KYo2878Yo2e0n9Uhrt2LHfY/98c6RW55VpeQl6YjNJF65GDAWtHW"
    encrypted_password = "9kXyhBG0Nu6zZqE7DCgeJj9IIvYDwFPYMM5KtrTdOnE="
    
    print("=== TRYING MULTIPLE DECRYPTION METHODS ===")
    
    # Calculate shared secret
    mobile_public_key_int = int(mobile_public_key, 16)
    server_private_key_int = int(server_private_key)
    shared_secret = pow(mobile_public_key_int, server_private_key_int, P)
    
    print(f"Shared Secret: {shared_secret}")
    
    # Method 1: Mobile app method (big_int_to_full_bytes + SHA-256[:16])
    shared_secret_bytes1 = big_int_to_full_bytes(shared_secret)
    aes_key1 = hashlib.sha256(shared_secret_bytes1).digest()[:16]
    
    # Method 2: Standard to_bytes + SHA-256[:16]
    shared_secret_bytes2 = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
    aes_key2 = hashlib.sha256(shared_secret_bytes2).digest()[:16]
    
    # Method 3: Hex string + SHA-256[:16]
    shared_secret_hex = hex(shared_secret)[2:]
    aes_key3 = hashlib.sha256(shared_secret_hex.encode()).digest()[:16]
    
    # Method 4: Direct bytes (first 16)
    aes_key4 = shared_secret_bytes1[:16] if len(shared_secret_bytes1) >= 16 else shared_secret_bytes1 + b'\x00' * (16 - len(shared_secret_bytes1))
    
    print(f"Method 1 AES Key: {aes_key1.hex()}")
    print(f"Method 2 AES Key: {aes_key2.hex()}")
    print(f"Method 3 AES Key: {aes_key3.hex()}")
    print(f"Method 4 AES Key: {aes_key4.hex()}")
    
    print("\n=== USERNAME DECRYPTION ATTEMPTS ===")
    print(try_decrypt(aes_key1, encrypted_username, "Method 1 (mobile app)"))
    print(try_decrypt(aes_key2, encrypted_username, "Method 2 (standard)"))
    print(try_decrypt(aes_key3, encrypted_username, "Method 3 (hex string)"))
    print(try_decrypt(aes_key4, encrypted_username, "Method 4 (direct bytes)"))
    
    print("\n=== PASSWORD DECRYPTION ATTEMPTS ===")
    print(try_decrypt(aes_key1, encrypted_password, "Method 1 (mobile app)"))
    print(try_decrypt(aes_key2, encrypted_password, "Method 2 (standard)"))
    print(try_decrypt(aes_key3, encrypted_password, "Method 3 (hex string)"))
    print(try_decrypt(aes_key4, encrypted_password, "Method 4 (direct bytes)"))

if __name__ == "__main__":
    decrypt_credentials()