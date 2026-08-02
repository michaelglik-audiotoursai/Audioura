#!/usr/bin/env python3
"""
Test the user tracking fix

LOCAL-141: Migrated to TestTourFactory.adopt_and_ensure_flagged() — the flag
is set structurally after HTTP creation, regardless of Docker env vars.
"""
import os
import sys
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_tour_factory import TestTourFactory
from db_connection import get_connection

# Factory instance — adopt tours created via HTTP so is_test=TRUE is structural
_factory = TestTourFactory(auto_cleanup=True)

def test_tracking_fix():
    print("Testing User Tracking Fix")
    print("=" * 30)
    
    # Test with the actual user ID
    user_id = "txzs7duahw03g8l0"
    
    # Generate a test tour
    tour_data = {
        "location": "Test Museum Boston",
        "tour_type": "walking",
        "total_stops": 3,
        "user_id": user_id,
        "request_string": "Test tour for tracking verification",
        "is_test": True,  # LOCAL-103: mark HTTP-generated test tours
    }
    
    print(f"1. Starting tour for user: {user_id}")
    response = requests.post(
        'http://192.168.0.217:5002/generate-complete-tour',
        headers={'Content-Type': 'application/json'},
        json=tour_data
    )
    
    if response.status_code == 200:
        job_id = response.json()['job_id']
        print(f"   Job started: {job_id}")
        
        # Wait a bit for processing
        print("2. Waiting for processing...")
        time.sleep(10)
        
        # LOCAL-141: Poll for tour_id and adopt it
        try:
            sr = requests.get(f'http://192.168.0.217:5002/status/{job_id}', timeout=10)
            if sr.status_code == 200:
                sd = sr.json()
                tour_id = sd.get('final_tour_id')
                if tour_id:
                    _factory.adopt_and_ensure_flagged(tour_id)
                    print(f"   ✅ Tour {tour_id} adopted and flagged is_test=TRUE")
                elif sd.get('status') == 'completed':
                    # Try to find by name
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM audio_tours WHERE tour_name ILIKE %s ORDER BY id DESC LIMIT 1",
                        ('%Test Museum Boston%',)
                    )
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    if row:
                        _factory.adopt_and_ensure_flagged(row[0])
                        print(f"   ✅ Tour {row[0]} found by name and flagged is_test=TRUE")
        except Exception as e:
            print(f"   ⚠️ Could not adopt tour (will be caught by guard): {e}")
        
        # Check user data
        print("3. Checking user tracking...")
        user_response = requests.get(f'http://192.168.0.217:5003/user/{user_id}')
        
        if user_response.status_code == 200:
            user_data = user_response.json()
            tours_count = len(user_data.get('tours', []))
            print(f"   User found: {tours_count} tours recorded")
            
            if tours_count > 0:
                print("   SUCCESS: User tracking is working!")
                for tour in user_data.get('tours', []):
                    print(f"   - {tour.get('request_string', 'N/A')}")
            else:
                print("   WARNING: No tours found yet (may need more time)")
        else:
            print(f"   ERROR: User not found: {user_response.status_code}")
    else:
        print(f"   ERROR: Tour generation failed: {response.status_code}")

if __name__ == "__main__":
    test_tracking_fix()