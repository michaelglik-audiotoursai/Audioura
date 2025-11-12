#!/usr/bin/env python3

import psycopg2

def find_newsletter_by_public_key():
    # Server public key from mobile app logs
    mobile_app_received = "581efd62213962de713420d12794ae421bf9e2fe0830584a3284199cbadbec06a0e9986f2530390e9f1da771548a6fbdd0028e434b6430b224fdbb6fe0983a904a3e7ae74a3440a2db097ae097a784b91eed5e30b63214a4885577847f000623de317827481bdd43a8ee9dcc3dab04820782c85fad656b9624b821ae2e6e7c39621b592873e3b796eb2d52c6869fe40672c3a7f556cce80f4c96c798962eab0cfade6d5cc956d4d54225e7776c23f46ccd1e5426b7079ad4ae046c1a945d20a6eb525225cfff9b29c3f88ef2480b9f5de93a793b4c438e391029756db384a687467023eb97ccf837674756e37911d7974acf733c29144bac7e58b1c67a91c510"
    
    # RFC 3526 Group 14 parameters
    P = int("FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183560791C6BD3F2C0F6CC41659", 16)
    G = 2
    
    # Connect to database
    conn = psycopg2.connect(
        host='localhost',
        database='audiotours',
        user='admin',
        password='password123',
        port='5433'
    )
    cursor = conn.cursor()
    
    # Get all newsletter server keys
    cursor.execute("SELECT newsletter_id, private_key FROM newsletter_server_keys ORDER BY newsletter_id;")
    results = cursor.fetchall()
    
    print("=== SEARCHING FOR CORRECT NEWSLETTER ===")
    print(f"Target public key: {mobile_app_received[:64]}...")
    print()
    
    for newsletter_id, private_key in results:
        # Calculate public key for this newsletter
        calculated_public_key = pow(G, int(private_key), P)
        calculated_hex = hex(calculated_public_key)[2:]
        
        print(f"Newsletter {newsletter_id}: {calculated_hex[:64]}...")
        
        if calculated_hex == mobile_app_received:
            print(f"*** MATCH FOUND: Newsletter {newsletter_id} ***")
            cursor.close()
            conn.close()
            return newsletter_id, private_key
    
    print("No matching newsletter found!")
    cursor.close()
    conn.close()
    return None, None

if __name__ == "__main__":
    newsletter_id, private_key = find_newsletter_by_public_key()
    if newsletter_id:
        print(f"The mobile app used server keys from Newsletter {newsletter_id}")
        print(f"Private key: {private_key}")
    else:
        print("Could not find matching newsletter - this explains the decryption failure")