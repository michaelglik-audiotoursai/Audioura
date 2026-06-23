#!/usr/bin/env python3
"""
T4 DB-Down → 503 Unit Test (no running service, no real DB)
=============================================================
Patches psycopg2.connect to raise OperationalError (simulating DB down).
Verifies the news orchestrator returns 503 on quota check failure.
"""
import sys
import os
from unittest.mock import patch, MagicMock

# Ensure imports find the service files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set minimal env so the service can import
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_NAME', 'audiotours')
os.environ.setdefault('DB_USER', 'admin')
os.environ.setdefault('DB_PASSWORD', 'test')
os.environ.setdefault('DB_PORT', '5432')

from news_orchestrator_service import app
import psycopg2

def test_db_down_returns_503():
    """When the DB is unreachable, /generate-news should return 503 (fail-closed).
    The entitlements module now RAISES on DB connection errors, which the orchestrator
    catches and returns 503 (quota_check_failed)."""
    client = app.test_client()
    
    # Patch psycopg2.connect to simulate DB being down (raises on connect)
    with patch('entitlements.psycopg2.connect', side_effect=psycopg2.OperationalError("connection refused")):
        response = client.post('/generate-news', 
                              json={'article_text': 'test', 'secret_id': 'TEST-USER-DBDOWN'},
                              content_type='application/json')
    
    print(f"T4 DB-Down Test:")
    print(f"  Status: {response.status_code}")
    print(f"  Body: {response.get_json()}")
    
    assert response.status_code == 503, f"Expected 503, got {response.status_code}: {response.get_json()}"
    body = response.get_json()
    assert body.get('error') == 'quota_check_failed', f"Expected error='quota_check_failed', got: {body}"
    
    print(f"  ✅ T4 PASS: DB down → 503 with error='quota_check_failed'")
    return True

def test_anonymous_still_401_with_db_down():
    """Anonymous should still get 401 (checked before DB), even if DB is down."""
    client = app.test_client()
    
    with patch('entitlements.psycopg2.connect', side_effect=psycopg2.OperationalError("connection refused")):
        response = client.post('/generate-news',
                              json={'article_text': 'test'},
                              content_type='application/json')
    
    print(f"\nT4b Anonymous with DB down:")
    print(f"  Status: {response.status_code}")
    
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print(f"  ✅ PASS: Anonymous → 401 (identity check precedes DB)")
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("T4: DB-Down → 503 Unit Test (mocked psycopg2)")
    print("=" * 60)
    
    try:
        t1 = test_db_down_returns_503()
        t2 = test_anonymous_still_401_with_db_down()
        
        print("\n" + "=" * 60)
        print("✅ ALL T4 CHECKS PASSED")
    except AssertionError as e:
        print(f"\n❌ ASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
