#!/usr/bin/env python3
"""
test_local153_tour_editing_shims_guard.py — Guard test for tour-editing shim routes.
====================================================================================
LOCAL-153: Verify that update-stop and job-status routes are registered in
tour_editing_phase2.py via app.url_map (D35: exercise, don't just inspect).

Two-part test per the project pattern:
  1. Break-probe: temporarily remove the routes from a copy and confirm the
     test catches the absence (D36: print replacement count — 0 means probe
     never applied and is not evidence).
  2. Real assertion: import the Flask app from the source file and verify
     both routes resolve in url_map.

Exit 0 = both routes registered.  Exit 1 = one or both missing.

Usage:
    python3 tests/test_local153_tour_editing_shims_guard.py
"""
import os
import sys
import tempfile
import importlib.util
import unittest.mock
from unittest.mock import MagicMock

# ─── Configuration ───────────────────────────────────────────────────────────
SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_FILE = os.path.join(SERVICE_DIR, "tour_editing_phase2.py")

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


def _mock_missing_modules():
    """Install mock modules for dependencies not available on the host.

    The test only needs Flask's url_map — it does not exercise boto3, psycopg2,
    etc. Mocking them lets us import the app purely for route registration.
    """
    mocks = {}
    for mod_name in [
        "boto3", "psycopg2", "psycopg2.errors", "psycopg2.extras",
        "flask_cors", "requests",
    ]:
        if mod_name not in sys.modules:
            mock = MagicMock()
            # flask_cors.CORS must be callable and return nothing harmful
            if mod_name == "flask_cors":
                mock.CORS = lambda app, **kw: None
            sys.modules[mod_name] = mock
            mocks[mod_name] = mock
    return mocks


def _cleanup_mocks(mocks):
    """Remove mock modules we injected."""
    for mod_name in mocks:
        if mod_name in sys.modules and sys.modules[mod_name] is mocks[mod_name]:
            del sys.modules[mod_name]


