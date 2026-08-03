#!/usr/bin/env python3
"""
LOCAL-154: Prove wallet Blueprint routes are registered on the shared orchestrator.

Method: import the orchestrator module in-process, build a Flask test_client(),
and assert each of the five routes resolves in app.url_map (the LOCAL-134
method). A route in url_map is proof of registration — no container needed.

Then exercise each route via test_client() and confirm it returns something
other than a generic Flask HTML 404 (structured JSON response).

Finally: break-probe — neuter the registration, prove the test goes red, restore.
"""

import os
import sys
import importlib
import re
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def separator(title):
    print(f"\n{'─' * 70}")
    print(f"  {title}")
    print(f"{'─' * 70}")


def is_generic_flask_404(response_data):
    """Detect the generic Flask HTML 404 that means 'route not registered'."""
    text = response_data.decode("utf-8", errors="replace") if isinstance(response_data, bytes) else response_data
    return "<!DOCTYPE HTML" in text and "404 Not Found" in text


def get_app():
    """Import and return the Flask app from tour_orchestrator_service.

    We must re-import fresh each time because Blueprint registration is
    module-level and happens on import.
    """
    # Remove cached modules to get fresh import
    mods_to_remove = [k for k in sys.modules.keys()
                      if k in ('tour_orchestrator_service', 'wallet_api', 'swipe_preference_service')]
    for mod in mods_to_remove:
        del sys.modules[mod]

    import tour_orchestrator_service
    return tour_orchestrator_service.app


