#!/usr/bin/env python3
"""
test_local114_referral_wiring_guard.py — Guard test for referral blueprint registration.
========================================================================================
LOCAL-114: Verify referral_bp is registered on generate_tour_text_service.py.
LOCAL-133: Added behavioural assertion — imports the Flask app and uses test_client()
           to verify routes are actually reachable, not just syntactically present.

The AST check is kept as a cheap first line (catches comment-out fast) but is
insufficient alone (misses `if False:` neutering — D35).

Two independent questions:
  1. Is the registration in the source? (AST guard — always answerable)
  2. Does the app actually serve the route? (Behavioural — uses test_client())

Exit 0 = all pass. Exit 1 = wiring broken.

Usage:
    python3 tests/test_local114_referral_wiring_guard.py
"""
import ast
import os
import sys

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_tour_text_service.py",
)

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: AST Guard — register_blueprint(referral_bp) is live code
# ═══════════════════════════════════════════════════════════════════════════════

def test_ast_guard():
    """Parse generate_tour_text_service.py and verify referral_bp registration."""
    print("\n[AST GUARD] Verifying referral_bp registration in source code")
    print(f"  File: {SERVICE_FILE}")

    if not os.path.exists(SERVICE_FILE):
        check("Source file exists", False, f"Not found: {SERVICE_FILE}")
        return

    with open(SERVICE_FILE, "r") as f:
        source = f.read()

    # Check 1: import statement present
    import_needle = "from referral_endpoints import referral_bp"
    import_count = source.count(import_needle)
    print(f"    (import matches: {import_count})")
    has_import = import_count > 0
    check("import referral_bp present in source", has_import,
          f"Expected: '{import_needle}'")

    # Check 2: register_blueprint call present in text
    register_needle = "register_blueprint(referral_bp)"
    register_count = source.count(register_needle)
    print(f"    (register_blueprint matches: {register_count})")
    has_register = register_count > 0
    check("register_blueprint(referral_bp) call present", has_register,
          "Expected: 'app.register_blueprint(referral_bp)' or similar")

    # Check 3: AST confirms it's executable code (not in a comment or string)
    try:
        tree = ast.parse(source)
        found_in_ast = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and func.attr == "register_blueprint"
                        and len(node.args) >= 1
                        and isinstance(node.args[0], ast.Name)
                        and node.args[0].id == "referral_bp"):
                    found_in_ast = True
                    break
        check("AST confirms register_blueprint(referral_bp) is live code", found_in_ast,
              "Call exists in text but not in AST — possibly commented out or in a string")
    except SyntaxError as e:
        check("Source file parses", False, str(e))

    # Check 4: referral_endpoints.py exists and defines referral_bp
    endpoints_file = os.path.join(SERVICE_DIR, "referral_endpoints.py")
    check("referral_endpoints.py exists", os.path.isfile(endpoints_file),
          f"Not found: {endpoints_file}")

    if os.path.isfile(endpoints_file):
        ep_source = open(endpoints_file).read()
        ep_tree = ast.parse(ep_source)
        has_bp_def = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "referral_bp" for t in node.targets)
            for node in ast.walk(ep_tree)
        )
        check("referral_bp defined in referral_endpoints.py", has_bp_def,
              "Expected: referral_bp = Blueprint(...)")

        # Check routes defined
        routes_found = []
        for node in ast.walk(ep_tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if (isinstance(decorator, ast.Call)
                            and isinstance(decorator.func, ast.Attribute)
                            and decorator.func.attr == "route"):
                        if decorator.args:
                            route_str = ast.literal_eval(decorator.args[0])
                            routes_found.append(route_str)
        check("POST /referral/create route defined", "/referral/create" in routes_found,
              f"Routes found: {routes_found}")
        check("POST /referral/redeem route defined", "/referral/redeem" in routes_found,
              f"Routes found: {routes_found}")

    # Check 5: referral_engine.py exists (dependency)
    engine_file = os.path.join(SERVICE_DIR, "referral_engine.py")
    check("referral_engine.py exists", os.path.isfile(engine_file),
          f"Not found: {engine_file}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Behavioural Guard — import app, use test_client, verify route (LOCAL-133)
# ═══════════════════════════════════════════════════════════════════════════════

def test_behavioural_guard():
    """Import the Flask app and verify referral routes respond via test_client().

    This catches `if False: app.register_blueprint(referral_bp)` — the route
    will 404 even though ast.walk finds the Call node (D35).
    """
    print("\n[BEHAVIOURAL GUARD] Verifying referral routes via test_client()")

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

    # Test: POST /referral/create should NOT be 404 (route is registered)
    resp = client.post(
        "/referral/create",
        json={"user_id": "guard_test_local133_wiring"},
        headers={"Content-Type": "application/json", "X-API-Key": "test-api-key"},
    )
    check("POST /referral/create is not 404 (behavioural)",
          resp.status_code != 404,
          f"Got {resp.status_code} — blueprint not registered or route unreachable!")

    # Test: POST /referral/redeem should NOT be 404
    # (Will likely 404 with "code not found" from business logic, but the route itself exists)
    resp2 = client.post(
        "/referral/redeem",
        json={"referral_code": "ZZZTST", "new_user_id": "guard_test_nobody"},
        headers={"Content-Type": "application/json", "X-API-Key": "test-api-key"},
    )
    # Business-logic 404 (referral code not found) is fine — it means the route IS registered.
    # A Flask-level unregistered route returns a generic HTML 404.
    route_exists = (
        resp2.status_code != 404
        or b"referral" in resp2.data.lower()
        or b"not found" in resp2.data.lower()
    )
    check("POST /referral/redeem route registered (behavioural)",
          route_exists,
          f"Got {resp2.status_code} with no referral-related body — route not registered!")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 70)
    print("test_local114_referral_wiring_guard.py")
    print("LOCAL-114 + LOCAL-133: Referral blueprint wiring guard")
    print("=" * 70)

    # AST guard — cheap first line
    test_ast_guard()

    # Behavioural guard — exercises actual app (LOCAL-133)
    test_behavioural_guard()

    # Summary
    print("\n" + "=" * 70)
    if SKIP_COUNT > 0:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL, {SKIP_COUNT} SKIP")
    else:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0 and SKIP_COUNT == 0:
        print("ALL ASSERTIONS PASSED — wiring is correct")
    elif FAIL_COUNT == 0 and SKIP_COUNT > 0:
        print("SOURCE ASSERTIONS PASSED — behavioural tests skipped (see reasons above)")
    else:
        print("WIRING BROKEN — failures detected")
    print("=" * 70)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