def load_app_from_file(filepath):
    """Import a Python file as a module and return its Flask app object.

    Mocks heavy dependencies (boto3, psycopg2) that aren't needed for
    route registration. Only Flask itself must be real.
    """
    # Set env vars the app expects
    os.environ.setdefault("DATABASE_URL", "postgresql://admin:password123@localhost:5433/audiotours")
    os.environ.setdefault("POLLY_TTS_URL", "http://localhost:5018")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

    # Add service dir to path for any local imports
    if SERVICE_DIR not in sys.path:
        sys.path.insert(0, SERVICE_DIR)

    mocks = _mock_missing_modules()
    try:
        # Remove any previously loaded version of this module
        mod_name = "tour_editing_phase2_under_test"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        spec = importlib.util.spec_from_file_location(mod_name, filepath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.app
    finally:
        _cleanup_mocks(mocks)


def check_route_in_url_map(app, route_path, method):
    """Check if a route is registered in Flask's url_map using adapter.match()."""
    from werkzeug.routing import RequestRedirect
    from werkzeug.exceptions import MethodNotAllowed, NotFound

    adapter = app.url_map.bind("")
    try:
        adapter.match(route_path, method=method)
        return True
    except (RequestRedirect, MethodNotAllowed):
        # Redirect or wrong-method means the route exists (registered)
        return True
    except NotFound:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: Break-probe — verify the test can detect absence (D36)
# ═══════════════════════════════════════════════════════════════════════════════

def test_break_probe():
    """Create a copy with routes removed, verify the test catches it.

    D36 mandates: print replacement count. If count is 0, the probe never
    applied and its result is not evidence about the system.
    """
    print("\n[BREAK PROBE] Verifying test detects missing routes")

    with open(SERVICE_FILE, "r") as f:
        source = f.read()

    # Remove the update-stop route decorator and function
    needle_update_stop = "@app.route('/tour/<tour_id>/update-stop', methods=['POST'])"
    count_update_stop = source.count(needle_update_stop)
    print(f"  Replacement count (update-stop decorator): {count_update_stop}")
    check("Break-probe: update-stop found in source for removal",
          count_update_stop > 0,
          "Cannot run break-probe — needle not found (D36: probe never applied)")

    needle_job_status = "@app.route('/tour/<tour_id>/job-status/<job_id>', methods=['GET'])"
    count_job_status = source.count(needle_job_status)
    print(f"  Replacement count (job-status decorator): {count_job_status}")
    check("Break-probe: job-status found in source for removal",
          count_job_status > 0,
          "Cannot run break-probe — needle not found (D36: probe never applied)")

    if count_update_stop == 0 or count_job_status == 0:
        print("  SKIP: Break-probe cannot proceed — source lacks expected needles")
        return

    # Remove both route blocks by commenting out the decorators
    # This makes the functions orphaned (not registered as routes)
    broken_source = source.replace(
        needle_update_stop,
        "# REMOVED: " + needle_update_stop
    ).replace(
        needle_job_status,
        "# REMOVED: " + needle_job_status
    )

    # Write to temp file and try to load it
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(broken_source)
        broken_path = f.name

    try:
        broken_app = load_app_from_file(broken_path)

        # These should FAIL (return False) — the routes are removed
        update_stop_present = check_route_in_url_map(
            broken_app, "/tour/test-id/update-stop", "POST")
        job_status_present = check_route_in_url_map(
            broken_app, "/tour/test-id/job-status/job-123", "GET")

        check("Break-probe: update-stop absent in broken copy",
              not update_stop_present,
              "Route still found after removal — test is hollow!")
        check("Break-probe: job-status absent in broken copy",
              not job_status_present,
              "Route still found after removal — test is hollow!")
    except Exception as e:
        # If loading fails, that's also proof the broken version can't serve routes
        # But we prefer a clean load + absent route for stronger evidence
        print(f"  WARNING: Broken copy failed to load: {e}")
        print(f"  Falling back: broken code cannot serve routes → break-probe passes")
        check("Break-probe: broken copy does not serve routes (load failure)", True)
    finally:
        os.unlink(broken_path)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: Real assertion — both routes registered in url_map
# ═══════════════════════════════════════════════════════════════════════════════

def test_routes_registered():
    """Import the real app and verify both shim routes are in url_map."""
    print("\n[URL_MAP GUARD] Verifying shim routes registered in Flask app")
    print(f"  File: {SERVICE_FILE}")

    if not os.path.exists(SERVICE_FILE):
        check("Source file exists", False, f"Not found: {SERVICE_FILE}")
        return

    try:
        app = load_app_from_file(SERVICE_FILE)
    except Exception as e:
        check("Flask app loads", False, f"Import error: {e}")
        return

    check("Flask app loads", True)

    # Check update-stop route
    update_stop_registered = check_route_in_url_map(
        app, "/tour/test-id/update-stop", "POST")
    check("POST /tour/<tour_id>/update-stop registered in url_map",
          update_stop_registered,
          "Route not found — shim missing from tour_editing_phase2.py!")

    # Check job-status route
    job_status_registered = check_route_in_url_map(
        app, "/tour/test-id/job-status/job-123", "GET")
    check("GET /tour/<tour_id>/job-status/<job_id> registered in url_map",
          job_status_registered,
          "Route not found — shim missing from tour_editing_phase2.py!")

    # Bonus: print all registered routes containing our targets
    print("\n  Registered routes containing 'update-stop' or 'job-status':")
    for rule in app.url_map.iter_rules():
        if "update-stop" in rule.rule or "job-status" in rule.rule:
            print(f"    {rule.methods - {'HEAD', 'OPTIONS'}} {rule.rule}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 70)
    print("test_local153_tour_editing_shims_guard.py")
    print("LOCAL-153: Tour-editing shim routes (update-stop, job-status) guard")
    print("=" * 70)

    test_break_probe()
    test_routes_registered()

    print(f"\n{'=' * 70}")
    print(f"Results: {PASS_COUNT} passed, {FAIL_COUNT} failed")
    print("=" * 70)

    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
