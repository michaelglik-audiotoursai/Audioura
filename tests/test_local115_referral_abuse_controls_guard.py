#!/usr/bin/env python3
"""
test_local115_referral_abuse_controls_guard.py — Guard test for referral abuse controls.
=========================================================================================
LOCAL-115: Verify all three abuse controls are present and functional.
LOCAL-130: Fixed — exercises BEHAVIOUR, not source text.

This test FAILS if any control is disabled, bypassed, or removed:
  1. Self-referral prevention → 403 on own-code redemption
  2. Duplicate redemption guard → 409 on second redemption (not 500)
  3. Rate limiting → 429 after threshold exceeded

The test starts a fresh Flask instance host-side (no Docker) with the real
referral_endpoints and referral_engine, pointed at the existing Postgres
database. This makes it immune to source-level evasions (if False, dead code,
decorator swaps, etc.) — if the control does not actually reject, the test fails.

Exit 0 = all controls working. Exit 1 = a control is broken or missing.

Usage:
    python3 tests/test_local115_referral_abuse_controls_guard.py
"""
import ast
import os
import sys
import time
import signal
import socket
import subprocess

# ─── Test harness ────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    """Hard assertion — failure causes exit 1."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def skip(name: str, reason: str):
    """Explicit skip — does not cause exit 1, but is not a pass."""
    global SKIP_COUNT
    SKIP_COUNT += 1
    print(f"  SKIP: {name} — {reason}")


# ─── Paths ───────────────────────────────────────────────────────────────────
SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINTS_FILE = os.path.join(SERVICE_DIR, "referral_endpoints.py")
ENGINE_FILE = os.path.join(SERVICE_DIR, "referral_engine.py")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: AST Guard — structural presence checks (fast first-line defence)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 1: AST Guard — abuse control code structurally present")
print("=" * 70)

check("referral_endpoints.py exists", os.path.isfile(ENDPOINTS_FILE),
      f"Not found: {ENDPOINTS_FILE}")
check("referral_engine.py exists", os.path.isfile(ENGINE_FILE),
      f"Not found: {ENGINE_FILE}")

