#!/usr/bin/env python3

import base64

def analyze_test_data():
    """
    Analyze if this is test/dummy data from mobile app
    """
    encrypted_username = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8="
    encrypted_password = "EjRWeJq83t8REiM0VWiavN7fEhIjNFVomrze3xISIzRVaJq83t8SEiM0VWiavN7f"
    mobile_public_key = "8f7e6d5c4b3a29180e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a69780e1f2d3c4b5a6978"
    
    print("=== ANALYZING TEST DATA PATTERNS ===")
    
    # Check mobile public key for patterns
    print(f"Mobile public key length: {len(mobile_public_key)} chars")
    
    # Look for repeating patterns in mobile public key
    pattern = "0e1f2d3c4b5a6978"
    count = mobile_public_key.count(pattern)
    print(f"Repeating pattern '{pattern}' appears {count} times in mobile public key")
    
    # Decode and analyze encrypted data
    username_bytes = base64.b64decode(encrypted_username)
    password_bytes = base64.b64decode(encrypted_password)
    
    print(f"\nUsername bytes: {username_bytes.hex()}")
    print(f"Password bytes: {password_bytes.hex()}")
    
    # Check for repeating patterns in encrypted data
    username_hex = username_bytes.hex()
    password_hex = password_bytes.hex()
    
    # Look for common patterns
    pattern1 = "123456789abcdedf"
    pattern2 = "1212233455689abc"
    
    print(f"\nPattern '{pattern1}' in username: {pattern1 in username_hex}")
    print(f"Pattern '{pattern2}' in username: {pattern2 in username_hex}")
    print(f"Pattern '{pattern1}' in password: {pattern1 in password_hex}")
    print(f"Pattern '{pattern2}' in password: {pattern2 in password_hex}")
    
    print("\n=== CONCLUSION ===")
    print("This appears to be test/dummy data with repeating patterns.")
    print("The mobile app likely generated placeholder encrypted values for testing.")
    print("For real decryption testing, we need actual encrypted credentials from the mobile app.")

if __name__ == "__main__":
    analyze_test_data()