#!/usr/bin/env python3

import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# RFC 3526 Group 14 parameters
P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)

def decrypt_credentials():
    # Data from mobile app submission
    mobile_public_key = "6f70fbc33e798529042c90c515266584c0cb3061e53f8bd816f69d9967085643982604420e665f38fa06f89bb33be2a0c11cb2f22e546985940031b2bb175f641b0371c66dbdf8b545fde7a3fac8c6ad88aa4d9c6ad1acfb6991dae880e008a8b3967b3b9edb419e98ff7f0923a0b374a2da1eaef74ca14c59ece32241f0e1e320c76388223ec5804fc86b765b327704596f2613d7a129a03b918b3754555ce5bae0c8b8d4dccc2c02f640df37dbbd639e5fe3a826fe7b0cb324a16f48bccac64935bac063eb962356c9dc4558b824d7049e6ed0157aaf9163515ef0442aa62cc2f8f7aad4d9cbbb0690e7a98dca96fff93be5039f6825e4922d0ef9bd1b7a7"
    server_private_key = "1855699527122823605301096117990787629509201203106440200973732878362536081808"
    encrypted_username = "RNGQP63arctKpcqSDaXKfCCo+TMl+yl0iwOmXr6TF3GxF4ihSf76scYBNhFmwKaM"
    encrypted_password = "/6lXH2QjsBJRtiKx4fjyh1Zo5DyZj11gZFSwAfLjkHM="
    
    print("=== DECRYPTING MOBILE APP CREDENTIALS ===")
    print(f"Device ID: USER-281301397")
    print(f"Article ID: a6725c3a-a7cf-4e32-adea-4668dab70a17")
    print(f"Newsletter ID: 169")
    print(f"Domain: bostonglobe.com")
    print()
    
    # Calculate shared secret
    mobile_public_key_int = int(mobile_public_key, 16)
    server_private_key_int = int(server_private_key)
    shared_secret = pow(mobile_public_key_int, server_private_key_int, P)
    
    # Derive AES key
    shared_secret_bytes = shared_secret.to_bytes((shared_secret.bit_length() + 7) // 8, 'big')
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
    
    return decrypted_username, decrypted_password

if __name__ == "__main__":
    decrypt_credentials()