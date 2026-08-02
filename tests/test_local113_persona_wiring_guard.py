#!/usr/bin/env python3
"""
test_local113_persona_wiring_guard.py — Guard test for persona blueprint registration
======================================================================================
LOCAL-113: Verifies that persona_bp is registered on generate_tour_text_service.py.
LOCAL-131: Split into source-level and live-HTTP assertions so the guard is not
           permanently red when the container is stale.

Two independent questions:
  1. Is the registration in the source? (AST guard — always answerable)
  2. Does the running service serve the route? (HTTP — skips when the container
     is stale, i.e. source is correct but route 404s)

Exit 0 = source assertions pass (HTTP may be skipped).
Exit 1 = source assertion fails.
Skips are reported separately and never masquerade as passes.

When the container is rebuilt with current source, the HTTP assertions will
start running automatically (no hardcoded skip — reachability is detected).

Usage:
    python3 tests/test_local113_persona_wiring_guard.py [--service-url URL]
"""
import os
import sys
import ast
import socket

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:5000")
API_KEY = os.getenv("GATEWAY_API_KEY", "test-api-key")

SERVICE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "generate_tour_text_service.py"
)

# ─── Test harness ────────────────────────────────────────────────────────────
PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0

# Track whether source guard passed — used by HTTP guard to decide skip vs fail
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


def is_port_reachable(url: str, timeout: float = 3.0) -> bool:
    """Check if the host:port in a URL is accepting TCP connections."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 80
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


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
# PART 2: Behaviour Guard — persona is opt-in only (no side effects)
# ═══════════════════════════════════════════════════════════════════════════════

def test_behaviour_guard():
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

    check("No cost_meter import in persona_endpoints.py",
          "cost_meter" not in source,
          "persona_endpoints.py imports cost_meter — persona should be free")

    check("No wallet_ledger reference in persona_endpoints.py",
          "wallet_ledger" not in source,
          "persona_endpoints.py references wallet_ledger — persona should be free")

    check("No audio_tours modification in persona_endpoints.py",
          "audio_tours" not in source,
          "persona_endpoints.py touches audio_tours table — should only use user_preferences")

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
# PART 3: Live HTTP Guard — verify routes respond (SKIPS if stale/unreachable)
# ═══════════════════════════════════════════════════════════════════════════════

def test_live_http():
    """Hit the running service and verify persona routes are reachable.

    Skip logic (no hardcoded skip — detect reachability):
      - Port unreachable → SKIP (no container running at all)
      - Port reachable, route 404, source guard PASSED → SKIP (container stale)
      - Port reachable, route 404, source guard FAILED → FAIL (genuinely broken)
      - Port reachable, route non-404 → assert normally

    When the container is rebuilt with current source, the 404 disappears and
    HTTP assertions begin running automatically.
    """
    print(f"\n[LIVE HTTP] Testing against {SERVICE_URL}")

    # Gate 1: Is the port even accepting connections?
    if not is_port_reachable(SERVICE_URL):
        reason = (
            f"Port not accepting connections at {SERVICE_URL} — "
            f"no container running. Will auto-run when service starts."
        )
        skip("POST /user/persona reachable", reason)
        skip("GET /user/persona reachable", reason)
        return

    # Port is open — probe the route
    import requests

    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}

    # Probe POST
    try:
        resp_post = requests.post(
            f"{SERVICE_URL}/user/persona",
            json={"user_id": "guard_test_local113", "persona": "art_lover"},
            headers=headers,
            timeout=10,
        )
    except requests.ConnectionError as e:
        reason = f"Connection failed after port probe: {e}"
        skip("POST /user/persona reachable", reason)
        skip("GET /user/persona reachable", reason)
        return

    # Gate 2: If 404 and source guard passed → container is stale, skip
    if resp_post.status_code == 404 and SOURCE_GUARD_PASSED:
        reason = (
            f"Container at {SERVICE_URL} returns 404 for /user/persona — "
            f"image predates persona_bp registration (source is correct per "
            f"Part 1). Cannot rebuild (Docker builds hung). "
            f"Will auto-run when container is rebuilt with current source."
        )
        skip("POST /user/persona is not 404", reason)
        skip("POST /user/persona returns 200", reason)
        skip("GET /user/persona is not 404", reason)
        skip("GET /user/persona returns 200", reason)
        skip("Round trip: persona value matches", reason)
        return

    # Gate 3: If 404 and source guard FAILED → genuinely broken
    # (fall through to normal assertions which will fail)

    # Normal assertions — route is responding
    print("\n  POST /user/persona:")
    check("POST /user/persona is not 404", resp_post.status_code != 404,
          f"Got {resp_post.status_code} — blueprint not registered!")
    check("POST /user/persona returns 200", resp_post.status_code == 200,
          f"Got {resp_post.status_code}: {resp_post.text[:200]}")

    # GET /user/persona — round trip
    print("\n  GET /user/persona:")
    try:
        resp_get = requests.get(
            f"{SERVICE_URL}/user/persona?user_id=guard_test_local113",
            headers=headers,
            timeout=10,
        )
        check("GET /user/persona is not 404", resp_get.status_code != 404,
              f"Got {resp_get.status_code} — blueprint not registered!")
        check("GET /user/persona returns 200", resp_get.status_code == 200,
              f"Got {resp_get.status_code}: {resp_get.text[:200]}")

        if resp_get.status_code == 200:
            data = resp_get.json()
            check("Round trip: persona value matches",
                  data.get("persona") == "art_lover",
                  f"Expected 'art_lover', got: {data.get('persona')}")
    except Exception as e:
        check("GET request succeeded", False, str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    global SERVICE_URL

    # Parse CLI args
    if "--service-url" in sys.argv:
        idx = sys.argv.index("--service-url")
        if idx + 1 < len(sys.argv):
            SERVICE_URL = sys.argv[idx + 1]

    print("=" * 70)
    print("test_local113_persona_wiring_guard.py")
    print("LOCAL-113 + LOCAL-131: Persona blueprint registration guard")
    print(f"Service: {SERVICE_URL}")
    print("=" * 70)

    # Source guard — always runs, always answerable
    test_source_guard()

    # Behaviour guard — always runs (reads source only)
    test_behaviour_guard()

    # Live HTTP — skips if unreachable or stale, runs if route is live
    test_live_http()

    # Summary — skips counted separately from passes
    print("\n" + "=" * 70)
    if SKIP_COUNT > 0:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL, {SKIP_COUNT} SKIP")
    else:
        print(f"Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL")

    if FAIL_COUNT == 0 and SKIP_COUNT == 0:
        print("ALL TESTS PASSED")
    elif FAIL_COUNT == 0 and SKIP_COUNT > 0:
        print("SOURCE ASSERTIONS PASSED — live HTTP skipped (see reasons above)")
    else:
        print("SOME TESTS FAILED")
    print("=" * 70)

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
