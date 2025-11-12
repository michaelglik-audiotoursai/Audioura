#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import psycopg2

def decrypt_credential_debug(encrypted_base64, hex_key):
    """Debug version with multiple key processing attempts"""
    
    print(f"Input key: {hex_key}")
    print(f"Encrypted data: {encrypted_base64}")
    
    # Try different key processing methods
    key_methods = [
        ("First 32 hex chars", bytes.fromhex(hex_key[:32])),
        ("Full key first 16 bytes", bytes.fromhex(hex_key)[:16]),
        ("Base64 of first 16 bytes", base64.b64encode(bytes.fromhex(hex_key[:32]))),
    ]
    
    encrypted_data = base64.b64decode(encrypted_base64)
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    print(f"IV: {iv.hex()}")
    print(f"Ciphertext: {ciphertext.hex()}")
    
    for method_name, key_bytes in key_methods:
        try:
            print(f"\nTrying {method_name}: {key_bytes.hex() if isinstance(key_bytes, bytes) else key_bytes}")
            
            if len(key_bytes) < 16:
                continue
                
            # Use first 16 bytes for AES-128
            aes_key = key_bytes[:16]
            
            cipher = AES.new(aes_key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(ciphertext)
            
            print(f"Raw decrypted: {decrypted.hex()}")
            
            # Try different unpadding approaches
            try:
                # Standard PKCS7 unpadding
                plaintext = unpad(decrypted, AES.block_size)
                result = plaintext.decode('utf-8')
                print(f"✅ SUCCESS with {method_name}: '{result}'")
                return result
            except:
                # Manual padding check
                if len(decrypted) > 0:
                    last_byte = decrypted[-1]
                    if 1 <= last_byte <= 16:
                        try:
                            plaintext = decrypted[:-last_byte]
                            result = plaintext.decode('utf-8')
                            print(f"✅ SUCCESS with manual unpad {method_name}: '{result}'")
                            return result
                        except:
                            pass
                            
        except Exception as e:
            print(f"❌ Failed {method_name}: {e}")
            
    return None

# Connect and test
conn = psycopg2.connect(
    host='localhost',
    database='audiotours', 
    user='admin',
    password='password123',
    port='5433'
)

cursor = conn.cursor()
cursor.execute("""
    SELECT usc.encrypted_username, usc.encrypted_password, dek.encryption_key
    FROM user_subscription_credentials usc
    JOIN device_encryption_keys dek ON usc.device_id = dek.device_id
    WHERE usc.device_id = 'USER-281301397'
    ORDER BY usc.created_at DESC LIMIT 1
""")

result = cursor.fetchone()
if result:
    enc_username, enc_password, hex_key = result
    
    print("=== DECRYPTING BOSTON GLOBE CREDENTIALS ===")
    
    print("\n--- USERNAME ---")
    username = decrypt_credential_debug(enc_username, hex_key)
    
    print("\n--- PASSWORD ---")
    password = decrypt_credential_debug(enc_password, hex_key)
    
    if username and password:
        print(f"\n🎉 FINAL RESULT:")
        print(f"Domain: bostonglobe.com")
        print(f"Username: {username}")
        print(f"Password: {password}")
    else:
        print("\n❌ Could not decrypt credentials")

cursor.close()
conn.close()