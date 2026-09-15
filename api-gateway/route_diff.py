#!/usr/bin/env python3
"""Diff the gateway route list of two gateway_routes.yaml manifests.

GCS-5R B2 proof: the NEW gateway image's route manifest must equal the deployed
v35 image's manifest PLUS exactly the 4 tour-editing routes and 1 backend — and
nothing else (no accidental /user drift, no dropped routes).

Usage:
  python api-gateway/route_diff.py <old_yaml> <new_yaml>

Prints added/removed backends and routes and exits non-zero if the delta is
anything other than the 4 editing routes + tour-editing backend.
Windows-safe: utf-8 on every read.
"""
import sys
import re
import yaml


EXPECTED_ADDED_ROUTES = {
    ('/tour/<tour_id>/update-multiple-stops', 'POST'),
    ('/tour/<tour_id>/update-stop', 'POST'),
    ('/tour/<tour_id>/job-status/<job_id>', 'GET'),
    ('/tour/<tour_id>/download', 'GET'),
}
EXPECTED_ADDED_BACKENDS = {'tour-editing'}


def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    # Resolve ${VAR:-default} to its default (or empty) so YAML parses cleanly.
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}', lambda m: m.group(3) or '', raw)
    return yaml.safe_load(resolved)


def route_set(manifest):
    s = set()
    for r in manifest.get('routes', []):
        for m in r.get('methods', []):
            s.add((r['public_path'], m))
    return s


def backend_set(manifest):
    return set(manifest.get('backends', {}).keys())


def main():
    if len(sys.argv) != 3:
        print("usage: route_diff.py <old_yaml> <new_yaml>")
        return 2
    old = load(sys.argv[1])
    new = load(sys.argv[2])

    old_routes, new_routes = route_set(old), route_set(new)
    old_be, new_be = backend_set(old), backend_set(new)

    added_routes = new_routes - old_routes
    removed_routes = old_routes - new_routes
    added_be = new_be - old_be
    removed_be = old_be - new_be

    print(f"OLD: {sys.argv[1]}  ({len(old_routes)} route-methods, {len(old_be)} backends)")
    print(f"NEW: {sys.argv[2]}  ({len(new_routes)} route-methods, {len(new_be)} backends)")
    print("\nAdded backends:   " + (", ".join(sorted(added_be)) or "(none)"))
    print("Removed backends: " + (", ".join(sorted(removed_be)) or "(none)"))
    print("\nAdded routes:")
    for p, m in sorted(added_routes):
        print(f"  + {m:5s} {p}")
    print("Removed routes:")
    for p, m in sorted(removed_routes):
        print(f"  - {m:5s} {p}")

    ok = True
    if added_routes != EXPECTED_ADDED_ROUTES:
        ok = False
        print(f"\nFAIL: added routes != expected 4 editing routes. "
              f"unexpected={added_routes ^ EXPECTED_ADDED_ROUTES}")
    if removed_routes:
        ok = False
        print(f"\nFAIL: routes were REMOVED vs v35: {removed_routes}")
    if added_be != EXPECTED_ADDED_BACKENDS:
        ok = False
        print(f"\nFAIL: added backends != {{tour-editing}}: {added_be}")
    if removed_be:
        ok = False
        print(f"\nFAIL: backends were REMOVED vs v35: {removed_be}")

    print("\n" + "=" * 60)
    if ok:
        print("PASS: only difference is the 4 tour-editing routes + tour-editing backend.")
        return 0
    print("FAIL: route delta is not exactly the 4 editing routes + 1 backend.")
    return 1


if __name__ == '__main__':
    sys.exit(main())
