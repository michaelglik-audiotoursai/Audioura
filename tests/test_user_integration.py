#!/usr/bin/env python3
"""
Test script for user tracking integration

LOCAL-141: Migrated to TestTourFactory.adopt_and_ensure_flagged() — the flag
is set structurally after HTTP creation, regardless of Docker env vars.
"""
import os
import sys
import requests
import json
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_tour_factory import TestTourFactory
from db_connection import get_connection

# Factory instance — adopt tours created via HTTP so is_test=TRUE is structural
_factory = TestTourFactory(auto_cleanup=True)


@pytest.mark.service
def test_user_integration():
    print("Testing User Tracking Integration")
    print("=" * 50)
    
    # Test 1: Add user
    print("1. Adding test user...")
    user_id = "test_user_123"
    
    response = requests.post(
        "http://localhost:5003/user",
        headers={"Content-Type": "application/json"},
        json={
            "secret_id": user_id,
            "coordinates": {"lat": 42.325417, "lng": -71.202111}
        }
    )
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    # Test 2: Generate tour with user tracking
    print("\n2. Generating tour with user tracking...")
    
    tour_data = {
        "location": "Boston Common",
        "tour_type": "walking",
        "total_stops": 5,
        "user_id": user_id,
        "request_string": "Please generate a walking tour of Boston Common",
        "is_test": True,  # LOCAL-103: mark HTTP-generated test tours
    }
    
    response = requests.post(
        "http://localhost:5002/generate-complete-tour",
        headers={"Content-Type": "application/json"},
        json=tour_data
    )
    
    if response.status_code == 200:
        job_data = response.json()
        job_id = job_data["job_id"]
        print(f"   Job ID: {job_id}")
        
        # Wait a bit for processing to start
        time.sleep(5)
        
        # Check status
        status_response = requests.get(f"http://localhost:5002/status/{job_id}")
        if status_response.status_code == 200:
            status = status_response.json()
            print(f"   Status: {status['status']}")
            print(f"   Progress: {status['progress']}")
            
            # LOCAL-141: Adopt the tour if completed
            tour_id = status.get('final_tour_id')
            if tour_id:
                _factory.adopt_and_ensure_flagged(tour_id)
                print(f"   ✅ Tour {tour_id} adopted and flagged is_test=TRUE")
            elif status['status'] == 'completed':
                # Try to find by name
                conn = get_connection()
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM audio_tours WHERE tour_name ILIKE %s ORDER BY id DESC LIMIT 1",
                    ('%Boston Common%',)
                )
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row:
                    _factory.adopt_and_ensure_flagged(row[0])
                    print(f"   ✅ Tour {row[0]} found by name and flagged is_test=TRUE")
        
    else:
        print(f"   Error: {response.status_code} - {response.text}")
    
    # Test 3: Check user data
    print("\n3. Checking user tracking data...")
    
    response = requests.get(f"http://localhost:5003/user/{user_id}")
    if response.status_code == 200:
        user_data = response.json()
        print(f"   User ID: {user_data['secret_id']}")
        print(f"   Total Records: {user_data['total_records']}")
        print(f"   Coordinates: {len(user_data['coordinates'])} records")
        print(f"   Tours: {len(user_data['tours'])} records")
        
        if user_data['tours']:
            for i, tour in enumerate(user_data['tours']):
                # [D223] request_string can be None on a tour the API returns
                # before generation has populated it. This is a diagnostic print;
                # it must not crash the test. Whether the column should be
                # NOT NULL is a schema question for Michael, not a test fix.
                _req = tour.get('request_string') or '(no request_string)'
                print(f"     Tour {i+1}: {tour['tour_id']} - {_req[:50]}...")
    else:
        print(f"   Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_user_integration()