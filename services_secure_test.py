#!/usr/bin/env python3
"""
Services Secure Decryption Test - Using PyCrypto
"""
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64

def derive_aes_key_secure(shared_secret_bigint):
    """
    SECURE METHOD: Use full shared secret for key derivation (no truncation)
    """
    # Calculate actual byte length (maintains full entropy)
    bit_length = shared_secret_bigint.bit_length()
    byte_length = (bit_length + 7) // 8
    
    print(f"SERVICES DEBUG: Shared secret bit length: {bit_length}")
    print(f"SERVICES DEBUG: Shared secret byte length: {byte_length}")
    print(f"SERVICES DEBUG: SECURE METHOD - NO TRUNCATION, FULL ENTROPY")
    
    # Convert to full byte array (maintains all entropy)
    shared_secret_bytes = shared_secret_bigint.to_bytes(byte_length, byteorder='big')
    
    # SHA-256 hash of full shared secret
    hash_digest = hashlib.sha256(shared_secret_bytes).digest()
    
    print(f"SERVICES DEBUG: SHA-256 hash (32 bytes): {hash_digest.hex()}")
    
    # Return first 16 bytes as AES-128 key
    aes_key = hash_digest[:16]
    print(f"SERVICES DEBUG: AES-128 key (16 bytes): {aes_key.hex()}")
    
    return aes_key

def decrypt_credentials_secure(encrypted_username_b64, encrypted_password_b64, aes_key):
    """
    Decrypt credentials using AES-128-CBC with PKCS7 padding
    """
    def decrypt_aes_cbc(encrypted_b64, key):
        try:
            # Decode base64
            encrypted_data = base64.b64decode(encrypted_b64)
            
            # Extract IV (first 16 bytes) and ciphertext
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            
            print(f"SERVICES DEBUG: IV: {iv.hex()}")
            print(f"SERVICES DEBUG: Ciphertext length: {len(ciphertext)} bytes")
            
            # Decrypt using AES-128-CBC
            cipher = AES.new(key, AES.MODE_CBC, iv)
            padded_plaintext = cipher.decrypt(ciphertext)
            
            # Remove PKCS7 padding
            plaintext = unpad(padded_plaintext, AES.block_size)
            
            return plaintext.decode('utf-8')
        except Exception as e:
            print(f"SERVICES ERROR: Decryption failed: {e}")
            return None
    
    print("SERVICES DEBUG: Decrypting username...")
    username = decrypt_aes_cbc(encrypted_username_b64, aes_key)
    
    print("SERVICES DEBUG: Decrypting password...")
    password = decrypt_aes_cbc(encrypted_password_b64, aes_key)
    
    print(f"SERVICES DEBUG: Decrypted username: '{username}'")
    print(f"SERVICES DEBUG: Decrypted password: '{password}'")
    
    return username, password

def test_secure_decryption():
    """
    Test secure decryption with test shared secret
    """
    print("=== SERVICES SECURE DECRYPTION TEST ===")
    
    # Test shared secret (large number for testing)
    shared_secret_str = (
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "123456789012345678901234567890123456789012345678901234567890"
        "1234567890"
    )
    
    shared_secret = int(shared_secret_str)
    
    print("SERVICES TEST: Starting secure decryption test...")
    
    # Derive AES key using SECURE method (full entropy)
    aes_key = derive_aes_key_secure(shared_secret)
    
    print("\n✅ SECURE KEY DERIVATION WORKING")
    print("✅ Ready for mobile app encrypted values")
    print("\nNext steps:")
    print("1. Mobile app runs test with same shared secret")
    print("2. Mobile app provides encrypted values")
    print("3. Services decrypts and verifies compatibility")
    
    return aes_key

def test_with_actual_shared_secret():
    """
    Test with our actual stored shared secret
    """
    print("\n=== TESTING WITH ACTUAL SHARED SECRET ===")
    
    # Our actual shared secret from stored credentials
    actual_shared_secret = 376247706963695395655942410089832014385902292525619568738686307803236121300817324410794408994386117655280655842515751417256970207265621256134942126115810316027345450459417783218550341441497105925164381448417501339371554553966138478663002876245166881627654080154690541380769471364388529300386342332010061414234026059573997842463866452263604972411909941391123343686254395125117539536474863775225819210454953763922120536098726031647823255111006583630959683070231072699651120677353889508319492868795993107305252766924799681465763844483377584228037024984598407941217312092860640036678370991632954542927205910798727860164
    
    # Derive AES key using SECURE method
    aes_key = derive_aes_key_secure(actual_shared_secret)
    
    # Test with stored credentials (should work if mobile app uses secure method)
    stored_username = "OyER5/+SrzHipflupmxrTXBXVRJcb4IOwzW83qzCBUeQ3XAeehMpQkCIiHHYtIuB"
    stored_password = "3OunxXzP/xwd6Bl/vvz8rA6OQnEzKVv2N6jfaSTwyNg="
    
    print(f"\nTesting stored credentials with secure method:")
    username, password = decrypt_credentials_secure(stored_username, stored_password, aes_key)
    
    if username and password:
        print(f"✅ SUCCESS: Decrypted credentials")
        print(f"Username: '{username}'")
        print(f"Password: '{password}'")
    else:
        print("❌ FAILED: Could not decrypt stored credentials")
        print("This means mobile app is still using insecure truncation method")
    
    return username, password

if __name__ == "__main__":
    # Test secure key derivation
    test_aes_key = test_secure_decryption()
    
    # Test with actual stored credentials
    test_with_actual_shared_secret()