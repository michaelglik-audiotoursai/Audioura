#!/usr/bin/env python3
"""
Test with proper 32-byte handling as per mobile app specification
"""
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import os

def test_with_proper_32byte():
    # Your shared secret (from Services)
    shared_secret = 376247706963695395655942410089832014385902292525619568738686307803236121300817324410794408994386117655280655842515751417256970207265621256134942126115810316027345450459417783218550341441497105925164381448417501339371554553966138478663002876245166881627654080154690541380769471364388529300386342332010061414234026059573997842463866452263604972411909941391123343686254395125117539536474863775225819210454953763922120536098726031647823255111006583630959683070231072699651120677353889508319492868795993107305252766924799681465763844483377584228037024984598407941217312092860640036678370991632954542927205910798727860164
    
    print(f"Shared secret: {str(shared_secret)[:50]}...")
    
    # Check bit length
    bit_length = shared_secret.bit_length()
    byte_length = (bit_length + 7) // 8
    print(f"Bit length: {bit_length}")
    print(f"Required byte length: {byte_length}")
    
    # Mobile app specification: Convert to 32 bytes (pad with leading zeros if needed)
    # But if > 32 bytes, we need to handle differently
    
    if byte_length <= 32:
        # Pad to 32 bytes
        shared_secret_bytes = shared_secret.to_bytes(32, byteorder='big')
        print("Using 32-byte padding (mobile app method)")
    else:
        # Use actual length (our shared secret is too big for 32 bytes)
        shared_secret_bytes = shared_secret.to_bytes(byte_length, byteorder='big')
        print(f"Using actual length ({byte_length} bytes) - shared secret too large for 32 bytes")
    
    print(f"Shared secret bytes: {shared_secret_bytes[:16].hex()}... (showing first 16 bytes)")
    
    # SHA-256 hash
    hash_digest = hashlib.sha256(shared_secret_bytes).digest()
    print(f"SHA-256 hash: {hash_digest.hex()}")
    
    # AES-128 key (first 16 bytes)
    aes_key = hash_digest[:16]
    print(f"AES Key: {aes_key.hex()}")
    
    # Test encryption/decryption
    def encrypt_decrypt_test(plaintext, key):
        print(f"\nTesting: '{plaintext}'")
        
        # Encrypt
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plaintext.encode('utf-8'), 16)
        encrypted = cipher.encrypt(padded)
        combined = iv + encrypted
        encrypted_b64 = base64.b64encode(combined).decode()
        
        print(f"Encrypted: {encrypted_b64}")
        
        # Decrypt
        combined_back = base64.b64decode(encrypted_b64)
        iv_back = combined_back[:16]
        encrypted_back = combined_back[16:]
        
        cipher_back = AES.new(key, AES.MODE_CBC, iv_back)
        padded_back = cipher_back.decrypt(encrypted_back)
        
        padding_length = padded_back[-1]
        plaintext_back = padded_back[:-padding_length]
        result = plaintext_back.decode('utf-8')
        
        print(f"Decrypted: '{result}'")
        
        if result == plaintext:
            print("✅ SUCCESS")
        else:
            print("❌ FAILURE")
        
        return encrypted_b64
    
    # Test with known values
    print("\n=== TESTING KNOWN VALUES ===")
    encrypted_username = encrypt_decrypt_test("testuser123", aes_key)
    encrypted_password = encrypt_decrypt_test("testpass456", aes_key)
    
    print(f"\n=== RESULTS FOR MOBILE APP COMPARISON ===")
    print(f"AES Key (hex): {aes_key.hex()}")
    print(f"Test encrypted username: {encrypted_username}")
    print(f"Test encrypted password: {encrypted_password}")

if __name__ == "__main__":
    test_with_proper_32byte()