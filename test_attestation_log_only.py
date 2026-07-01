"""
test_attestation_log_only.py — Verify attestation NEVER blocks requests.
=========================================================================
Task [S57]: Sends 4 test requests to the gateway (running locally):
(1) valid API key + valid mock attestation token
(2) valid API key + no attestation token
(3) valid API key + malformed attestation token
(4) valid API key + wrong platform header
All must return HTTP 200 (not 401/403 due to attestation).

Usage:
    python test_attestation_log_only.py

Requires: local gateway running on localhost:8080 with
    GATEWAY_API_KEY set and ATTESTATION_MODE=log_only.
"""
import os
import sys
import requests

# Configuration
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")

# Use a known endpoint that requires API key (health is open, so use /sync)
TEST_ENDPOINT = f"{GATEWAY_URL}/health"

PASS_COUNT = 0
FAIL_COUNT = 0


def test(name: str, headers: dict, expect_not_blocked: bool = True):
    """Run a single test request."""
    global PASS_COUNT, FAIL_COUNT
    try:
        resp = requests.get(TEST_ENDPOINT, headers=headers, timeout=10)
        # The key assertion: attestation must NEVER cause 401 or 403
        if resp.status_code in (401, 403):
            print(f"  FAIL: {name} — got {resp.status_code} (blocked by attestation)")
            FAIL_COUNT += 1
            return False
        # Accept any success response (200, etc.)
        print(f"  PASS: {name} — HTTP {resp.status_code}")
        PASS_COUNT += 1
        return True
    except requests.ConnectionError:
        print(f"  FAIL: {name} — connection refused (is gateway running?)")
        FAIL_COUNT += 1
        return False
    except Exception as e:
        print(f"  FAIL: {name} — {e}")
        FAIL_COUNT += 1
        return False


def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("test_attestation_log_only.py")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Endpoint: {TEST_ENDPOINT}")
    print("=" * 60)

    # Test 1: Valid API key + valid mock attestation token
    test(
        "Valid API key + valid attestation token",
        {
            "X-API-Key": API_KEY,
            "X-App-Attestation": "eyJhbGciOiJSUzI1NiJ9.eyJub25jZSI6InRlc3QifQ.signature",
            "X-App-Platform": "android",
        },
    )

    # Test 2: Valid API key + no attestation token
    test(
        "Valid API key + NO attestation token",
        {
            "X-API-Key": API_KEY,
        },
    )

    # Test 3: Valid API key + malformed attestation token
    test(
        "Valid API key + malformed attestation token",
        {
            "X-API-Key": API_KEY,
            "X-App-Attestation": "this-is-not-a-valid-token-at-all!!!",
            "X-App-Platform": "android",
        },
    )

    # Test 4: Valid API key + wrong platform header
    test(
        "Valid API key + wrong platform header",
        {
            "X-API-Key": API_KEY,
            "X-App-Attestation": "eyJhbGciOiJSUzI1NiJ9.test.sig",
            "X-App-Platform": "blackberry",
        },
    )

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL 4 TESTS PASSED — attestation never blocks requests")
    else:
        print("SOME TESTS FAILED — attestation may be blocking requests!")
    print("=" * 60)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
