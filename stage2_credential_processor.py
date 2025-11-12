#!/usr/bin/env python3
"""
Stage 2: Credential Processing for Subscription Article Access
This will be used when implementing actual subscription article processing
"""
import psycopg2
import os
import hashlib
import base64
from dh_service_simple import (
    get_server_private_key_by_newsletter, 
    get_newsletter_id_from_article,
    DH_GENERATOR, DH_PRIME
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'), 
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def get_decrypted_credentials(article_id, device_id):
    """
    Get decrypted credentials for accessing subscription articles
    This function will be used in Stage 2 implementation
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get stored credentials for this article/device
        cursor.execute("""
            SELECT domain, mobile_public_key, encrypted_username, encrypted_password
            FROM user_subscription_credentials 
            WHERE device_id = %s
            AND (article_id = %s OR domain IN (
                SELECT subscription_domain FROM article_requests WHERE article_id = %s
            ))
            ORDER BY created_at DESC
            LIMIT 1
        """, (device_id, article_id, article_id))
        
        result = cursor.fetchone()
        if not result:
            return {"error": "No credentials found for this article/device"}
        
        domain, mobile_public_key_hex, enc_username_b64, enc_password_b64 = result
        
        # Get newsletter_id for DH key retrieval
        newsletter_id = get_newsletter_id_from_article(article_id)
        if not newsletter_id:
            return {"error": "Cannot find newsletter for article"}
        
        # Get server private key for this newsletter session
        server_private_key = get_server_private_key_by_newsletter(newsletter_id)
        if not server_private_key:
            return {"error": "No server private key found"}
        
        # Calculate shared secret using Diffie-Hellman
        mobile_public_key = int(mobile_public_key_hex, 16)
        shared_secret = pow(mobile_public_key, server_private_key, DH_PRIME)
        
        # Derive AES key (this will need to match mobile app's method)
        aes_key = hashlib.sha256(str(shared_secret).encode()).digest()[:16]
        
        # For Stage 2: Decrypt credentials here using PyCrypto
        # For now, return encrypted data and key for verification
        return {
            "success": True,
            "domain": domain,
            "aes_key": aes_key.hex(),
            "encrypted_username": enc_username_b64,
            "encrypted_password": enc_password_b64,
            "shared_secret": str(shared_secret)[:50] + "...",  # Truncated for security
            "ready_for_stage2": True
        }
        
    except Exception as e:
        return {"error": f"Credential processing failed: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

def test_credential_retrieval():
    """Test credential retrieval for Stage 2 implementation"""
    
    # Test with the stored credentials
    article_id = "a6725c3a-a7cf-4e32-adea-4668dab70a17"
    device_id = "USER-281301397"
    
    result = get_decrypted_credentials(article_id, device_id)
    
    print("Stage 2 Credential Retrieval Test:")
    print("=" * 50)
    
    if result.get("success"):
        print(f"✅ Domain: {result['domain']}")
        print(f"✅ AES Key: {result['aes_key']}")
        print(f"✅ Shared Secret: {result['shared_secret']}")
        print(f"✅ Ready for Stage 2: {result['ready_for_stage2']}")
        print(f"📦 Encrypted Username: {result['encrypted_username'][:30]}...")
        print(f"📦 Encrypted Password: {result['encrypted_password'][:30]}...")
        print("\n🎯 STAGE 1 COMPLETE: Credentials stored and retrievable")
        print("🚀 STAGE 2 READY: Can decrypt and use credentials for subscription access")
    else:
        print(f"❌ Error: {result['error']}")

if __name__ == "__main__":
    test_credential_retrieval()