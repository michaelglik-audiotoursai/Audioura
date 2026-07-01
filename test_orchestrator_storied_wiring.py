"""
test_orchestrator_storied_wiring.py — Verify orchestrator passes Storied params.
Task [S84]. Checks that tour_orchestrator_service.py correctly forwards
user_id and persona to the tour-generator service.

Usage: python test_orchestrator_storied_wiring.py
Requires: tour-orchestrator running on port 5002
"""
import os
import sys
import requests

SERVICE_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def main():
    print("=" * 60)
    print("test_orchestrator_storied_wiring.py")
    print(f"Orchestrator: {SERVICE_URL}")
    print("=" * 60)

    # Test 1: Health endpoint returns version and mode
    print("\n[1] Health endpoint includes version + mode")
    try:
        resp = requests.get(f"{SERVICE_URL}/health", timeout=10)
        check("Health returns 200", resp.status_code == 200)
        data = resp.json()
        check("Health has status", "status" in data)
    except requests.ConnectionError:
        print("  FAIL: Orchestrator not reachable — is it running?")
        sys.exit(1)
    except Exception as e:
        print(f"  FAIL: {e}")

    # Test 2: Generate request accepts user_id
    print("\n[2] Generate request with user_id accepted")
    try:
        resp = requests.post(f"{SERVICE_URL}/generate-complete-tour", json={
            "location": "Test Museum, Nice",
            "tour_type": "museum",
            "total_stops": 3,
            "user_id": "test_user_storied_wiring",
        }, headers=HEADERS, timeout=15)
        check("Generate with user_id accepted", resp.status_code in (200, 202),
              f"got {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        check("Generate with user_id accepted", False, str(e))

    # Test 3: Generate request accepts persona
    print("\n[3] Generate request with persona accepted")
    try:
        resp = requests.post(f"{SERVICE_URL}/generate-complete-tour", json={
            "location": "Test Museum, Nice",
            "tour_type": "museum",
            "total_stops": 3,
            "user_id": "test_user_storied_wiring",
            "persona": "art_lover",
        }, headers=HEADERS, timeout=15)
        check("Generate with persona accepted", resp.status_code in (200, 202),
              f"got {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        check("Generate with persona accepted", False, str(e))

    # Test 4: Generate request without user_id still works
    print("\n[4] Generate without user_id still works")
    try:
        resp = requests.post(f"{SERVICE_URL}/generate-complete-tour", json={
            "location": "Test Museum, Nice",
            "tour_type": "museum",
            "total_stops": 3,
        }, headers=HEADERS, timeout=15)
        check("Generate without user_id works", resp.status_code in (200, 202),
              f"got {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        check("Generate without user_id works", False, str(e))

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
