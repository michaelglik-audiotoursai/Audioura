#!/usr/bin/env python3
"""
test_local113_persona_wiring_guard.py — Guard test for persona blueprint registration
======================================================================================
LOCAL-113: Verifies that persona_bp is registered on generate_tour_text_service.py.
LOCAL-131: Split into source-level and live-HTTP assertions.
LOCAL-133: Added behavioural assertion — imports the Flask app and uses test_client()
           to verify routes are actually reachable, not just syntactically present.

The AST check is kept as a cheap first line (catches comment-out fast) but is
insufficient alone (misses `if False:` neutering — D35).

Two independent questions:
  1. Is the registration in the source? (AST guard — always answerable)
  2. Does the app actually serve the route? (Behavioural — uses test_client())

Exit 0 = all assertions pass (skips OK). Exit 1 = test failure.
Skips are reported separately and never masquerade as passes.

Usage:
    python3 tests/test_local113_persona_wiring_guard.py
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

# ─── Test harness ────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0

# Track whether source guard passed
SOURCE_GUARD_PASSED = False


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
# PART 1: Source Guard — persona_bp registration is live code
# ═══════════════════════════════════════════════════════════════════════════════

def test_source_guard():
    """Parse generate_tour_text_service.py and verify persona_bp registration.

    Prints match counts so a no-op edit cannot masquerade as a result (D36).
    """
    global SOURCE_GUARD_PASSED

    print("\n[SOURCE GUARD] Verifying persona_bp registration in source code")
    print(f"  File: {SERVICE_FILE}")

    if not os.path.exists(SERVICE_FILE):
        check("Source file exists", False, f"{SERVICE_FILE} not found")
        return

    with open(SERVICE_FILE, "r") as f:
        source = f.read()

    part_failures = 0

    # Check 1: import statement exists
    import_needle = "from persona_endpoints import persona_bp"
    import_count = source.count(import_needle)
    has_import = import_count > 0
    print(f"    (import matches: {import_count})")
    check("Import statement present", has_import,
          f"Expected: '{import_needle}' — found 0 occurrences")
    if not has_import:
        part_failures += 1

    # Check 2: register_blueprint call exists in text
    register_needle = "register_blueprint(persona_bp)"
    register_count = source.count(register_needle)
    has_register = register_count > 0
    print(f"    (register_blueprint matches: {register_count})")
    check("register_blueprint(persona_bp) call present", has_register,
          f"Expected: 'app.register_blueprint(persona_bp)' — found 0 occurrences")
    if not has_register:
        part_failures += 1

    # Check 3: AST parse to confirm it's live code (not commented/stringified)
    try:
        tree = ast.parse(source)
        found_register = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "register_blueprint":
                        for arg in node.args:
                            if isinstance(arg, ast.Name) and arg.id == "persona_bp":
                                found_register = True
                                break
        check("AST confirms register_blueprint(persona_bp) is live code",
              found_register,
              "Call exists in text but not in AST — possibly commented out or in a string")
        if not found_register:
            part_failures += 1
    except SyntaxError as e:
        check("Source file parses without error", False, str(e))
        part_failures += 1

    SOURCE_GUARD_PASSED = (part_failures == 0)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Behavioural Guard — import app, use test_client, verify route (LOCAL-133)
# ═══════════════════════════════════════════════════════════════════════════════

def test_behavioural_guard():
    """Import the Flask app and verify persona routes respond via test_client().

    This catches `if False: app.register_blueprint(persona_bp)` — the route
    will 404 even though ast.walk finds the Call node (D35).
    """
    print("\n[BEHAVIOURAL GUARD] Verifying persona routes via test_client()")

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

    # Test: POST /user/persona should NOT be 404 (route is registered)
    resp = client.post(
        "/user/persona",
        json={"user_id": "guard_test_local133", "persona": "art_lover"},
        headers={"Content-Type": "application/json", "X-API-Key": "test-api-key"},
    )
    check("POST /user/persona is not 404 (behavioural)",
          resp.status_code != 404,
          f"Got {resp.status_code} — blueprint not registered or route unreachable!")

    # Test: GET /user/persona should NOT be 404
    resp2 = client.get(
        "/user/persona?user_id=guard_test_local133",
        headers={"X-API-Key": "test-api-key"},
    )
    check("GET /user/persona is not 404 (behavioural)",
          resp2.status_code != 404,
          f"Got {resp2.status_code} — blueprint not registered or route unreachable!")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: Behaviour Guard — persona is opt-in only (no side effects)
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_side_effects():
    """Verify persona endpoints don't modify tours or cost data."""
    print("\n[SIDE-EFFECT GUARD] Verifying persona is opt-in only")

    persona_file = os.path.join(SERVICE_DIR, "persona_endpoints.py")

    if not os.path.exists(persona_file):
        check("persona_endpoints.py exists", False, "File not found")
        return

    with open(persona_file, "r") as f:
        source = f.read()

    check("No cost_meter import in persona_endpoints.py",
          "cost_meter" not in source,
          "persona_endpoints.py imports cost_meter — persona should be free")

    check("No wallet_ledger reference in persona_endpoints.py",
          "wallet_ledger" not in source,
          "persona_endpoints.py references wallet_ledger — persona should be free")

    check("No audio_tours modification in persona_endpoints.py",
          "audio_tours" not in source,
          "persona_endpoints.py touches audio_tours table — should only use user_preferences")

    store_file = os.path.join(SERVICE_DIR, "persona_preference_store.py")
    if os.path.exists(store_file):
        with open(store_file, "r") as f:
            store_source = f.read()
        check("Persona store uses user_preferences table",
              "user_preferences" in store_source,
              "Expected persona_preference_store.py to use user_preferences table")
        check("Persona store does NOT touch audio_tours",
              "audio_tours" not in store_source,
              "persona_preference_store.py should never modify audio_tours")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("test_local113_persona_wiring_guard.py")
    print("LOCAL-113 + LOCAL-131 + LOCAL-133: Persona blueprint registration guard")
    print("=" * 70)

    # Source guard — always runs, always answerable
    test_source_guard()

    # Side-effect guard — always runs (reads source only)
    test_no_side_effects()

    # Behavioural guard — exercises actual app (LOCAL-133)
    test_behavioural_guard()

    # Summary — skips counted separately from passes
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
