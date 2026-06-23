#!/usr/bin/env python3
"""
Realistic Phase 3 User Consolidation Test
Tests device merging with actual database operations
"""

import psycopg2
import os
from user_consolidation_service import user_consolidation_service

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5433')
    )

def store_test_credentials(device_id, domain, username, password):
    """Store test credentials in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_subscription_credentials 
            (device_id, article_id, domain, decrypted_username, decrypted_password)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (device_id, domain) 
            DO UPDATE SET 
                decrypted_username = EXCLUDED.decrypted_username,
                decrypted_password = EXCLUDED.decrypted_password,
                created_at = NOW()
        """, (device_id, 'test-article-id', domain, username, password))
        
        conn.commit()
        print(f"Stored credentials for {device_id} on {domain}")
        
    finally:
        cursor.close()
        conn.close()

def test_realistic_consolidation():
    """Test realistic consolidation scenario"""
    print("=== Realistic Phase 3 Consolidation Test ===")
    
    # Scenario 1: Create first device with Boston Globe credentials
    print("\n1. Creating first device with Boston Globe credentials")
    store_test_credentials("DEVICE-A", "bostonglobe.com", "test@example.com", "password123")
    
    status_a = user_consolidation_service.get_consolidated_user_status("DEVICE-A")
    print(f"   DEVICE-A status: {status_a['status']}, consolidated: {status_a['consolidated']}")
    
    # Scenario 2: Create second device with SAME Boston Globe credentials
    print("\n2. Creating second device with SAME Boston Globe credentials")
    store_test_credentials("DEVICE-B", "bostonglobe.com", "test@example.com", "password123")
    
    # Test consolidation logic
    consolidation_result = user_consolidation_service.handle_credential_submission_with_consolidation(
        "DEVICE-B", "bostonglobe.com", "test@example.com", "password123"
    )
    
    print(f"   Consolidation result: {consolidation_result['action']}")
    if consolidation_result['action'] == 'merged':
        print(f"   Consolidated User ID: {consolidation_result['consolidated_user_id']}")
        print(f"   Primary Device: {consolidation_result['primary_device']}")
        print(f"   Merged Device: {consolidation_result['merged_device']}")
    
    # Check status after consolidation
    status_a_after = user_consolidation_service.get_consolidated_user_status("DEVICE-A")
    status_b_after = user_consolidation_service.get_consolidated_user_status("DEVICE-B")
    
    print(f"   DEVICE-A after: {status_a_after['status']}, consolidated: {status_a_after['consolidated']}")
    print(f"   DEVICE-B after: {status_b_after['status']}, consolidated: {status_b_after['consolidated']}")
    
    # Scenario 3: Test cross-domain conflict
    print("\n3. Testing cross-domain conflict scenario")
    
    # Add NYTimes credentials to DEVICE-A
    store_test_credentials("DEVICE-A", "nytimes.com", "test@example.com", "nytimes123")
    
    # Create DEVICE-C with same Boston Globe but different NYTimes credentials
    store_test_credentials("DEVICE-C", "bostonglobe.com", "test@example.com", "password123")
    store_test_credentials("DEVICE-C", "nytimes.com", "different@example.com", "differentpass")
    
    # Try to consolidate DEVICE-C (should detect conflict)
    conflict_result = user_consolidation_service.handle_credential_submission_with_consolidation(
        "DEVICE-C", "bostonglobe.com", "test@example.com", "password123"
    )
    
    print(f"   Conflict test result: {conflict_result['action']}")
    if conflict_result['action'] == 'separate':
        print(f"   Reason: {conflict_result.get('reason', 'Unknown')}")
    
    # Scenario 4: Test perfect match (no conflicts)
    print("\n4. Testing perfect match scenario")
    
    # Create DEVICE-D with EXACT same credentials as DEVICE-A (both domains)
    store_test_credentials("DEVICE-D", "bostonglobe.com", "test@example.com", "password123")
    store_test_credentials("DEVICE-D", "nytimes.com", "test@example.com", "nytimes123")
    
    perfect_match_result = user_consolidation_service.handle_credential_submission_with_consolidation(
        "DEVICE-D", "bostonglobe.com", "test@example.com", "password123"
    )
    
    print(f"   Perfect match result: {perfect_match_result['action']}")
    if perfect_match_result['action'] == 'merged':
        print(f"   Synced domains: {perfect_match_result['synced_domains']}")
        print(f"   Available subscriptions: {perfect_match_result['available_subscriptions']}")

def cleanup_test_data():
    """Clean up test data"""
    print("\n=== Cleaning Up Test Data ===")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete test credentials
        test_devices = ['DEVICE-A', 'DEVICE-B', 'DEVICE-C', 'DEVICE-D']
        
        for device in test_devices:
            cursor.execute("DELETE FROM user_subscription_credentials WHERE device_id = %s", (device,))
        
        # Delete test consolidation records
        cursor.execute("DELETE FROM device_consolidation_history WHERE merged_device_id = ANY(%s)", (test_devices,))
        cursor.execute("DELETE FROM user_consolidation_map WHERE primary_device_id = ANY(%s)", (test_devices,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Test data cleaned up successfully")
        
    except Exception as e:
        print(f"Cleanup failed: {e}")

if __name__ == "__main__":
    print("Phase 3 Realistic User Consolidation Test")
    print("=" * 50)
    
    try:
        test_realistic_consolidation()
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_test_data()
    
    print("\nRealistic Phase 3 testing complete!")