#!/usr/bin/env python3
import base64
from Crypto.Cipher import AES
import hashlib

def test_key_variation(encrypted_base64, key_variation, variation_name):
    """Test a specific key variation"""
    try:
        encrypted_data = base64.b64decode(encrypted_base64)
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]
        
        if len(key_variation) < 16:
            return None
            
        cipher = AES.new(key_variation[:16], AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)
        
        # Check if it looks like text (printable ASCII)
        try:
            # Try to find valid text in the decrypted data
            for i in range(len(decrypted)):
                for j in range(i+1, len(decrypted)+1):
                    chunk = decrypted[i:j]
                    try:
                        text = chunk.decode('utf-8')
                        if len(text) >= 3 and text.isprintable() and not text.isspace():
                            print(f"✅ {variation_name}: Found text '{text}' at position {i}-{j}")
                            return text
                    except:
                        continue
        except:
            pass
            
        return None
    except Exception as e:
        return None

# Test different key derivations
device_key = "e178f9137714b6466e4c138dc2980bb4be06fba3448ddd4b04a354f3e177d480"
encrypted_username = "c1tbCx/NyyRwX4w/U+WhkJHW5VHaU1HgnzxzHzrZGfb84fp34Zwfp9ztuyPwRj1G"
encrypted_password = "L+v7YYe4lt1NNSAeeVkLCEFa8mLXw3mbL3txl0YuNEw="

key_variations = [
    (bytes.fromhex(device_key[:32]), "First 32 hex chars"),
    (bytes.fromhex(device_key[32:64]), "Last 32 hex chars"), 
    (bytes.fromhex(device_key)[:16], "Full key first 16 bytes"),
    (bytes.fromhex(device_key)[16:32], "Full key middle 16 bytes"),
    (bytes.fromhex(device_key)[32:48], "Full key last 16 bytes"),
    (hashlib.sha256(device_key.encode()).digest()[:16], "SHA256 of full key"),
    (hashlib.sha256(device_key[:32].encode()).digest()[:16], "SHA256 of first 32 chars"),
    (hashlib.md5(device_key.encode()).digest(), "MD5 of full key"),
    (device_key[:16].encode(), "First 16 chars as bytes"),
]

print("=== TESTING KEY VARIATIONS ===")
print(f"Device key: {device_key}")
print(f"Username encrypted: {encrypted_username}")
print(f"Password encrypted: {encrypted_password}")
print()

print("--- Testing Username ---")
for key_bytes, name in key_variations:
    result = test_key_variation(encrypted_username, key_bytes, name)
    if result:
        print(f"FOUND USERNAME: '{result}' with {name}")

print("\n--- Testing Password ---")
for key_bytes, name in key_variations:
    result = test_key_variation(encrypted_password, key_bytes, name)
    if result:
        print(f"FOUND PASSWORD: '{result}' with {name}")

print("\n--- Raw Decryption Analysis ---")
# Show what the "correct" method produces
key_bytes = bytes.fromhex(device_key[:32])
encrypted_data = base64.b64decode(encrypted_password)
iv = encrypted_data[:16]
ciphertext = encrypted_data[16:]
cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
decrypted = cipher.decrypt(ciphertext)
print(f"Password decrypted bytes: {decrypted.hex()}")
print(f"As ASCII (ignoring errors): {decrypted.decode('ascii', errors='ignore')}")
print(f"Printable chars: {''.join(c for c in decrypted.decode('ascii', errors='ignore') if c.isprintable())}")