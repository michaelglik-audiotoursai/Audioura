#!/usr/bin/env python3
"""
test_local110_sharing_wiring_guard.py — Guard test for sharing blueprint registration
=====================================================================================
LOCAL-110: Verifies that sharing_bp is registered on generate_tour_text_service.py
and that POST /tour/share + GET /tour/<id> are reachable (not 404).

This test FAILS if the register_blueprint(sharing_bp) line is removed or commented out.

Two modes:
  1. Live HTTP test (default): hits the running subscribed-generator container.
  2. AST guard (always runs): statically verifies the import + registration exist in
     the source file, so the test catches removal even without a running container.

Usage:
    python3 tests/test_local110_sharing_wiring_guard.py [--service-url URL]

Exit codes:
    0 = all pass
    1 = test failure (registration missing or route 404)
    7 = DB/service unreachable (infra problem)
"""
import os
import sys
import ast
import requests

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5100")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")

# The source file that must contain the registration
SERVICE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_tour_text_service.py"
)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        FAIL_COUNT += 1


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
    has_import = "from sharing_endpoints import sharing_bp" in source
    check("Import statement present", has_import,
          "Expected: 'from sharing_endpoints import sharing_bp'")

    # Check 2: register_blueprint call exists
    has_register = "register_blueprint(sharing_bp)" in source
    check("register_blueprint(sharing_bp) call present", has_register,
          "Expected: 'app.register_blueprint(sharing_bp)' or similar")

    # Check 3: AST parse to confirm it's not inside a comment or string
    try:
        tree = ast.parse(source)
        found_register = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for *.register_blueprint(sharing_bp)
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
# PART 2: Live HTTP test — verify routes respond (not 404)
# ═══════════════════════════════════════════════════════════════════════════════

def test_live_routes():
    """Hit the running service and verify sharing routes are reachable."""
    print(f"\n[LIVE HTTP] Testing against {SERVICE_URL}")

    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

    # Test POST /tour/share — should NOT be 404
    print("\n  POST /tour/share:")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/tour/share",
            json={
                "location": "Guard Test Nice",
                "tour_type": "walking",
                "total_stops": 3,
                "tour_text": "Guard test tour text for LOCAL-110.",
            },
            headers=headers,
            timeout=10,
        )
        check("POST /tour/share is not 404", resp.status_code != 404,
              f"Got {resp.status_code} — blueprint not registered!")
        check("POST /tour/share returns 200", resp.status_code == 200,
              f"Got {resp.status_code}: {resp.text[:200]}")

        if resp.status_code == 200:
            data = resp.json()
            share_id = data.get("share_id", "")
            check("Response has share_id", bool(share_id), f"Got: {data}")

            # Test GET /tour/<id>
            print(f"\n  GET /tour/{share_id}:")
            resp2 = requests.get(f"{SERVICE_URL}/tour/{share_id}", timeout=10)
            check("GET /tour/<id> is not 404 (Flask-level)",
                  resp2.status_code != 404 or "tour not found" in resp2.text,
                  f"Got {resp2.status_code} — route not registered!")
            check("GET /tour/<id> returns 200", resp2.status_code == 200,
                  f"Got {resp2.status_code}: {resp2.text[:200]}")

            if resp2.status_code == 200:
                tour_data = resp2.json()
                check("Retrieved tour_text matches",
                      tour_data.get("tour_text") == "Guard test tour text for LOCAL-110.",
                      f"Got: {tour_data.get('tour_text', '')[:100]}")

    except requests.ConnectionError:
        print(f"  SKIP: Service not running at {SERVICE_URL}")
        print("  (AST guard above still validates the registration exists)")
        return
    except Exception as e:
        check("HTTP request succeeded", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: No-charge guard — verify sharing does NOT hit cost_meter/wallet_ledger
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_charge_on_sharing():
    """Verify sharing_endpoints.py has no cost_meter or wallet_ledger references."""
    print("\n[NO-CHARGE GUARD] Verifying sharing is free (no metering)")

    sharing_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "sharing_endpoints.py"
    )

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
    tour_sharing_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tour_sharing.py"
    )
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
    global PASS_COUNT, FAIL_COUNT, SERVICE_URL

    # Parse CLI args early
    if "--service-url" in sys.argv:
        idx = sys.argv.index("--service-url")
        if idx + 1 < len(sys.argv):
            SERVICE_URL = sys.argv[idx + 1]

    print("=" * 70)
    print("test_local110_sharing_wiring_guard.py")
    print("LOCAL-110: Sharing blueprint registration guard")
    print(f"Service: {SERVICE_URL}")
    print("=" * 70)

    # Always run static guard
    test_ast_guard()

    # Always run no-charge guard
    test_no_charge_on_sharing()

    # Run live test if service is reachable
    test_live_routes()

    # Summary
    print("\n" + "=" * 70)
    print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
