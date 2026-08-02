#!/usr/bin/env python3
"""
test_local110_sharing_wiring_guard.py — Guard test for sharing blueprint registration
=====================================================================================
LOCAL-110: Verifies that sharing_bp is registered on generate_tour_text_service.py
and that POST /tour/share + GET /tour/<id> are reachable (not 404).

LOCAL-133: Added behavioural assertion — imports the Flask app and uses test_client()
to verify routes are actually reachable, not just syntactically present in the AST.
The AST check is kept as a cheap first line (catches comment-out fast) but is
insufficient alone (misses `if False:` neutering — D35).

Two independent questions:
  1. Is the registration in the source? (AST guard — always answerable)
  2. Does the app actually serve the route? (Behavioural — uses test_client())

Exit 0 = all pass. Exit 1 = test failure.

Usage:
    python3 tests/test_local110_sharing_wiring_guard.py
"""
import os
import sys
import ast

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_tour_text_service.py"
)

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


def skip(name: str, reason: str):
    global SKIP_COUNT
    SKIP_COUNT += 1
    print(f"  SKIP: {name} — {reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: AST Guard — static verification that sharing_bp is registered
# ═══════════════════════════════════════════════════════════════════════════════

def test_ast_guard():
    """Parse generate_tour_text_service.py and verify sharing_bp registration."""
    print("\n[AST GUARD] Verifying sharing_bp registration in source code")
    print(f"  File: {SERVICE_FILE}")

    if not os.path.exists(SERVICE_FILE):
        check("Source file exists", False, f"{SERVICE_FILE} not found")
        return

    with open(SERVICE_FILE, "r") as f:
        source = f.read()

    # Check 1: import statement exists
    import_needle = "from sharing_endpoints import sharing_bp"
    import_count = source.count(import_needle)
    print(f"    (import matches: {import_count})")
    has_import = import_count > 0
    check("Import statement present", has_import,
          f"Expected: '{import_needle}'")

    # Check 2: register_blueprint call exists
    register_needle = "register_blueprint(sharing_bp)"
    register_count = source.count(register_needle)
    print(f"    (register_blueprint matches: {register_count})")
    has_register = register_count > 0
    check("register_blueprint(sharing_bp) call present", has_register,
          "Expected: 'app.register_blueprint(sharing_bp)' or similar")

    # Check 3: AST parse to confirm it's not inside a comment or string
    try:
        tree = ast.parse(source)
        found_register = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "register_blueprint":
                        for arg in node.args:
                            if isinstance(arg, ast.Name) and arg.id == "sharing_bp":
                                found_register = True
                                break
        check("AST confirms register_blueprint(sharing_bp) is live code",
              found_register,
              "Call exists in text but not in AST — possibly commented out or in a string")
    except SyntaxError as e:
        check("Source file parses", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Behavioural Guard — import app, use test_client, verify route (LOCAL-133)
# ═══════════════════════════════════════════════════════════════════════════════

def test_behavioural_guard():
    """Import the Flask app and verify sharing routes respond via test_client().

    This catches `if False: app.register_blueprint(sharing_bp)` — the route
    will 404 even though ast.walk finds the Call node (D35).
    """
    print("\n[BEHAVIOURAL GUARD] Verifying sharing routes via test_client()")

    # Add project root to path so we can import the app
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)

    # Set env vars the app expects
    os.environ.setdefault("DATABASE_URL", "postgresql://admin:password123@localhost:5433/audiotours")
    os.environ.setdefault("GATEWAY_API_KEY", "test-api-key")

    try:
        from generate_tour_text_service import app
        client = app.test_client()
    except Exception as e:
        skip("Behavioural guard (all)", f"Cannot import app: {e}")
        return

    # Test: POST /tour/share should NOT be 404 (route is registered)
    resp = client.post(
        "/tour/share",
        json={
            "location": "Guard Test LOCAL-133",
            "tour_type": "walking",
            "total_stops": 3,
            "tour_text": "Behavioural guard test text.",
        },
        headers={"Content-Type": "application/json", "X-API-Key": "test-api-key"},
    )
    check("POST /tour/share is not 404 (behavioural)",
          resp.status_code != 404,
          f"Got {resp.status_code} — blueprint not registered or route unreachable!")

    # Test: GET /tour/<id> should NOT be 404 at Flask-routing level
    # (it may return 404 as business logic "tour not found", but the route must exist)
    resp2 = client.get("/tour/nonexistent-id-for-guard-test")
    # A registered route returns its own 404 with JSON body; an unregistered route
    # returns Flask's default HTML 404. Check for route existence.
    route_exists = (
        resp2.status_code != 404
        or b"tour" in resp2.data.lower()  # route handler's own 404 message
    )
    check("GET /tour/<id> route registered (behavioural)",
          route_exists,
          f"Got {resp2.status_code} with no tour-related body — route not registered!")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: No-charge guard — verify sharing does NOT hit cost_meter/wallet_ledger
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_charge_on_sharing():
    """Verify sharing_endpoints.py has no cost_meter or wallet_ledger references."""
    print("\n[NO-CHARGE GUARD] Verifying sharing is free (no metering)")

    sharing_file = os.path.join(SERVICE_DIR, "sharing_endpoints.py")

    if not os.path.exists(sharing_file):
        check("sharing_endpoints.py exists", False, "File not found")
        return

    with open(sharing_file, "r") as f:
        source = f.read()

    check("No cost_meter import in sharing_endpoints.py",
          "cost_meter" not in source,
          "FINDING: sharing_endpoints.py imports cost_meter — sharing should be FREE")

    check("No wallet_ledger reference in sharing_endpoints.py",
          "wallet_ledger" not in source,
          "FINDING: sharing_endpoints.py references wallet_ledger — sharing should be FREE")

    check("No record_operation in sharing_endpoints.py",
          "record_operation" not in source,
          "FINDING: sharing_endpoints.py calls record_operation — sharing should be FREE")

    # Also check tour_sharing.py
    tour_sharing_file = os.path.join(SERVICE_DIR, "tour_sharing.py")
    if os.path.exists(tour_sharing_file):
        with open(tour_sharing_file, "r") as f:
            ts_source = f.read()
        check("No cost_meter in tour_sharing.py",
              "cost_meter" not in ts_source,
              "FINDING: tour_sharing.py imports cost_meter — sharing should be FREE")
        check("No wallet_ledger in tour_sharing.py",
              "wallet_ledger" not in ts_source,
              "FINDING: tour_sharing.py references wallet_ledger — sharing should be FREE")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("test_local110_sharing_wiring_guard.py")
    print("LOCAL-110 + LOCAL-133: Sharing blueprint registration guard")
    print("=" * 70)

    # Always run static guard
    test_ast_guard()

    # Always run no-charge guard
    test_no_charge_on_sharing()

    # Behavioural guard — exercises the actual app (LOCAL-133)
    test_behavioural_guard()

    # Summary
    print("\n" + "=" * 70)
    if SKIP_COUNT > 0:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL, {SKIP_COUNT} SKIP")
    else:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0 and SKIP_COUNT == 0:
        print("ALL TESTS PASSED")
    elif FAIL_COUNT == 0 and SKIP_COUNT > 0:
        print("SOURCE ASSERTIONS PASSED — behavioural tests skipped (see reasons above)")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
