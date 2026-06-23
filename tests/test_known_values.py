#!/usr/bin/env python3
"""
Test encryption/decryption with known values from Mobile App Amazon-Q
"""
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import os

def test_encryption_like_mobile():
    # Your shared secret (from Services)
    shared_secret = 376247706963695395655942410089832014385902292525619568738686307803236121300817324410794408994386117655280655842515751417256970207265621256134942126115810316027345450459417783218550341441497105925164381448417501339371554553966138478663002876245166881627654080154690541380769471364388529300386342332010061414234026059573997842463866452263604972411909941391123343686254395125117539536474863775225819210454953763922120536098726031647823255111006583630959683070231072699651120677353889508319492868795993107305252766924799681465763844483377584228037024984598407941217312092860640036678370991632954542927205910798727860164
    
    # Convert to 32-byte array (mobile app method)
    shared_secret_bytes = shared_secret.to_bytes(32, byteorder='big')
    print(f"Shared secret bytes (32): {shared_secret_bytes.hex()}")
    
    # SHA-256 hash
    hash_digest = hashlib.sha256(shared_secret_bytes).digest()
    print(f"SHA-256 hash: {hash_digest.hex()}")
    
    # AES-128 key (first 16 bytes)
    aes_key = hash_digest[:16]
    print(f"AES Key: {aes_key.hex()}")
    print(f"AES Key (base64): {base64.b64encode(aes_key).decode()}")
    
    # Test encryption exactly like mobile app
    def encrypt_like_mobile(plaintext, key):
        print(f"Encrypting: '{plaintext}' (length: {len(plaintext)})")
        
        # Generate random IV (16 bytes)
        iv = os.urandom(16)
        print(f"IV: {iv.hex()}")
        
        # Setup AES-CBC cipher
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Add PKCS7 padding
        padded = pad(plaintext.encode('utf-8'), 16)
        print(f"Padded plaintext: {padded.hex()} (length: {len(padded)})")
        
        # Encrypt
        encrypted = cipher.encrypt(padded)
        print(f"Encrypted: {encrypted.hex()} (length: {len(encrypted)})")
        
        # Return Base64(IV + Encrypted)
        combined = iv + encrypted
        result = base64.b64encode(combined).decode()
        print(f"Final result: {result}")
        return result
    
    # Test with known values
    print("\n=== ENCRYPTING USERNAME ===")
    encrypted_username = encrypt_like_mobile("testuser123", aes_key)
    
    print("\n=== ENCRYPTING PASSWORD ===")
    encrypted_password = encrypt_like_mobile("testpass456", aes_key)
    
    print("\n=== FINAL TEST RESULTS ===")
    print(f"Encrypted username: {encrypted_username}")
    print(f"Encrypted password: {encrypted_password}")
    
    # Verify decryption works
    def decrypt_test(encrypted_b64, key):
        combined = base64.b64decode(encrypted_b64)
        iv = combined[:16]
        encrypted = combined[16:]
        
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_plaintext = cipher.decrypt(encrypted)
        
        # Remove PKCS7 padding
        padding_length = padded_plaintext[-1]
        plaintext = padded_plaintext[:-padding_length]
        
        return plaintext.decode('utf-8')
    
    print("\n=== DECRYPTION VERIFICATION ===")
    decrypted_username = decrypt_test(encrypted_username, aes_key)
    decrypted_password = decrypt_test(encrypted_password, aes_key)
    print(f"Decrypted username: '{decrypted_username}'")
    print(f"Decrypted password: '{decrypted_password}'")
    
    # Verify results
    if decrypted_username == "testuser123" and decrypted_password == "testpass456":
        print("\n✅ SUCCESS: Encryption/Decryption working correctly!")
    else:
        print("\n❌ FAILURE: Decryption mismatch!")
    
    return {
        'shared_secret': shared_secret,
        'aes_key_hex': aes_key.hex(),
        'encrypted_username': encrypted_username,
        'encrypted_password': encrypted_password
    }

if __name__ == "__main__":
    test_encryption_like_mobile()