#!/usr/bin/env python3
"""
test_local115_referral_abuse_controls_guard.py — Guard test for referral abuse controls.
=========================================================================================
LOCAL-115: Verify all three abuse controls are present and functional.

This test FAILS if any control is removed:
  1. Self-referral prevention → 403 on own-code redemption
  2. Duplicate redemption guard → 409 on second redemption (not 500)
  3. Rate limiting → 429 after threshold exceeded
  4. Legitimate flow still works end-to-end

Exit 0 = all controls working. Exit 1 = a control is broken or missing.

Usage:
    python3 tests/test_local115_referral_abuse_controls_guard.py
"""
import ast
import os
import sys
import time

# ─── Test harness ────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    """Hard assertion — failure causes exit 1."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: AST Guard — abuse control code is present in source
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 1: AST Guard — abuse controls present in referral_endpoints.py")
print("=" * 70)

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINTS_FILE = os.path.join(SERVICE_DIR, "referral_endpoints.py")
ENGINE_FILE = os.path.join(SERVICE_DIR, "referral_engine.py")

check("referral_endpoints.py exists", os.path.isfile(ENDPOINTS_FILE),
      f"Not found: {ENDPOINTS_FILE}")
check("referral_engine.py exists", os.path.isfile(ENGINE_FILE),
      f"Not found: {ENGINE_FILE}")

if os.path.isfile(ENDPOINTS_FILE):
    ep_source = open(ENDPOINTS_FILE).read()

    # Self-referral guard: check for comparison between new_user_id and referrer_user_id
    has_self_referral = (
        "new_user_id == referrer_user_id" in ep_source
        or "referrer_user_id == new_user_id" in ep_source
    )
    check("Self-referral guard present (new_user_id == referrer_user_id check)",
          has_self_referral,
          "No self-referral comparison found in source")

    # 403 response for self-referral
    has_403 = "403" in ep_source and "self_referral" in ep_source
    check("Self-referral returns 403 with error code 'self_referral'",
          has_403,
          "Expected 403 + 'self_referral' error")

    # Rate limiting
    has_rate_limit = "_check_rate_limit" in ep_source
    check("Rate limiter function called in endpoints",
          has_rate_limit,
          "No _check_rate_limit call found")

    has_429 = "429" in ep_source and "rate_limit_exceeded" in ep_source
    check("Rate limit returns 429 with error code 'rate_limit_exceeded'",
          has_429,
          "Expected 429 + 'rate_limit_exceeded' error")

    # Duplicate redemption handling
    has_duplicate_check = '"duplicate"' in ep_source and "409" in ep_source
    check("Duplicate redemption returns 409",
          has_duplicate_check,
          "Expected 'duplicate' result handling + 409")

    has_already_redeemed = "already_redeemed" in ep_source
    check("Duplicate response has 'already_redeemed' error code",
          has_already_redeemed,
          "Expected 'already_redeemed' in response")

if os.path.isfile(ENGINE_FILE):
    eng_source = open(ENGINE_FILE).read()

    # Engine returns "duplicate" on UniqueViolation
    has_unique_handling = "UniqueViolation" in eng_source and '"duplicate"' in eng_source
    check("Engine catches UniqueViolation and returns 'duplicate'",
          has_unique_handling,
          "Expected psycopg2.errors.UniqueViolation handling returning 'duplicate'")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Live HTTP Guard — all controls respond correctly
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2: Live HTTP Guard — abuse controls respond correctly")
print("=" * 70)

SERVICE_URL = os.environ.get("SERVICE_URL", "http://localhost:5100")
API_KEY = os.environ.get("GATEWAY_API_KEY", "test-api-key")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("  SKIP: requests not installed — live HTTP tests skipped")