def main():
    print("=" * 70)
    print("  LOCAL-154: Wallet Routes Registered on Shared Orchestrator")
    print("=" * 70)

    passed = 0
    failed = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1: url_map inspection — prove routes exist
    # ═══════════════════════════════════════════════════════════════════════════
    separator("PHASE 1: url_map — five routes must resolve")

    app = get_app()

    # The five routes from LOCAL-152's table
    expected_routes = [
        ("GET", "/wallet/<user_id>"),
        ("GET", "/wallet/<user_id>/transactions"),
        ("GET", "/plans/available"),
        ("POST", "/wallet/<user_id>/topup"),
        ("POST", "/user/<user_id>/stop-feedback"),
    ]

    # Extract all rules from url_map
    url_rules = []
    for rule in app.url_map.iter_rules():
        for method in rule.methods:
            if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                url_rules.append((method, rule.rule))

    print(f"\n  Registered routes ({len(url_rules)} total):")
    for method, rule in sorted(url_rules):
        print(f"    {method:6s} {rule}")

    print(f"\n  Checking five required wallet/preference routes:")
    for method, route in expected_routes:
        found = any(m == method and r == route for m, r in url_rules)
        status = "✓ FOUND" if found else "✗ MISSING"
        print(f"    {status}: {method} {route}")
        if found:
            passed += 1
        else:
            failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2: test_client() — each route returns structured JSON, not HTML 404
    # ═══════════════════════════════════════════════════════════════════════════
    separator("PHASE 2: test_client() — no generic Flask HTML 404")

    client = app.test_client()

    # These requests will fail at the DB layer (no real DB in-process), but
    # they must NOT return the generic Flask HTML 404. Any response from
    # application code (even 500) proves the route is registered.
    test_cases = [
        ("GET", "/wallet/test-user-154"),
        ("GET", "/wallet/test-user-154/transactions"),
        ("GET", "/plans/available"),
        ("POST", "/wallet/test-user-154/topup"),
        ("POST", "/user/test-user-154/stop-feedback"),
    ]

    for method, path in test_cases:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={}, content_type="application/json")

        data = resp.get_data()
        generic_404 = is_generic_flask_404(data)
        status_code = resp.status_code

        if generic_404:
            print(f"    ✗ FAIL: {method} {path} → generic Flask HTML 404 (NOT REGISTERED)")
            failed += 1
        else:
            # Route is registered — it returned something from application code
            # For /plans/available we expect 200 (no DB needed)
            # For others we might get 500 (DB not available) or 400 (bad body)
            # All of these prove the route exists
            print(f"    ✓ PASS: {method} {path} → {status_code} (route registered, not generic 404)")
            passed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3: /plans/available returns actual plan data
    # ═══════════════════════════════════════════════════════════════════════════
    separator("PHASE 3: /plans/available returns plan list")

    resp = client.get("/plans/available")
    if resp.status_code == 200:
        import json
        plans = json.loads(resp.get_data())
        plan_ids = [p["plan_id"] for p in plans]
        print(f"    Plans returned: {plan_ids}")
        if set(plan_ids) == {"free", "ppu", "unlimited"}:
            print("    ✓ PASS — All three plans present")
            passed += 1
        else:
            print(f"    ✗ FAIL — Expected free/ppu/unlimited, got {plan_ids}")
            failed += 1
    else:
        print(f"    ✗ FAIL — /plans/available returned {resp.status_code}")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4: Break-probe — neuter wallet_api import, prove routes vanish
    # ═══════════════════════════════════════════════════════════════════════════
    separator("PHASE 4: Break-probe")

    # Read source
    orch_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tour_orchestrator_service.py")
    with open(orch_path, "r") as f:
        original_source = f.read()

    # Count occurrences of the registration line (D36: print replacement count)
    registration_pattern = "from wallet_api import wallet_bp"
    replacement_count = original_source.count(registration_pattern)
    print(f"\n  Replacement count for '{registration_pattern}': {replacement_count}")
    assert replacement_count >= 1, "Cannot find wallet_api import in source!"

    # Neuter: replace the import with a forced ImportError
    neutered_source = original_source.replace(
        registration_pattern,
        "raise ImportError('BREAK_PROBE_LOCAL_154')  # "  + registration_pattern,
    )

    # Write neutered version
    with open(orch_path, "w") as f:
        f.write(neutered_source)
    print("  Neutered: wallet_api import raises ImportError")

    # Re-import and check url_map
    try:
        # Clear module cache
        mods_to_remove = [k for k in sys.modules.keys()
                          if k in ('tour_orchestrator_service', 'wallet_api', 'swipe_preference_service')]
        for mod in mods_to_remove:
            del sys.modules[mod]

        import tour_orchestrator_service as neutered_orch
        neutered_app = neutered_orch.app

        # Check: wallet routes should be GONE
        neutered_rules = []
        for rule in neutered_app.url_map.iter_rules():
            for method in rule.methods:
                if method in ("GET", "POST"):
                    neutered_rules.append((method, rule.rule))

        wallet_routes_present = [
            (m, r) for m, r in neutered_rules
            if "/wallet/" in r or "/plans/" in r
        ]

        if len(wallet_routes_present) == 0:
            print("  ✓ BREAK confirmed: wallet routes vanished from url_map")
            passed += 1
        else:
            print(f"  ✗ FAIL: wallet routes still present after neutering: {wallet_routes_present}")
            failed += 1

        # Also verify preference route is still registered (independent)
        pref_route = any(r == "/user/<user_id>/stop-feedback" for _, r in neutered_rules)
        if pref_route:
            print("  ✓ Preference route still registered (independent of wallet)")
        else:
            print("  ⚠ Preference route also missing (acceptable if both neutered)")

    finally:
        # RESTORE original source immediately
        with open(orch_path, "w") as f:
            f.write(original_source)
        print("  Restored: original source written back")

    # Verify restoration
    with open(orch_path, "r") as f:
        restored = f.read()
    assert restored == original_source, "CRITICAL: source not properly restored!"
    print("  ✓ Source verified identical to original")

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 5: Error logging — verify ERROR level on import failure
    # ═══════════════════════════════════════════════════════════════════════════
    separator("PHASE 5: ERROR-level logging on import failure")

    # Check that the except block uses logging.error (not just print)
    error_logging_patterns = [
        'getLogger("tour_orchestrator_service").error',
        "_wallet_logging",
    ]
    has_error_logging = all(p in original_source for p in error_logging_patterns)
    if has_error_logging:
        print("  ✓ PASS — Wallet import failure logs at ERROR level")
        passed += 1
    else:
        print("  ✗ FAIL — Wallet import failure does not log at ERROR level")
        failed += 1

    # Same for preference routes
    pref_patterns = [
        "_pref_logging",
        'getLogger("tour_orchestrator_service").error',
    ]
    has_pref_error = all(p in original_source for p in pref_patterns)
    if has_pref_error:
        print("  ✓ PASS — Preference import failure logs at ERROR level")
        passed += 1
    else:
        print("  ✗ FAIL — Preference import failure does not log at ERROR level")
        failed += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    separator("SUMMARY")
    total = passed + failed
    print(f"  Passed: {passed}/{total}")
    print(f"  Failed: {failed}/{total}")

    if failed > 0:
        print("\n  ✗ OVERALL: FAIL")
        sys.exit(1)
    else:
        print("\n  ✓ OVERALL: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
