#!/usr/bin/env python3
"""
Gateway Deploy-Gate Test — verifies ALL routes reject unauthenticated requests.
Run after EVERY gateway deploy. A deploy is not "done" until this passes.

Usage:
    # Key from env (recommended) or Secret Manager:
    export GATEWAY_API_KEY=$(gcloud secrets versions access latest --secret=gateway-api-key --project=audiotours-migration)
    python test_route_lock.py

    # Or pass directly (testing only):
    python test_route_lock.py --key YOUR_KEY

Reads routes from gateway_routes.yaml (auto-covers new routes).
"""
import os
import sys
import yaml
import re
import argparse
import requests

GATEWAY_BASE = os.getenv('GATEWAY_BASE_URL', 'https://api.audioura.com')
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), 'gateway_routes.yaml')

def load_routes():
    """Load all routes from the YAML manifest."""
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()
    # Resolve ${ENV_VAR:-default} patterns (not needed for route paths, but safe)
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}', lambda m: m.group(3) or '', raw)
    manifest = yaml.safe_load(resolved)
    return manifest.get('routes', [])

def make_test_url(public_path):
    """Convert a route template to a testable URL with dummy path params."""
    # Replace Flask-style path params with dummy values
    url = public_path
    url = re.sub(r'<path:subpath>', '42.36/-71.06', url)
    url = re.sub(r'<float:(\w+)>', '42.36', url)
    url = re.sub(r'<(\w+)>', 'test-id-000', url)
    return f"{GATEWAY_BASE}{url}"

def test_route(url, method, api_key):
    """Test a single route: no-key, wrong-key, good-key."""
    results = {}
    headers_base = {'Content-Type': 'application/json'}
    
    # For POST/DELETE, send minimal body
    body = '{}' if method in ('POST', 'DELETE') else None
    
    # Test 1: No key
    try:
        r = requests.request(method, url, headers=headers_base, data=body, timeout=10)
        results['no_key'] = r.status_code
    except Exception as e:
        results['no_key'] = f'ERROR: {e}'
    
    # Test 2: Wrong key
    try:
        headers_wrong = {**headers_base, 'X-API-Key': 'WRONG-KEY-12345'}
        r = requests.request(method, url, headers=headers_wrong, data=body, timeout=10)
        results['wrong_key'] = r.status_code
    except Exception as e:
        results['wrong_key'] = f'ERROR: {e}'
    
    # Test 3: Good key
    try:
        headers_good = {**headers_base, 'X-API-Key': api_key}
        r = requests.request(method, url, headers=headers_good, data=body, timeout=10)
        results['good_key'] = r.status_code
    except Exception as e:
        results['good_key'] = f'ERROR: {e}'
    
    return results

def main():
    parser = argparse.ArgumentParser(description='Gateway route lock test')
    parser.add_argument('--key', help='API key (or set GATEWAY_API_KEY env var)')
    args = parser.parse_args()
    
    api_key = args.key or os.getenv('GATEWAY_API_KEY', '')
    if not api_key:
        print("ERROR: No API key provided. Set GATEWAY_API_KEY env var or use --key")
        sys.exit(1)
    
    routes = load_routes()
    if not routes:
        print("ERROR: No routes found in gateway_routes.yaml")
        sys.exit(1)
    
    print(f"=== Gateway Deploy-Gate Test ===")
    print(f"Base: {GATEWAY_BASE}")
    print(f"Routes: {len(routes)}")
    print(f"{'='*70}")
    
    failures = []
    passes = 0
    
    for route in routes:
        public_path = route['public_path']
        method = route['methods'][0]  # Test with first method
        auth = route.get('auth', 'api_key')
        url = make_test_url(public_path)
        
        results = test_route(url, method, api_key)
        
        # Check expectations
        no_key_ok = results['no_key'] == 401
        wrong_key_ok = results['wrong_key'] == 401
        good_key_ok = results['good_key'] != 401  # Should NOT be 401 with valid key
        
        status = '✅' if (no_key_ok and wrong_key_ok and good_key_ok) else '❌'
        
        if status == '✅':
            passes += 1
        else:
            failures.append({
                'path': public_path,
                'method': method,
                'results': results,
                'no_key_ok': no_key_ok,
                'wrong_key_ok': wrong_key_ok,
                'good_key_ok': good_key_ok
            })
        
        print(f"{status} {method:6s} {public_path:50s} | no-key={results['no_key']} wrong-key={results['wrong_key']} good-key={results['good_key']}")
    
    print(f"{'='*70}")
    print(f"PASSED: {passes}/{len(routes)}")
    
    if failures:
        print(f"\n❌ FAILURES ({len(failures)}):")
        for f in failures:
            issues = []
            if not f['no_key_ok']:
                issues.append(f"no-key returned {f['results']['no_key']} (expected 401)")
            if not f['wrong_key_ok']:
                issues.append(f"wrong-key returned {f['results']['wrong_key']} (expected 401)")
            if not f['good_key_ok']:
                issues.append(f"good-key returned {f['results']['good_key']} (should NOT be 401)")
            print(f"  {f['method']} {f['path']}: {'; '.join(issues)}")
        print(f"\n⛔ DEPLOY NOT SAFE — {len(failures)} route(s) have auth issues")
        sys.exit(1)
    else:
        print(f"\n✅ ALL ROUTES LOCKED — deploy is safe")
        sys.exit(0)

if __name__ == '__main__':
    main()
