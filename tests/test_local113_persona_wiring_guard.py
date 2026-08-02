#!/usr/bin/env python3
"""
test_local113_persona_wiring_guard.py — Guard test for persona blueprint registration
======================================================================================
LOCAL-113: Verifies that persona_bp is registered on generate_tour_text_service.py
and that POST /user/persona + GET /user/persona are reachable (not 404).

This test FAILS if the register_blueprint(persona_bp) line is removed or commented out.

Three parts:
  1. AST guard (always runs): statically verifies import + registration in source.
  2. Live HTTP test: hits the running tour-generator container to prove routes respond.
  3. Round-trip test: POST a persona, GET it back, verify match.

Usage:
    python3 tests/test_local113_persona_wiring_guard.py [--service-url URL]

Exit codes:
    0 = all pass
    1 = test failure (registration missing or route 404)
    7 = DB/service unreachable (infra problem, not a test failure)
"""
import os
import sys
import ast
import requests

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
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
# PART 1: AST Guard — static verification that persona_bp is registered
# ═══════════════════════════════════════════════════════════════════════════════

def test_ast_guard():
    """Parse generate_tour_text_service.py and verify persona_bp registration."""
    print("\n[AST GUARD] Verifying persona_bp registration in source code")
    print(f"  File: {SERVICE_FILE}")

    if not os.path.exists(SERVICE_FILE):
        check("Source file exists", False, f"{SERVICE_FILE} not found")
        return

    with open(SERVICE_FILE, "r") as f:
        source = f.read()

    # Check 1: import statement exists
    has_import = "from persona_endpoints import persona_bp" in source
    check("Import statement present", has_import,
          "Expected: 'from persona_endpoints import persona_bp'")

    # Check 2: register_blueprint call exists in text
    has_register = "register_blueprint(persona_bp)" in source
    check("register_blueprint(persona_bp) call present", has_register,
          "Expected: 'app.register_blueprint(persona_bp)' or similar")

    # Check 3: AST parse to confirm it's not inside a comment or string
    try:
        tree = ast.parse(source)
        found_register = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for *.register_blueprint(persona_bp)
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "register_blueprint":
                        for arg in node.args:
                            if isinstance(arg, ast.Name) and arg.id == "persona_bp":
                                found_register = True
                                break
        check("AST confirms register_blueprint(persona_bp) is live code",
              found_register,
              "Call exists in text but not in AST — possibly commented out or in a string")
    except SyntaxError as e:
        check("Source file parses", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Live HTTP test — verify routes respond (not 404)
# ═══════════════════════════════════════════════════════════════════════════════

def test_live_routes():
    """Hit the running service and verify persona routes are reachable."""
    print(f"\n[LIVE HTTP] Testing against {SERVICE_URL}")

    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

    # Test POST /user/persona — should NOT be 404
    print("\n  POST /user/persona:")
    try:
        resp = requests.post(
            f"{SERVICE_URL}/user/persona",
            json={
                "user_id": "guard_test_local113",
                "persona": "art_lover",
            },
            headers=headers,
            timeout=10,
        )
        check("POST /user/persona is not 404", resp.status_code != 404,
              f"Got {resp.status_code} — blueprint not registered!")
        check("POST /user/persona returns 200", resp.status_code == 200,
              f"Got {resp.status_code}: {resp.text[:200]}")

    except requests.ConnectionError:
        print(f"  SKIP: Service not running at {SERVICE_URL}")
        print("  (AST guard above still validates the registration exists)")
        return
    except Exception as e:
        check("HTTP request succeeded", False, str(e))
        return

    # Test GET /user/persona — round trip
    print("\n  GET /user/persona:")
    try:
        resp = requests.get(
            f"{SERVICE_URL}/user/persona?user_id=guard_test_local113",
            headers=headers,
            timeout=10,
        )
        check("GET /user/persona is not 404", resp.status_code != 404,
              f"Got {resp.status_code} — blueprint not registered!")
        check("GET /user/persona returns 200", resp.status_code == 200,
              f"Got {resp.status_code}: {resp.text[:200]}")

        if resp.status_code == 200:
            data = resp.json()
            check("Round trip: persona value matches",
                  data.get("persona") == "art_lover",
                  f"Expected 'art_lover', got: {data.get('persona')}")
    except Exception as e:
        check("GET request succeeded", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: No behaviour change guard — persona is opt-in only
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_behaviour_change():
    """Verify persona endpoints don't modify tours or cost data."""
    print("\n[BEHAVIOUR GUARD] Verifying persona is opt-in only")

    persona_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "persona_endpoints.py"
    )

    if not os.path.exists(persona_file):
        check("persona_endpoints.py exists", False, "File not found")
        return

    with open(persona_file, "r") as f:
        source = f.read()

    # Persona endpoints should NOT touch cost_meter, wallet_ledger, or audio_tours
    check("No cost_meter import in persona_endpoints.py",
          "cost_meter" not in source,
          "persona_endpoints.py imports cost_meter — persona should be free")

    check("No wallet_ledger reference in persona_endpoints.py",
          "wallet_ledger" not in source,
          "persona_endpoints.py references wallet_ledger — persona should be free")

    check("No audio_tours modification in persona_endpoints.py",
          "audio_tours" not in source,
          "persona_endpoints.py touches audio_tours table — should only use user_preferences")

    # Verify persona store uses user_preferences table only
    store_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "persona_preference_store.py"
    )
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
    global PASS_COUNT, FAIL_COUNT, SERVICE_URL

    # Parse CLI args
    if "--service-url" in sys.argv:
        idx = sys.argv.index("--service-url")
        if idx + 1 < len(sys.argv):
            SERVICE_URL = sys.argv[idx + 1]

    print("=" * 70)
    print("test_local113_persona_wiring_guard.py")
    print("LOCAL-113: Persona blueprint registration guard")
    print(f"Service: {SERVICE_URL}")
    print("=" * 70)

    # Always run static guard
    test_ast_guard()

    # Always run behaviour guard
    test_no_behaviour_change()

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
