#!/usr/bin/env python3
"""
GCS-5 gateway route test — IN-PROCESS (no network, no deploy needed).

Proves, using Flask's test client against the real gateway app built from
gateway_routes.yaml:
  1. All four tour-editing paths are registered and mapped to the
     `tour-editing` backend with auth: api_key.
  2. A request WITHOUT X-API-Key is refused (401) on every editing route.
  3. A request WITH a wrong key is refused (401).
  4. With the correct key, the request is NOT rejected at the auth layer
     (it passes auth; the backend proxy call itself is stubbed out).

This complements test_route_lock.py (which probes a LIVE deployed gateway).
Run: python api-gateway/test_editing_routes.py
"""
import os
import re
import sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(HERE, 'gateway_routes.yaml')

EDITING_PATHS = [
    ('/tour/<tour_id>/update-multiple-stops', 'POST'),
    ('/tour/<tour_id>/update-stop', 'POST'),
    ('/tour/<tour_id>/job-status/<job_id>', 'GET'),
    ('/tour/<tour_id>/download', 'GET'),
]

TEST_KEY = 'gcs5-test-key'


def load_manifest():
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}', lambda m: m.group(3) or '', raw)
    return yaml.safe_load(resolved)


def manifest_checks(manifest):
    """Static checks on the YAML: routes exist, backend + auth correct, additive."""
    failures = []
    routes = manifest.get('routes', [])
    by_path = {(r['public_path'], m): r for r in routes for m in r['methods']}

    if 'tour-editing' not in manifest.get('backends', {}):
        failures.append("backends: missing 'tour-editing' entry")

    for path, method in EDITING_PATHS:
        r = by_path.get((path, method))
        if not r:
            failures.append(f"route missing: {method} {path}")
            continue
        if r.get('backend') != 'tour-editing':
            failures.append(f"{method} {path}: backend={r.get('backend')} (expected tour-editing)")
        if r.get('auth', 'api_key') != 'api_key':
            failures.append(f"{method} {path}: auth={r.get('auth')} (expected api_key)")

    # Save routes must have a generous timeout (>=300s) to cover full-tour TTS.
    for path in ('/tour/<tour_id>/update-multiple-stops', '/tour/<tour_id>/update-stop'):
        r = by_path.get((path, 'POST'))
        if r and r.get('timeout', 60) < 300:
            failures.append(f"POST {path}: timeout={r.get('timeout')} (expected >=300)")

    # Additive check: the pre-existing map-delivery resolve route is untouched.
    resolve = by_path.get(('/tour/<tour_id>/resolve', 'GET'))
    if not resolve or resolve.get('backend') != 'map-delivery':
        failures.append("existing /tour/<tour_id>/resolve -> map-delivery route was changed or removed")

    return failures


def live_app_checks():
    """Build the real gateway app and exercise auth with Flask's test client."""
    failures = []
    os.environ['GATEWAY_API_KEY'] = TEST_KEY
    sys.path.insert(0, HERE)
    import importlib
    main = importlib.import_module('main')
    importlib.reload(main)

    # Stub the proxy so a passing-auth request doesn't need a real backend.
    main._proxy_request = lambda backend_url, path, timeout=60: (
        main.jsonify({"stubbed": True, "backend_url": backend_url, "path": path})
    )

    client = main.app.test_client()

    def concrete(path):
        p = path.replace('<tour_id>', '123').replace('<job_id>', 'job-1')
        return p

    for path, method in EDITING_PATHS:
        url = concrete(path)
        req = getattr(client, method.lower())

        # No key -> 401
        r = req(url, json={} if method == 'POST' else None)
        if r.status_code != 401:
            failures.append(f"{method} {url}: no-key returned {r.status_code} (expected 401)")

        # Wrong key -> 401
        r = req(url, headers={'X-API-Key': 'WRONG'}, json={} if method == 'POST' else None)
        if r.status_code != 401:
            failures.append(f"{method} {url}: wrong-key returned {r.status_code} (expected 401)")

        # Good key -> NOT 401 (auth passes; proxy stubbed)
        r = req(url, headers={'X-API-Key': TEST_KEY}, json={} if method == 'POST' else None)
        if r.status_code == 401:
            failures.append(f"{method} {url}: good-key returned 401 (auth should pass)")

    return failures


def main_run():
    manifest = load_manifest()
    print("=== GCS-5 Gateway Editing-Route Test (in-process) ===")
    all_failures = []

    print("\n[1] Manifest static checks:")
    mf = manifest_checks(manifest)
    if mf:
        for f in mf:
            print(f"  FAIL: {f}")
        all_failures += mf
    else:
        print("  OK: 4 editing routes present, backend=tour-editing, auth=api_key, "
              "save timeouts >=300s, map-delivery resolve untouched")

    print("\n[2] Live app auth checks (Flask test client):")
    lf = live_app_checks()
    if lf:
        for f in lf:
            print(f"  FAIL: {f}")
        all_failures += lf
    else:
        for path, method in EDITING_PATHS:
            print(f"  OK: {method:4s} {path}  no-key=401 wrong-key=401 good-key!=401")

    print("\n" + "=" * 60)
    if all_failures:
        print(f"FAILED: {len(all_failures)} issue(s)")
        sys.exit(1)
    print("PASSED: all editing routes registered and fail-closed without X-API-Key")
    sys.exit(0)


if __name__ == '__main__':
    main_run()
