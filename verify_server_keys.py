#!/usr/bin/env python3
"""
Verify server key calculations and find the correct server private key
"""

# RFC 3526 Group 14 parameters (2048-bit)
DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)
DH_GENERATOR = 2

def verify_server_keys():
    """Verify which server private key produces the mobile app's server public key"""
    
    # Server public key that mobile app received
    mobile_received_server_public_hex = "581efd62213962de713420d12794ae421bf9e2fe0830584a3284199cbadbec06a0e9986f2530390e9f1da771548a6fbdd0028e434b6430b224fdbb6fe0983a904a3e7ae74a3440a2db097ae097a784b91eed5e30b63214a4885577847f000623de317827481bdd43a8ee9dcc3dab04820782c85fad656b9624b821ae2e6e7c39621b592873e3b796eb2d52c6869fe40672c3a7f556cce80f4c96c798962eab0cfade6d5cc956d4d54225e7776c23f46ccd1e5426b7079ad4ae046c1a945d20a6eb525225cfff9b29c3f88ef2480b9f5de93a793b4c438e391029756db384a687467023eb97ccf837674756e37911d7974acf733c29144bac7e58b1c67a91c510"
    
    mobile_received_server_public = int(mobile_received_server_public_hex, 16)
    
    print("=== SERVER KEY VERIFICATION ===")
    print(f"Mobile app received server public key: {mobile_received_server_public}")
    print()
    
    # Test known server private keys from database
    test_keys = [
        ("Newsletter 174", 23341236479817520700106440276798823353781619641231018265294860013864666580890),
        ("Newsletter 169", 1855699527122823605301096117990787629509201203106440200973732878362536081808)
    ]
    
    for name, private_key in test_keys:
        calculated_public = pow(DH_GENERATOR, private_key, DH_PRIME)
        matches = calculated_public == mobile_received_server_public
        
        print(f"{name}:")
        print(f"  Private Key: {private_key}")
        print(f"  Calculated Public: {calculated_public}")
        print(f"  Matches Mobile: {matches}")
        
        if matches:
            print(f"  *** FOUND MATCH! Mobile app used {name} server key ***")
        print()
    
    # Try to find the correct private key by brute force (if it's a small range)
    print("Searching for correct private key...")
    
    # Check if it could be a different newsletter's key
    import psycopg2
    import os
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5433')
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT newsletter_id, private_key FROM newsletter_server_keys")
        all_keys = cursor.fetchall()
        
        print(f"Checking all {len(all_keys)} server keys in database...")
        
        for newsletter_id, private_key_str in all_keys:
            private_key = int(private_key_str)
            calculated_public = pow(DH_GENERATOR, private_key, DH_PRIME)
            
            if calculated_public == mobile_received_server_public:
                print(f"*** MATCH FOUND! Newsletter {newsletter_id} has the correct server key ***")
                print(f"Private Key: {private_key}")
                return newsletter_id, private_key
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Database error: {e}")
    
    print("No matching server private key found in database!")
    return None, None

if __name__ == "__main__":
    verify_server_keys()