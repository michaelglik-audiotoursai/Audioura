"""
test_referral_flow.py — Verify referral code create → redeem → attribution.
=============================================================================
Task [S76]: End-to-end test:
1. Create referral code for "user_001" via POST /referral/create
2. Assert code is 6-char alphanumeric
3. Redeem code as "new_user_001" via POST /referral/redeem
4. Assert response contains referrer_user_id: "user_001"
5. Redeem same code again as "new_user_002"
6. Assert second redemption succeeds
7. Attempt redeem with unknown code → 404

Usage:
    python test_referral_flow.py

Requires: local service running with referral_endpoints registered,
and DATABASE_URL pointing to Postgres with referral tables.
"""
import os
import sys
import requests

# Configuration
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

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
    print("test_referral_flow.py")
    print(f"Service: {SERVICE_URL}")
    print("=" * 60)

    referral_code = ""

    # Step 1: Create referral code for "user_001"
    print("\n[1] POST /referral/create {user_id: 'user_001'}")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": "user_001"},
            headers=HEADERS,
            timeout=10,
        )
        check("POST returns 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        referral_code = data.get("referral_code", "")
        check("referral_code is 6-char alphanumeric",
              len(referral_code) == 6 and referral_code.isalnum(),
              f"got: '{referral_code}'")
        check("referral_url present", bool(data.get("referral_url")), f"got: {data}")
    except requests.ConnectionError:
        print("  FAIL: Connection refused (is service running?)")
        sys.exit(1)
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # Step 2: Same user_id → same referral_code (deterministic)
    print("\n[2] POST /referral/create again (deterministic)")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": "user_001"},
            headers=HEADERS,
            timeout=10,
        )
        data = resp.json()
        check("Same user → same code", data.get("referral_code") == referral_code,
              f"got: {data.get('referral_code')}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 3: Redeem code as "new_user_001"
    print(f"\n[3] POST /referral/redeem {{code: '{referral_code}', new_user_id: 'new_user_001'}}")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/redeem",
            json={"referral_code": referral_code, "new_user_id": "new_user_001"},
            headers=HEADERS,
            timeout=10,
        )
        check("Redeem returns 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        check("redeemed is true", data.get("redeemed") is True, f"got: {data}")
        check("referrer_user_id is 'user_001'",
              data.get("referrer_user_id") == "user_001",
              f"got: {data.get('referrer_user_id')}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 4: Redeem same code as "new_user_002"
    print(f"\n[4] POST /referral/redeem {{code: '{referral_code}', new_user_id: 'new_user_002'}}")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/redeem",
            json={"referral_code": referral_code, "new_user_id": "new_user_002"},
            headers=HEADERS,
            timeout=10,
        )
        check("Second redeem returns 200", resp.status_code == 200, f"got {resp.status_code}")
        data = resp.json()
        check("Second redeemed is true", data.get("redeemed") is True, f"got: {data}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 5: Attempt redeem with unknown code → 404
    print("\n[5] POST /referral/redeem {code: 'ZZZZZZ'} → 404")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/redeem",
            json={"referral_code": "ZZZZZZ", "new_user_id": "new_user_003"},
            headers=HEADERS,
            timeout=10,
        )
        check("Unknown code returns 404", resp.status_code == 404, f"got {resp.status_code}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # Step 6: Missing API key → 401
    print("\n[6] POST /referral/create without API key → 401")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": "user_001"},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        check("Missing API key returns 401", resp.status_code == 401, f"got {resp.status_code}")
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
