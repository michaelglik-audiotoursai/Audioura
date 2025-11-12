#!/usr/bin/env python3
import base64
import psycopg2

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    database='audiotours', 
    user='admin',
    password='password123',
    port='5433'
)

cursor = conn.cursor()
cursor.execute("""
    SELECT encrypted_username, encrypted_password
    FROM user_subscription_credentials 
    WHERE device_id = 'USER-281301397'
    ORDER BY created_at DESC LIMIT 1
""")

result = cursor.fetchone()
if result:
    enc_username, enc_password = result
    
    print("RAW ENCRYPTED DATA ANALYSIS:")
    print(f"Username (base64): {enc_username}")
    print(f"Password (base64): {enc_password}")
    
    # Decode and examine
    try:
        username_bytes = base64.b64decode(enc_username)
        password_bytes = base64.b64decode(enc_password)
        
        print(f"\nUsername bytes length: {len(username_bytes)}")
        print(f"Username bytes (hex): {username_bytes.hex()}")
        print(f"Password bytes length: {len(password_bytes)}")
        print(f"Password bytes (hex): {password_bytes.hex()}")
        
        # Check if it's simple base64 encoding (not AES)
        try:
            simple_username = base64.b64decode(enc_username).decode('utf-8')
            simple_password = base64.b64decode(enc_password).decode('utf-8')
            print(f"\nIF SIMPLE BASE64 (not AES):")
            print(f"Username: {simple_username}")
            print(f"Password: {simple_password}")
        except:
            print("\nNot simple base64 encoding")
            
    except Exception as e:
        print(f"Error: {e}")

cursor.close()
conn.close()