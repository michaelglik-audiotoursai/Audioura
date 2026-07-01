"""
test_sharing_deep_link.py — Verify share URL resolves to correct tour.
=======================================================================
Task [S75]: End-to-end test for tour sharing:
1. Generate tour text (mock or real)
2. POST /tour/share → get share_id + share_url
3. GET /tour/{id} → verify tour_text matches original
4. Verify share_count increments on each retrieval

Usage:
    python test_sharing_deep_link.py

Requires: local tour-generator service running with sharing_endpoints
registered, and DATABASE_URL pointing to Postgres with shared_tours table.
"""
import os
import sys
import requests

# Configuration
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Test tour data
TOUR_TEXT = """Stop 1: Musée National Marc Chagall
The Chagall Museum in Nice houses the world's largest collection of Marc Chagall's Biblical Message paintings.

Stop 2: Message Biblique Hall
Seventeen monumental canvases depict scenes from Genesis and Exodus in Chagall's signature luminous colors.

Stop 3: Concert Hall
The auditorium features three stunning stained-glass windows by Chagall depicting The Creation of the World.
"""

LOCATION = "Chagall Museum Nice"
TOUR_TYPE = "museum"
TOTAL_STOPS = 3

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    """Assert and report."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("test_sharing_deep_link.py")
    print(f"Service: {SERVICE_URL}")
    print("=" * 60)

    # Step 1: POST /tour/share
    print("\n[1] POST /tour/share")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/tour/share",
            json={
                "location": LOCATION,
                "tour_type": TOUR_TYPE,
                "total_stops": TOTAL_STOPS,
                "tour_text": TOUR_TEXT,
            },
            headers=HEADERS,
            timeout=10,
        )
        check("POST returns 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        share_id = data.get("share_id", "")
        share_url = data.get("share_url", "")
        check("Response has share_id", bool(share_id), f"got: {data}")
        check("Response has share_url", bool(share_url), f"got: {data}")
        check("share_id is 8-char alphanumeric", len(share_id) == 8 and share_id.isalnum(), f"got: '{share_id}'")
    except requests.ConnectionError:
        print("  FAIL: Connection refused (is service running?)")
        sys.exit(1)
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # Step 2: GET /tour/{id} — first retrieval
    print(f"\n[2] GET /tour/{share_id} (first retrieval)")
    try:
        resp = requests.get(f"{SERVICE_URL}/tour/{share_id}", timeout=10)
        check("GET returns 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        check("tour_text matches original", data.get("tour_text") == TOUR_TEXT, "text mismatch")
        check("share_count is 1", data.get("share_count") == 1, f"got: {data.get('share_count')}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 3: GET /tour/{id} — second retrieval
    print(f"\n[3] GET /tour/{share_id} (second retrieval)")
    try:
        resp = requests.get(f"{SERVICE_URL}/tour/{share_id}", timeout=10)
        data = resp.json()
        check("share_count incremented to 2", data.get("share_count") == 2, f"got: {data.get('share_count')}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 4: Second POST with same inputs returns same share_id (idempotent)
    print("\n[4] POST /tour/share again (idempotency)")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/tour/share",
            json={
                "location": LOCATION,
                "tour_type": TOUR_TYPE,
                "total_stops": TOTAL_STOPS,
                "tour_text": TOUR_TEXT,
            },
            headers=HEADERS,
            timeout=10,
        )
        data = resp.json()
        check("Same inputs → same share_id", data.get("share_id") == share_id, f"got: {data.get('share_id')}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 5: GET /tour/nonexistent → 404
    print("\n[5] GET /tour/nonexistent → 404")
    try:
        resp = requests.get(f"{SERVICE_URL}/tour/zzzzzzzz", timeout=10)
        check("Nonexistent tour returns 404", resp.status_code == 404, f"got {resp.status_code}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