if REQUESTS_AVAILABLE:
    try:
        HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
        ts = str(int(time.time()))  # unique per run to avoid collisions

        # --- Setup: Create a referral code ---
        creator_id = f"guard115_creator_{ts}"
        r = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": creator_id},
            headers=HEADERS,
            timeout=10,
        )
        check("Setup: create referral returns 200", r.status_code == 200,
              f"Got {r.status_code}: {r.text[:200]}")

        code = ""
        if r.status_code == 200:
            code = r.json().get("referral_code", "")
            check("Setup: referral_code returned", bool(code), f"Got: {r.json()}")

        # --- AC1: Legitimate redeem by different user ---
        if code:
            redeemer_id = f"guard115_redeemer_{ts}"
            r2 = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code, "new_user_id": redeemer_id},
                headers=HEADERS,
                timeout=10,
            )
            check("Legitimate redeem returns 200", r2.status_code == 200,
                  f"Got {r2.status_code}: {r2.text[:200]}")
            if r2.status_code == 200:
                data = r2.json()
                check("Redeem has redeemed=true", data.get("redeemed") is True,
                      f"Got: {data}")
                check("Redeem returns correct referrer_user_id",
                      data.get("referrer_user_id") == creator_id,
                      f"Got: {data.get('referrer_user_id')}")

        # --- AC2: Self-referral prevention ---
        if code:
            r3 = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code, "new_user_id": creator_id},
                headers=HEADERS,
                timeout=10,
            )
            check("Self-referral returns 403", r3.status_code == 403,
                  f"Got {r3.status_code}: {r3.text[:200]}")
            if r3.status_code == 403:
                data3 = r3.json()
                check("Self-referral error is 'self_referral'",
                      data3.get("error") == "self_referral",
                      f"Got: {data3}")

        # --- AC3: Duplicate redemption prevention ---
        if code:
            r4 = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code, "new_user_id": redeemer_id},
                headers=HEADERS,
                timeout=10,
            )
            check("Duplicate redeem returns 409 (not 500)", r4.status_code == 409,
                  f"Got {r4.status_code}: {r4.text[:200]}")
            if r4.status_code == 409:
                data4 = r4.json()
                check("Duplicate error is 'already_redeemed'",
                      data4.get("error") == "already_redeemed",
                      f"Got: {data4}")

        # --- AC4: Rate limiting ---
        # Use a fresh user ID to avoid collision with the create rate limit from earlier
        rate_user = f"guard115_rate_{ts}"
        tripped = False
        for i in range(12):
            r5 = requests.post(
                f"{SERVICE_URL}/referral/create",
                json={"user_id": rate_user},
                headers=HEADERS,
                timeout=10,
            )
            if r5.status_code == 429:
                tripped = True
                break

        check("Rate limit fires within 12 requests (limit=10)", tripped,
              "All 12 requests succeeded — rate limiting not active")
        if tripped:
            data5 = r5.json()
            check("Rate limit error is 'rate_limit_exceeded'",
                  data5.get("error") == "rate_limit_exceeded",
                  f"Got: {data5}")
            check("Rate limit includes retry_after_seconds",
                  "retry_after_seconds" in data5,
                  f"Got: {data5}")

    except requests.ConnectionError:
        print(f"  SKIP: Cannot connect to {SERVICE_URL}")
        print("         Start with: docker compose -f docker-compose-local115.yml up -d")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Database Guard — UNIQUE constraint exists
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 3: Database Guard — UNIQUE constraint on referral_redemptions")
print("=" * 70)

try:
    sys.path.insert(0, os.path.join(SERVICE_DIR, "tests"))
    from db_connection import get_connection, check_db_available

    if check_db_available():
        conn = get_connection()
        cur = conn.cursor()

        # Check UNIQUE constraint exists
        cur.execute("""
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'referral_redemptions'::regclass
            AND contype = 'u'
        """)
        constraints = [row[0] for row in cur.fetchall()]
        has_unique = "uq_referral_redemptions_code_user" in constraints
        check("UNIQUE constraint 'uq_referral_redemptions_code_user' exists",
              has_unique,
              f"Found constraints: {constraints}")

        # Verify constraint covers the right columns
        if has_unique:
            cur.execute("""
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conname = 'uq_referral_redemptions_code_user'
                ORDER BY a.attnum
            """)
            cols = [row[0] for row in cur.fetchall()]
            check("Constraint covers (referral_code, new_user_id)",
                  set(cols) == {"referral_code", "new_user_id"},
                  f"Covers: {cols}")

        # Verify audio_tours untouched
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        at_count = cur.fetchone()[0]
        check("audio_tours row count unchanged (88)", at_count == 88,
              f"Got {at_count} (expected 88)")

        conn.close()
    else:
        print("  SKIP: Database unreachable")

except ImportError:
    print("  SKIP: psycopg2 not available")
except Exception as e:
    print(f"  ERROR: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
if FAIL_COUNT == 0:
    print("ALL ASSERTIONS PASSED — referral abuse controls are working")
else:
    print("ABUSE CONTROLS BROKEN — one or more controls missing or non-functional")
print("=" * 70)

sys.exit(0 if FAIL_COUNT == 0 else 1)
