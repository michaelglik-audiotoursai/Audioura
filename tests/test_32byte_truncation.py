#!/usr/bin/env python3
"""
Test with 32-byte truncation method matching mobile app
"""
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import os

def test_32byte_truncation():
    # Your shared secret (from Services)
    shared_secret = 376247706963695395655942410089832014385902292525619568738686307803236121300817324410794408994386117655280655842515751417256970207265621256134942126115810316027345450459417783218550341441497105925164381448417501339371554553966138478663002876245166881627654080154690541380769471364388529300386342332010061414234026059573997842463866452263604972411909941391123343686254395125117539536474863775225819210454953763922120536098726031647823255111006583630959683070231072699651120677353889508319492868795993107305252766924799681465763844483377584228037024984598407941217312092860640036678370991632954542927205910798727860164
    
    print(f"Shared secret: {str(shared_secret)[:50]}...")
    
    # Check bit length
    bit_length = shared_secret.bit_length()
    byte_length = (bit_length + 7) // 8
    print(f"Bit length: {bit_length}")
    print(f"Full byte length: {byte_length}")
    
    # MOBILE APP METHOD: Truncate to 32 bytes
    # 1. Convert to full byte array
    shared_secret_bytes_full = shared_secret.to_bytes(byte_length, byteorder='big')
    print(f"Full bytes: {shared_secret_bytes_full[:16].hex()}... (showing first 16 of {len(shared_secret_bytes_full)})")
    
    # 2. Truncate to first 32 bytes (mobile app method)
    shared_secret_bytes_32 = shared_secret_bytes_full[:32]
    print(f"Truncated to 32 bytes: {shared_secret_bytes_32.hex()}")
    print(f"Truncated {len(shared_secret_bytes_full) - 32} bytes")
    
    # 3. SHA-256 hash of 32 bytes
    hash_digest = hashlib.sha256(shared_secret_bytes_32).digest()
    print(f"SHA-256 hash: {hash_digest.hex()}")
    
    # 4. AES-128 key (first 16 bytes)
    aes_key = hash_digest[:16]
    print(f"AES Key: {aes_key.hex()}")
    
    # Test decryption with stored credentials
    def decrypt_stored_credentials(encrypted_b64, key):
        try:
            combined = base64.b64decode(encrypted_b64)
            iv = combined[:16]
            encrypted = combined[16:]
            
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_plaintext = cipher.decrypt(encrypted)
            
            # Remove PKCS7 padding
            padding_length = padded_plaintext[-1]
            plaintext = padded_plaintext[:-padding_length]
            
            return plaintext.decode('utf-8')
        except Exception as e:
            return f"ERROR: {e}"
    
    # Test with actual stored credentials
    stored_username = "OyER5/+SrzHipflupmxrTXBXVRJcb4IOwzW83qzCBUeQ3XAeehMpQkCIiHHYtIuB"
    stored_password = "3OunxXzP/xwd6Bl/vvz8rA6OQnEzKVv2N6jfaSTwyNg="
    
    print("\n=== TESTING STORED CREDENTIALS ===")
    print(f"Stored username: {stored_username}")
    print(f"Stored password: {stored_password}")
    
    decrypted_username = decrypt_stored_credentials(stored_username, aes_key)
    decrypted_password = decrypt_stored_credentials(stored_password, aes_key)
    
    print(f"Decrypted username: '{decrypted_username}'")
    print(f"Decrypted password: '{decrypted_password}'")
    
    # Test encryption/decryption with known values
    def encrypt_test(plaintext, key):
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plaintext.encode('utf-8'), 16)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(iv + encrypted).decode()
    
    print("\n=== TESTING KNOWN VALUES ===")
    test_encrypted_username = encrypt_test("testuser123", aes_key)
    test_encrypted_password = encrypt_test("testpass456", aes_key)
    
    print(f"Test encrypted username: {test_encrypted_username}")
    print(f"Test encrypted password: {test_encrypted_password}")
    
    # Verify decryption
    test_decrypted_username = decrypt_stored_credentials(test_encrypted_username, aes_key)
    test_decrypted_password = decrypt_stored_credentials(test_encrypted_password, aes_key)
    
    print(f"Test decrypted username: '{test_decrypted_username}'")
    print(f"Test decrypted password: '{test_decrypted_password}'")
    
    if test_decrypted_username == "testuser123" and test_decrypted_password == "testpass456":
        print("\n✅ SUCCESS: 32-byte truncation method working!")
    else:
        print("\n❌ FAILURE: Still not working")
    
    return aes_key.hex()

if __name__ == "__main__":
    test_32byte_truncation()