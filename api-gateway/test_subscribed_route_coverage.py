#!/usr/bin/env python3
"""LOCAL-764 — Subscribed gateway route-coverage gate.

Proves that EVERY server call the Subscribed app makes has a matching route in
api-gateway/gateway_routes.subscribed.yaml. If a new app call is added without a
subscribed route, this test fails — so the Subscribed gateway can never silently
404 a feature the app relies on (the exact bug LOCAL-764 fixes: the Subscribed
build pointed at Beta's gateway, which lacks user-api / communities / IAP /
recovery / pricing routes).

Method (the task's spec): scan audio_tour_app/lib for the app's server-call
sites — Endpoints.<verb>(Service.X, '<path>' ...) and Endpoints.url(Service.X,
'<path>') (newline-tolerant) — turn each into a concrete probe path, and check
it resolves against the subscribed manifest's public_path templates. Also covers
the two news cloud paths the app builds in Endpoints.newsStatusUrl /
newsDownloadUrl (/news-status/<id>, /news-download/<id>), which do not appear as
(Service, path) literals.

No network, no deploy: pure static analysis of the Dart sources + the YAML.

Run:  python api-gateway/test_subscribed_route_coverage.py
      (exit 0 = every app path is covered; exit 1 = missing route(s))
"""
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("PyYAML required: pip install pyyaml")
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LIB = os.path.join(REPO, 'audio_tour_app', 'lib')
MANIFEST = os.path.join(HERE, 'gateway_routes.subscribed.yaml')

# (Service.X , 'path')  — tolerant of newlines/whitespace between the two args.
_CALL = re.compile(r"Service\.(\w+)\s*,\s*'([^']*)'")

# The app also builds two news paths WITHOUT a (Service, path) literal — the
# cloud branch of Endpoints.newsStatusUrl / newsDownloadUrl. Cover them too.
_EXTRA_PATHS = [
    '/news-status/42',
    '/news-download/42',
]


def load_manifest():
    with open(MANIFEST, 'r', encoding='utf-8') as f:
        raw = f.read()
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}',
                      lambda m: m.group(3) or '', raw)
    return yaml.safe_load(resolved)


def dart_paths():
    """Return a sorted set of concrete probe paths the app calls (query and
    Dart ${...} interpolation stripped to a dummy segment)."""
    found = set()
    for root, _dirs, files in os.walk(LIB):
        for name in files:
            if not name.endswith('.dart'):
                continue
            with open(os.path.join(root, name), 'r',
                      encoding='utf-8', errors='replace') as f:
                text = f.read()
            for m in _CALL.finditer(text):
                found.add(_concrete(m.group(2)))
    for p in _EXTRA_PATHS:
        found.add(_concrete(p))
    return sorted(found)


def _concrete(path):
    """Strip the query string and replace every Dart ${...}/$var interpolation
    with a dummy single path segment, so the path can be matched against a Flask
    route template segment-by-segment."""
    # A trailing query-string interpolation — the app builds these as `$q` /
    # `$query` / `$qs` holding '?user_id=...' and appends them to the path
    # (e.g. '/communities/$id/tours$q'). Drop such a trailing token so it does
    # not get mistaken for a path segment.
    path = re.sub(r'\$\{?(?:q|qs|query)\}?$', '', path)
    path = path.split('?')[0]
    # ${ ... }  (may itself contain nested braces for maps/encode calls)
    path = re.sub(r'\$\{[^}]*\}', 'X', path)
    # bare $ident (e.g. $tourId)
    path = re.sub(r'\$\w+', 'X', path)
    # collapse any empties and ensure leading slash
    if not path.startswith('/'):
        path = '/' + path
    return path


def route_regexes(manifest):
    """Compile each manifest public_path into a regex that matches a concrete
    path, Flask-style: <path:name> matches the rest; <name> matches one
    segment."""
    compiled = []
    for r in manifest.get('routes', []):
        tmpl = r['public_path']
        rx = _template_to_regex(tmpl)
        compiled.append((tmpl, re.compile(rx)))
    return compiled


def _template_to_regex(tmpl):
    out = ['^']
    i = 0
    n = len(tmpl)
    while i < n:
        c = tmpl[i]
        if c == '<':
            j = tmpl.index('>', i)
            token = tmpl[i + 1:j]
            if token.startswith('path:'):
                out.append(r'.+')          # <path:subpath> — one or more segments
            else:
                out.append(r'[^/]+')       # <name> — exactly one segment
            i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append('$')
    return ''.join(out)


def main():
    if not os.path.isdir(LIB):
        print(f"FAIL: lib dir not found: {LIB}")
        return 2
    if not os.path.isfile(MANIFEST):
        print(f"FAIL: subscribed manifest not found: {MANIFEST}")
        return 2

    manifest = load_manifest()
    routes = route_regexes(manifest)
    app_paths = dart_paths()

    # Paths the gateway answers with its OWN intrinsic handler (main.py), not via
    # the manifest — exactly as on the Beta/Storied gateway. The app calls these
    # (health diagnostics; outbox /sync) and they must NOT be reported missing.
    intrinsic = {'/health', '/sync', '/attest-nonce'}

    print("=== LOCAL-764 Subscribed route-coverage gate ===")
    print(f"Manifest: {os.path.relpath(MANIFEST, REPO)}")
    print(f"App server-call paths discovered: {len(app_paths)}")
    print(f"Manifest routes: {len(manifest.get('routes', []))}  "
          f"backends: {len(manifest.get('backends', {}))}")
    print("-" * 70)

    missing = []
    for p in app_paths:
        if p in intrinsic:
            continue
        if not any(rx.match(p) for _tmpl, rx in routes):
            missing.append(p)

    for p in app_paths:
        if p in intrinsic:
            mark = 'intr'
        elif p in missing:
            mark = 'MISS'
        else:
            mark = ' ok '
        print(f"[{mark}] {p}")

    print("-" * 70)
    if missing:
        print(f"FAIL: {len(missing)} app path(s) have NO route in the "
              f"subscribed manifest:")
        for p in missing:
            print(f"  - {p}")
        print("\nAdd a matching route to "
              "api-gateway/gateway_routes.subscribed.yaml.")
        return 1
    print(f"PASS: all {len(app_paths)} app server-call paths are covered by the "
          f"subscribed manifest.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
