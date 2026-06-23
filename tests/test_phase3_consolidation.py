#!/usr/bin/env python3
"""
Test Phase 3 User Consolidation Logic
Tests device merging based on credential matching
"""

import requests
import json
import sys
from user_consolidation_service import user_consolidation_service

def test_consolidation_status():
    """Test consolidation status endpoint"""
    print("=== Testing Consolidation Status ===")
    
    # Test existing user
    response = requests.get("http://localhost:5017/get_user_consolidation_status/USER-281301397")
    if response.status_code == 200:
        data = response.json()
        print(f"USER-281301397 status: {data['consolidation_status']['status']}")
        print(f"   Domains: {data['consolidation_status']['domains']}")
        print(f"   Consolidated: {data['consolidation_status']['consolidated']}")
    else:
        print(f"Failed to get status: {response.status_code}")
    
    # Test non-existent user
    response = requests.get("http://localhost:5017/get_user_consolidation_status/NON-EXISTENT-USER")
    if response.status_code == 200:
        data = response.json()
        print(f"NON-EXISTENT-USER status: {data['consolidation_status']['status']}")
    else:
        print(f"Failed to get status for non-existent user: {response.status_code}")

def test_consolidation_logic_direct():
    """Test consolidation logic directly using the service"""
    print("\n=== Testing Consolidation Logic (Direct) ===")
    
    try:
        # Test scenario 1: New user with no matching credentials
        print("Test 1: New user with unique credentials")
        result = user_consolidation_service.handle_credential_submission_with_consolidation(
            "TEST-DEVICE-1", "testdomain.com", "unique@test.com", "uniquepass123"
        )
        print(f"Result: {result['action']} - {result['message']}")
        
        # Test scenario 2: Same credentials from different device (should merge)
        print("\nTest 2: Same credentials from different device")
        result = user_consolidation_service.handle_credential_submission_with_consolidation(
            "TEST-DEVICE-2", "testdomain.com", "unique@test.com", "uniquepass123"
        )
        print(f"Result: {result['action']} - {result.get('message', 'No message')}")
        
        if result['action'] == 'merged':
            print(f"   Consolidated User ID: {result['consolidated_user_id']}")
            print(f"   Primary Device: {result['primary_device']}")
            print(f"   Merged Device: {result['merged_device']}")
            print(f"   Synced Domains: {result['synced_domains']}")
        
        # Test scenario 3: Check consolidation status
        print("\nTest 3: Check consolidation status after merge")
        status1 = user_consolidation_service.get_consolidated_user_status("TEST-DEVICE-1")
        status2 = user_consolidation_service.get_consolidated_user_status("TEST-DEVICE-2")
        
        print(f"TEST-DEVICE-1 status: {status1['status']}, consolidated: {status1['consolidated']}")
        print(f"TEST-DEVICE-2 status: {status2['status']}, consolidated: {status2['consolidated']}")
        
        if status1['consolidated'] and status2['consolidated']:
            print(f"   Both devices share consolidated user: {status1['consolidated_user_id']}")
        
    except Exception as e:
        print(f"Direct consolidation test failed: {e}")

def test_cross_domain_conflicts():
    """Test cross-domain conflict detection"""
    print("\n=== Testing Cross-Domain Conflicts ===")
    
    try:
        # Create two devices with same credentials for domain1 but different for domain2
        print("Setting up conflict scenario...")
        
        # Device A: domain1 + domain2 with specific credentials
        user_consolidation_service.handle_credential_submission_with_consolidation(
            "CONFLICT-DEVICE-A", "domain1.com", "user@test.com", "password123"
        )
        user_consolidation_service.handle_credential_submission_with_consolidation(
            "CONFLICT-DEVICE-A", "domain2.com", "user@test.com", "password456"
        )
        
        # Device B: same domain1 credentials, different domain2 credentials
        result1 = user_consolidation_service.handle_credential_submission_with_consolidation(
            "CONFLICT-DEVICE-B", "domain1.com", "user@test.com", "password123"
        )
        print(f"Same domain1 credentials: {result1['action']}")
        
        # This should detect conflict when adding domain2
        user_consolidation_service.handle_credential_submission_with_consolidation(
            "CONFLICT-DEVICE-B", "domain2.com", "different@test.com", "differentpass"
        )
        
        # Now try to merge again - should detect conflict
        result2 = user_consolidation_service.handle_credential_submission_with_consolidation(
            "CONFLICT-DEVICE-C", "domain1.com", "user@test.com", "password123"
        )
        print(f"Conflict detection result: {result2['action']}")
        
        if result2['action'] == 'separate':
            print(f"   Reason: {result2.get('reason', 'Unknown')}")
        
    except Exception as e:
        print(f"Cross-domain conflict test failed: {e}")

def cleanup_test_data():
    """Clean up test data"""
    print("\n=== Cleaning Up Test Data ===")
    
    try:
        import psycopg2
        conn = psycopg2.connect(
            host='localhost',
            database='audiotours',
            user='admin',
            password='password123',
            port='5433'
        )
        cursor = conn.cursor()
        
        # Delete test credentials
        test_devices = ['TEST-DEVICE-1', 'TEST-DEVICE-2', 'CONFLICT-DEVICE-A', 'CONFLICT-DEVICE-B', 'CONFLICT-DEVICE-C']
        test_domains = ['testdomain.com', 'domain1.com', 'domain2.com']
        
        for device in test_devices:
            cursor.execute("DELETE FROM user_subscription_credentials WHERE device_id = %s", (device,))
        
        # Delete test consolidation records
        cursor.execute("DELETE FROM device_consolidation_history WHERE merged_device_id = ANY(%s)", (test_devices,))
        cursor.execute("DELETE FROM user_consolidation_map WHERE primary_device_id = ANY(%s)", (test_devices,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Test data cleaned up")
        
    except Exception as e:
        print(f"Cleanup failed: {e}")

if __name__ == "__main__":
    print("Phase 3 User Consolidation Test Suite")
    print("=" * 50)
    
    # Run tests
    test_consolidation_status()
    test_consolidation_logic_direct()
    test_cross_domain_conflicts()
    
    # Cleanup
    cleanup_test_data()
    
    print("\nPhase 3 testing complete!")