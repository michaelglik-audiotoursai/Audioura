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

def decrypt_credentials():
    # Newsletter 174's private key (the one mobile app actually used)
    server_private_key = "23341236479817520700106440276798823353781619641231018265294860013864666580890"
    
    # Mobile app's data from logs
    mobile_public_key = "6249147f629130e026ab6732ba525088d15564df5e6e1b262d0fe1fe0899341e11472d92ca4db8e7d1ce89f367a41e0f2fed2d8f481d750a129dc80c2f630b6f409333ede85d667ec581cf0d5a9f3e3b9a9c8dc708ec522ee2176f79cb0e53b6255281f8de761f282fa11e0ad91d35bd39ec1afa0f63cf1cdf55f7cc765f4c1ef163f7c187f5d731f65440635129dbef204a609d345fbd5efd4642d9f54756dc52df18d9a204a197f9877699efbd3419c95ad59e8cd1ed423d5d6736d7ceca88e6382558effa6180f1182568252307a15943af05bd9a98c1a916aa744a71a6ffe950d091ce7a0aaa98a16edb3314b19dd18f2a584f7eb397eeba4c245c291293"
    encrypted_username = "JhTbwH1+aAY+KYo2878Yo2e0n9Uhrt2LHfY/98c6RW55VpeQl6YjNJF65GDAWtHW"
    encrypted_password = "9kXyhBG0Nu6zZqE7DCgeJj9IIvYDwFPYMM5KtrTdOnE="
    
    print("=== DECRYPTING WITH CORRECT NEWSLETTER 174 KEY ===")
    
    # Calculate shared secret
    mobile_public_key_int = int(mobile_public_key, 16)
    server_private_key_int = int(server_private_key)
    shared_secret = pow(mobile_public_key_int, server_private_key_int, P)
    
    # Derive AES key using mobile app's method
    shared_secret_bytes = big_int_to_full_bytes(shared_secret)
    aes_key = hashlib.sha256(shared_secret_bytes).digest()[:16]
    
    print(f"AES Key: {aes_key.hex()}")
    
    # Decrypt username
    username_data = base64.b64decode(encrypted_username)
    iv_username = username_data[:16]
    ciphertext_username = username_data[16:]
    
    cipher_username = AES.new(aes_key, AES.MODE_CBC, iv_username)
    decrypted_username = unpad(cipher_username.decrypt(ciphertext_username), AES.block_size).decode('utf-8')
    
    # Decrypt password
    password_data = base64.b64decode(encrypted_password)
    iv_password = password_data[:16]
    ciphertext_password = password_data[16:]
    
    cipher_password = AES.new(aes_key, AES.MODE_CBC, iv_password)
    decrypted_password = unpad(cipher_password.decrypt(ciphertext_password), AES.block_size).decode('utf-8')
    
    print("=== DECRYPTION SUCCESSFUL ===")
    print(f"Username: {decrypted_username}")
    print(f"Password: {decrypted_password}")

if __name__ == "__main__":
    decrypt_credentials()