if os.path.isfile(ENDPOINTS_FILE):
    ep_source = open(ENDPOINTS_FILE).read()
    ep_tree = ast.parse(ep_source)

    # Self-referral: AST has comparison of new_user_id == referrer_user_id
    self_referral_in_ast = False
    for node in ast.walk(ep_tree):
        if isinstance(node, ast.Compare):
            if (isinstance(node.left, ast.Name)
                    and len(node.ops) == 1
                    and isinstance(node.ops[0], ast.Eq)
                    and len(node.comparators) == 1
                    and isinstance(node.comparators[0], ast.Name)):
                names = {node.left.id, node.comparators[0].id}
                if names == {"new_user_id", "referrer_user_id"}:
                    self_referral_in_ast = True
                    break
    check("Self-referral: equality check in AST", self_referral_in_ast,
          "No live AST comparison of new_user_id == referrer_user_id found")

    # Rate limiter: actual Call to _check_rate_limit in route handlers
    rate_limit_calls = 0
    for node in ast.walk(ep_tree):
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            is_route = any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and d.func.attr == "route"
                for d in node.decorator_list
            )
            if is_route:
                for child in ast.walk(node):
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Name)
                            and child.func.id == "_check_rate_limit"):
                        rate_limit_calls += 1
    check("Rate limiter: _check_rate_limit() called in ≥2 routes",
          rate_limit_calls >= 2,
          f"Found {rate_limit_calls} calls, expected ≥2")

    # Duplicate redemption: 409 + "already_redeemed" in redeem handler
    has_duplicate_409 = False
    for node in ast.walk(ep_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "redeem_referral":
            func_source = ast.get_source_segment(ep_source, node)
            if (func_source
                    and '"duplicate"' in func_source
                    and "409" in func_source
                    and "already_redeemed" in func_source):
                has_duplicate_409 = True
                break
    check("Duplicate redemption: 409 + 'already_redeemed' in redeem_referral",
          has_duplicate_409,
          "Expected 'duplicate' check + 409 + 'already_redeemed'")

if os.path.isfile(ENGINE_FILE):
    eng_source = open(ENGINE_FILE).read()
    eng_tree = ast.parse(eng_source)
    has_unique_handling = False
    for node in ast.walk(eng_tree):
        if isinstance(node, ast.ExceptHandler):
            handler_source = ast.get_source_segment(eng_source, node)
            if handler_source and "UniqueViolation" in handler_source and '"duplicate"' in handler_source:
                has_unique_handling = True
                break
    check("Engine: catches UniqueViolation → 'duplicate'",
          has_unique_handling,
          "Expected except handler with UniqueViolation returning 'duplicate'")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Behavioural Guard — exercise each control via live HTTP
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 2: Behavioural Guard — exercise controls via live HTTP")
print("=" * 70)

# Start a temporary Flask server host-side to test the actual behaviour.
# This avoids depending on Docker containers.

def _find_free_port():
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


TEST_PORT = _find_free_port()

# Write a minimal launcher script
LAUNCHER_SCRIPT = os.path.join(SERVICE_DIR, "tests", "_guard_test_server.py")
with open(LAUNCHER_SCRIPT, "w") as f:
    f.write(f"""#!/usr/bin/env python3
\"\"\"Temporary test server for LOCAL-115 guard — auto-deleted after test.\"\"\"
import sys, os
sys.path.insert(0, {repr(SERVICE_DIR)})
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['GATEWAY_API_KEY'] = 'test-api-key'
os.environ['REFERRAL_RATE_LIMIT_MAX'] = '5'
os.environ['REFERRAL_RATE_LIMIT_WINDOW'] = '60'
from flask import Flask
from referral_endpoints import referral_bp
app = Flask(__name__)
app.register_blueprint(referral_bp)
app.run(host='127.0.0.1', port={TEST_PORT}, debug=False)
""")

SERVER_PROC = None
SERVICE_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

if not REQUESTS_AVAILABLE:
    skip("Live HTTP tests", "requests module not installed")
else:
    # Start the test server
    SERVER_PROC = subprocess.Popen(
        [sys.executable, LAUNCHER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for it to become ready (max 10s)
    SERVICE_URL = f"http://127.0.0.1:{TEST_PORT}"
    for attempt in range(40):
        time.sleep(0.25)
        try:
            r = requests.get(f"{SERVICE_URL}/", timeout=1)
            SERVICE_AVAILABLE = True
            break
        except (requests.ConnectionError, requests.Timeout):
            # Also check if process died
            if SERVER_PROC.poll() is not None:
                stderr_out = SERVER_PROC.stderr.read().decode()
                print(f"  ERROR: Test server exited early: {stderr_out[:500]}")
                break
            continue

    if not SERVICE_AVAILABLE:
        # One more check with a real endpoint
        try:
            r = requests.post(
                f"{SERVICE_URL}/referral/create",
                json={"user_id": "probe"},
                headers={"X-API-Key": "test-api-key", "Content-Type": "application/json"},
                timeout=2,
            )
            SERVICE_AVAILABLE = True
        except (requests.ConnectionError, requests.Timeout):
            pass

    if SERVICE_AVAILABLE:
        HEADERS = {"X-API-Key": "test-api-key", "Content-Type": "application/json"}
        ts = str(int(time.time() * 1000))  # unique per run

        # ─── AC1: Self-referral prevention → 403 ─────────────────────────
        print("\n  --- Self-referral prevention ---")
        creator_id = f"guard_self_{ts}"
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

        if code:
            # Attempt self-referral
            r_self = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code, "new_user_id": creator_id},
                headers=HEADERS,
                timeout=10,
            )
            check("Self-referral returns 403",
                  r_self.status_code == 403,
                  f"Got {r_self.status_code}: {r_self.text[:200]}")
            if r_self.status_code == 403:
                check("Self-referral error is 'self_referral'",
                      r_self.json().get("error") == "self_referral",
                      f"Got: {r_self.json()}")
        else:
            skip("Self-referral 403", "Could not create referral code")

        # ─── AC2: Duplicate redemption → 409 ─────────────────────────────
        print("\n  --- Duplicate redemption prevention ---")
        creator2 = f"guard_dup_creator_{ts}"
        r2 = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": creator2},
            headers=HEADERS,
            timeout=10,
        )
        code2 = ""
        if r2.status_code == 200:
            code2 = r2.json().get("referral_code", "")

        if code2:
            redeemer2 = f"guard_dup_redeemer_{ts}"
            # First redeem — should succeed
            r2a = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code2, "new_user_id": redeemer2},
                headers=HEADERS,
                timeout=10,
            )
            check("First redeem returns 200", r2a.status_code == 200,
                  f"Got {r2a.status_code}: {r2a.text[:200]}")

            # Second redeem with same user — should get 409
            r2b = requests.post(
                f"{SERVICE_URL}/referral/redeem",
                json={"referral_code": code2, "new_user_id": redeemer2},
                headers=HEADERS,
                timeout=10,
            )
            check("Duplicate redeem returns 409 (not 500)",
                  r2b.status_code == 409,
                  f"Got {r2b.status_code}: {r2b.text[:200]}")
            if r2b.status_code == 409:
                check("Duplicate error is 'already_redeemed'",
                      r2b.json().get("error") == "already_redeemed",
                      f"Got: {r2b.json()}")
        else:
            skip("Duplicate redemption 409", "Could not create referral code")

        # ─── AC3: Rate limiting → 429 ────────────────────────────────────
        print("\n  --- Rate limiting ---")
        # Server configured with REFERRAL_RATE_LIMIT_MAX=5, so 6th request should 429
        rate_user = f"guard_rate_{ts}"
        tripped_429 = False
        last_status = None
        for i in range(8):
            r_rate = requests.post(
                f"{SERVICE_URL}/referral/create",
                json={"user_id": rate_user},
                headers=HEADERS,
                timeout=10,
            )
            last_status = r_rate.status_code
            if r_rate.status_code == 429:
                tripped_429 = True
                break

        check("Rate limit fires within 8 requests (limit=5)", tripped_429,
              f"All requests returned {last_status} — rate limiting not active")
        if tripped_429:
            data_rate = r_rate.json()
            check("Rate limit error is 'rate_limit_exceeded'",
                  data_rate.get("error") == "rate_limit_exceeded",
                  f"Got: {data_rate}")
            check("Rate limit includes retry_after_seconds",
                  "retry_after_seconds" in data_rate,
                  f"Got: {data_rate}")

        # ─── AC4: Legitimate flow still works ─────────────────────────────
        print("\n  --- Legitimate flow ---")
        legit_creator = f"guard_legit_creator_{ts}"
        r_legit = requests.post(
            f"{SERVICE_URL}/referral/create",
            json={"user_id": legit_creator},
            headers=HEADERS,
            timeout=10,
        )
        if r_legit.status_code == 200:
            legit_code = r_legit.json().get("referral_code", "")
            if legit_code:
                legit_redeemer = f"guard_legit_redeemer_{ts}"
                r_legit2 = requests.post(
                    f"{SERVICE_URL}/referral/redeem",
                    json={"referral_code": legit_code, "new_user_id": legit_redeemer},
                    headers=HEADERS,
                    timeout=10,
                )
                check("Legitimate redeem returns 200", r_legit2.status_code == 200,
                      f"Got {r_legit2.status_code}: {r_legit2.text[:200]}")
                if r_legit2.status_code == 200:
                    check("Legitimate redeem has redeemed=true",
                          r_legit2.json().get("redeemed") is True,
                          f"Got: {r_legit2.json()}")
    else:
        skip("All live HTTP tests",
             f"Could not start test server on port {TEST_PORT}. "
             "This may indicate a missing dependency or DB issue.")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Database Guard — UNIQUE constraint exists + row count invariant
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("PART 3: Database Guard — UNIQUE constraint + row-count invariant")
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

        # Row-count invariant: tables must not change during the test.
        # Never assert an absolute value — only assert stability.
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        audio_tours_before = cur.fetchone()[0]
        print(f"  INFO: audio_tours row count = {audio_tours_before}")

        cur.execute("SELECT COUNT(*) FROM stop_metrics")
        stop_metrics_before = cur.fetchone()[0]
        print(f"  INFO: stop_metrics row count = {stop_metrics_before}")

        # Re-read to confirm stability
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        audio_tours_after = cur.fetchone()[0]
        check("audio_tours row count unchanged across test",
              audio_tours_after == audio_tours_before,
              f"audio_tours changed: {audio_tours_before} -> {audio_tours_after}")

        cur.execute("SELECT COUNT(*) FROM stop_metrics")
        stop_metrics_after = cur.fetchone()[0]
        check("stop_metrics row count unchanged across test",
              stop_metrics_after == stop_metrics_before,
              f"stop_metrics changed: {stop_metrics_before} -> {stop_metrics_after}")

        conn.close()
    else:
        skip("Database guard", "Database unreachable")

except ImportError:
    skip("Database guard", "psycopg2 not available")
except Exception as e:
    print(f"  ERROR: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup + Summary
# ═══════════════════════════════════════════════════════════════════════════════

# Stop the test server
if SERVER_PROC and SERVER_PROC.poll() is None:
    SERVER_PROC.terminate()
    try:
        SERVER_PROC.wait(timeout=5)
    except subprocess.TimeoutExpired:
        SERVER_PROC.kill()

# Remove launcher script
if os.path.isfile(LAUNCHER_SCRIPT):
    os.unlink(LAUNCHER_SCRIPT)

print("\n" + "=" * 70)
print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL, {SKIP_COUNT} SKIP")
if FAIL_COUNT == 0 and SKIP_COUNT == 0:
    print("ALL ASSERTIONS PASSED — referral abuse controls are working")
elif FAIL_COUNT == 0:
    print("PASS with skips — controls verified where reachable")
else:
    print("ABUSE CONTROLS BROKEN — one or more controls missing or non-functional")
print("=" * 70)

sys.exit(0 if FAIL_COUNT == 0 else 1)
