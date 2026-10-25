#!/usr/bin/env python3
"""LOCAL-764 — in-process proof that the SUBSCRIBED manifest loads and is
fail-closed, and that selecting it does not change the default (Beta) behaviour.

Complements test_subscribed_route_coverage.py (which proves every app call has a
route) by exercising the real gateway app built from
gateway_routes.subscribed.yaml with Flask's test client — no network, no deploy:

  1. With GATEWAY_ROUTES_FILE set, main loads the subscribed manifest (its
     backends include the -subscribed services the Beta manifest lacks:
     user-api, tour-id-resolution, voice, generator, custom-audio).
  2. Every manifest route is auth: api_key — a request without X-API-Key is
     refused (401); the backend proxy itself is stubbed so a good key passes
     auth (NOT 401).
  3. With GATEWAY_ROUTES_FILE UNSET, main loads the Beta manifest unchanged
     (gateway_routes.yaml) — the default is byte-for-byte as before.

Run: python api-gateway/test_subscribed_gateway_loads.py
"""
import importlib
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBED = 'gateway_routes.subscribed.yaml'
TEST_KEY = 'local764-test-key'

# Representative subscribed-only routes (absent from the Beta manifest) that
# MUST register and fail closed. One per newly-added backend family.
SAMPLE = [
    ('GET', '/communities/map'),            # user-api
    ('POST', '/communities/1/join'),        # user-api
    ('GET', '/wallet/u1'),                  # orchestrator (subscribed-only)
    ('GET', '/tour/686/role'),              # orchestrator (LOCAL-762)
    ('POST', '/purchases/verify'),          # user-api IAP verify
    ('GET', '/tour/686/resolve'),           # tour-id-resolution
    ('POST', '/parse_voice_search'),        # voice
    ('POST', '/tour/share'),                # generator
    ('GET', '/tour/686/audio-metadata'),    # custom-audio
]

# Backends the subscribed manifest must declare (the -subscribed services).
REQUIRED_BACKENDS = {
    'map-delivery', 'orchestrator', 'user-api', 'translation',
    'news-orchestrator', 'newsletter', 'treats', 'tour-editing',
    'tour-id-resolution', 'generator', 'voice', 'custom-audio',
}


def _fresh_main(routes_file):
    if routes_file is None:
        os.environ.pop('GATEWAY_ROUTES_FILE', None)
    else:
        os.environ['GATEWAY_ROUTES_FILE'] = routes_file
    os.environ['GATEWAY_API_KEY'] = TEST_KEY
    sys.path.insert(0, HERE)
    import main
    importlib.reload(main)
    # Stub the proxy so a passing-auth request needs no real backend.
    main._proxy_request = lambda backend_url, path, timeout=60: (
        main.jsonify({'stubbed': True, 'backend_url': backend_url, 'path': path})
    )
    return main


def manifest_static_checks():
    failures = []
    with open(os.path.join(HERE, SUBSCRIBED), 'r', encoding='utf-8') as f:
        raw = f.read()
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}',
                      lambda m: m.group(3) or '', raw)
    m = yaml.safe_load(resolved)

    be = set(m.get('backends', {}).keys())
    missing_be = REQUIRED_BACKENDS - be
    if missing_be:
        failures.append(f"backends missing: {sorted(missing_be)}")

    # Every route must be api_key (no public 'none' routes on subscribed).
    for r in m.get('routes', []):
        if r.get('auth', 'api_key') != 'api_key':
            failures.append(f"{r['public_path']}: auth={r.get('auth')} "
                            f"(expected api_key)")
    # internal_only must list admin routes (ADMIN_API_KEY surface).
    admin = [e for e in m.get('internal_only', [])
             if 'admin' in e.get('path', '')]
    if not admin:
        failures.append("internal_only must list the /communities/admin/* "
                        "routes (ADMIN_API_KEY) as not publicly exposed")
    return failures


def live_checks():
    failures = []
    main = _fresh_main(SUBSCRIBED)

    if not os.path.basename(main.MANIFEST_PATH) == SUBSCRIBED:
        failures.append(f"MANIFEST_PATH not subscribed: {main.MANIFEST_PATH}")

    be = set(main.BACKENDS.keys())
    if not REQUIRED_BACKENDS.issubset(be):
        failures.append(f"loaded backends missing: "
                        f"{sorted(REQUIRED_BACKENDS - be)}")

    client = main.app.test_client()
    for method, url in SAMPLE:
        req = getattr(client, method.lower())
        body = {} if method in ('POST', 'DELETE') else None
        # No key -> 401
        r = req(url, json=body)
        if r.status_code != 401:
            failures.append(f"{method} {url}: no-key={r.status_code} "
                            f"(expected 401 — route missing or not fail-closed)")
        # Good key -> NOT 401 (auth passes; proxy stubbed)
        r = req(url, headers={'X-API-Key': TEST_KEY}, json=body)
        if r.status_code == 401:
            failures.append(f"{method} {url}: good-key=401 (auth should pass)")
    return failures


def default_unchanged_check():
    failures = []
    main = _fresh_main(None)  # unset -> default Beta manifest
    if os.path.basename(main.MANIFEST_PATH) != 'gateway_routes.yaml':
        failures.append(f"default manifest changed: {main.MANIFEST_PATH} "
                        f"(expected gateway_routes.yaml)")
    # A subscribed-only route must NOT exist on the default manifest.
    client = main.app.test_client()
    r = client.get('/wallet/u1', headers={'X-API-Key': TEST_KEY})
    if r.status_code != 404:
        failures.append(f"/wallet/u1 on default manifest -> {r.status_code} "
                        f"(expected 404; it is subscribed-only)")
    return failures


def main_run():
    print("=== LOCAL-764 Subscribed gateway load + fail-closed (in-process) ===")
    allf = []

    print("\n[1] Manifest static checks:")
    f1 = manifest_static_checks()
    (print("  OK: 12 -subscribed backends present, all routes api_key, admin "
           "routes internal_only") if not f1
     else [print(f"  FAIL: {x}") for x in f1])
    allf += f1

    print("\n[2] Live app auth checks (subscribed manifest):")
    f2 = live_checks()
    (print(f"  OK: {len(SAMPLE)} subscribed-only routes register and are "
           f"fail-closed (no-key=401, good-key!=401)") if not f2
     else [print(f"  FAIL: {x}") for x in f2])
    allf += f2

    print("\n[3] Default (GATEWAY_ROUTES_FILE unset) still loads Beta manifest:")
    f3 = default_unchanged_check()
    (print("  OK: default manifest is gateway_routes.yaml; /wallet is 404 "
           "there (subscribed-only)") if not f3
     else [print(f"  FAIL: {x}") for x in f3])
    allf += f3

    print("\n" + "=" * 60)
    if allf:
        print(f"FAILED: {len(allf)} issue(s)")
        return 1
    print("PASSED: subscribed manifest loads, is fail-closed, and the default "
          "is unchanged.")
    return 0


if __name__ == '__main__':
    sys.exit(main_run())
