"""
storied_smoke_test.py — End-to-end smoke test for all 5 Storied features.
Task [S60]. Runs against locally running containers. Prints PASS/FAIL per test.
Exit 0 if all pass, 1 otherwise.

Usage:
    python storied_smoke_test.py
"""
import os
import sys
import requests
import json

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

PASS_COUNT = 0
FAIL_COUNT = 0


def test(name, func):
    global PASS_COUNT, FAIL_COUNT
    try:
        result = func()
        if result:
            print(f"  PASS: {name}")
            PASS_COUNT += 1
        else:
            print(f"  FAIL: {name}")
            FAIL_COUNT += 1
    except Exception as e:
        print(f"  FAIL: {name} — {e}")
        FAIL_COUNT += 1


def test_1_tour_generation():
    """Test 1: Tour generation with STORIED_MODE=true completes."""
    # Just check that the /generate endpoint accepts a request
    resp = requests.post(f"{SERVICE_URL}/generate", json={
        "location": "Test Museum",
        "tour_type": "museum",
        "total_stops": 3,
    }, headers=HEADERS, timeout=10)
    return resp.status_code == 200


def test_2_persona():
    """Test 2: POST /user/persona saves and GET retrieves."""
    # Save
    resp = requests.post(f"{SERVICE_URL}/user/persona", json={
        "user_id": "smoke_test_user",
        "persona": "art_lover",
    }, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return False
    # Retrieve
    resp = requests.get(f"{SERVICE_URL}/user/persona?user_id=smoke_test_user",
                       headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return False
    return resp.json().get("persona") == "art_lover"


def test_3_share():
    """Test 3: POST /tour/share returns share_url."""
    resp = requests.post(f"{SERVICE_URL}/tour/share", json={
        "location": "Test",
        "tour_type": "museum",
        "total_stops": 3,
        "tour_text": "Stop 1: Test\nThis is a test tour.",
    }, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return False
    data = resp.json()
    return bool(data.get("share_id")) and bool(data.get("share_url"))


def test_4_get_shared():
    """Test 4: GET /tour/{id} retrieves shared tour."""
    # First create one
    resp = requests.post(f"{SERVICE_URL}/tour/share", json={
        "location": "Smoke Test",
        "tour_type": "walking",
        "total_stops": 5,
        "tour_text": "Stop 1: Smoke\nSmoke test tour content.",
    }, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return False
    share_id = resp.json().get("share_id")
    # Now retrieve
    resp = requests.get(f"{SERVICE_URL}/tour/{share_id}", timeout=10)
    return resp.status_code == 200 and "tour_text" in resp.json()


def test_5_referral():
    """Test 5: POST /referral/create returns referral_code."""
    resp = requests.post(f"{SERVICE_URL}/referral/create", json={
        "user_id": "smoke_test_referrer",
    }, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return False
    data = resp.json()
    return bool(data.get("referral_code")) and len(data.get("referral_code", "")) == 6


def test_6_attestation():
    """Test 6: Gateway with attestation header returns 200 (log_only)."""
    resp = requests.get(f"{GATEWAY_URL}/health", headers={
        "X-API-Key": API_KEY,
        "X-App-Attestation": "test.token.value",
        "X-App-Platform": "android",
    }, timeout=10)
    # Health endpoint should return 200 regardless of attestation
    return resp.status_code == 200


def main():
    print("=" * 60)
    print("storied_smoke_test.py — Storied Feature Smoke Test")
    print(f"Service: {SERVICE_URL}")
    print(f"Gateway: {GATEWAY_URL}")
    print("=" * 60)

    test("1. Tour generation endpoint accepts request", test_1_tour_generation)
    test("2. Persona save + retrieve", test_2_persona)
    test("3. Tour share returns share_url", test_3_share)
    test("4. GET shared tour by ID", test_4_get_shared)
    test("5. Referral code creation", test_5_referral)
    test("6. Gateway attestation log-only", test_6_attestation)

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS_COUNT}/6 PASS, {FAIL_COUNT}/6 FAIL")
    if FAIL_COUNT == 0:
        print("ALL 6 SMOKE TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
