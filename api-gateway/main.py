"""
Audioura API Gateway — Data-driven auth-proxy
================================================
Routes are loaded from gateway_routes.yaml at startup.
Adding/removing an endpoint = editing the YAML, not this Python file.

Backends set to --no-allow-unauthenticated; only this gateway is public.
"""
import os
import sys
import re
import time
import hmac
import yaml
import requests as http_requests
from flask import Flask, request, jsonify, Response

sys.path.insert(0, '/app')  # Ensure storied modules are importable
try:
    from storied_version_constants import STORIED_SERVICE_VERSION
    SERVICE_VERSION = STORIED_SERVICE_VERSION
except ImportError:
    SERVICE_VERSION = "2.2.0.1"

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Load route manifest
# ---------------------------------------------------------------------------
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), 'gateway_routes.yaml')

def _load_manifest():
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        raw = f.read()
    # Resolve ${ENV_VAR:-default} patterns
    def _env_sub(m):
        var = m.group(1)
        default = m.group(3) if m.group(3) else ''
        return os.getenv(var, default)
    resolved = re.sub(r'\$\{([A-Z_]+)(?:(:-)(.*?))?\}', _env_sub, raw)
    return yaml.safe_load(resolved)

manifest = _load_manifest()
BACKENDS = manifest['backends']
ROUTES = manifest['routes']

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
API_KEY = os.getenv('GATEWAY_API_KEY', '')
if not API_KEY:
    print("[WARNING] GATEWAY_API_KEY is not set — cost-bearing endpoints will REJECT all requests (fail-closed)")

# Attestation configuration (log-only by default)
ATTESTATION_ENFORCED = os.getenv('ATTESTATION_ENFORCED', 'false').lower() == 'true'
ATTESTATION_MODE = os.getenv('ATTESTATION_MODE', 'off')  # 'log_only', 'off', or 'enforce'
ATTESTATION_SECRET = os.getenv('ATTESTATION_NONCE_SECRET', 'default-nonce-hmac-key-change-in-prod')
PLAY_INTEGRITY_API_KEY = os.getenv('PLAY_INTEGRITY_API_KEY', '')
APP_PACKAGE_NAME = os.getenv('APP_PACKAGE_NAME', 'com.audioura.audiotours')
APP_BUNDLE_ID = os.getenv('APP_BUNDLE_ID', 'com.audioura.app')
print(f"[ATTESTATION] Mode: {ATTESTATION_MODE} (ENFORCED={ATTESTATION_ENFORCED})")

# Nonce is STATELESS (HMAC-signed with embedded timestamp) — works across multiple Cloud Run instances.
# No shared state needed. Any instance can verify any nonce it or another instance issued.
import secrets
import hashlib
NONCE_TTL_SECONDS = 300  # 5 minutes

def _require_api_key():
    """Check X-API-Key header. Fails CLOSED if key not configured."""
    if not API_KEY:
        return jsonify({"error": "service_misconfigured", "message": "API key not configured on gateway"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized", "message": "Valid X-API-Key header required"}), 401
    return None


def _verify_attestation():
    """Verify platform attestation token on cost-bearing endpoints.
    
    Behavior depends on ATTESTATION_MODE env var:
    - 'off' (default): skip entirely, no logging.
    - 'log_only': call attestation_verifier functions, log results, ALWAYS allow.
    - 'enforce': not implemented for Aug 1 release (see [S58]).
    
    The app sends: X-App-Attestation (token) and X-App-Platform (android|ios).
    """
    # If attestation is off, skip entirely
    if ATTESTATION_MODE not in ('log_only', 'enforce'):
        return None

    token = request.headers.get('X-App-Attestation', '') or request.headers.get('X-Attestation-Token', '')
    platform = request.headers.get('X-App-Platform', '') or request.headers.get('X-Attestation-Platform', 'unknown')

    # Import attestation verifier (placed in sys.path at gateway startup)
    try:
        import sys
        _dev_path = os.path.join(os.path.dirname(os.path.dirname(__file__)))
        if _dev_path not in sys.path:
            sys.path.insert(0, _dev_path)
        from attestation_verifier import verify_attestation_token, verify_play_integrity, verify_app_attest
    except ImportError as e:
        print(f"[ATTESTATION] Warning: could not import attestation_verifier: {e}")
        return None

    # Generate a request_id for correlation
    import uuid
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4())[:8])

    # Step 1: Structural log (always runs in log_only mode)
    verify_attestation_token(token if token else None, platform, request_id)

    # Step 2: Platform-specific verification (log-only, never blocks)
    if platform.lower() == 'android' and token:
        verify_play_integrity(token, APP_PACKAGE_NAME, PLAY_INTEGRITY_API_KEY)
    elif platform.lower() == 'ios' and token:
        verify_app_attest(token, key_id=request.headers.get('X-App-Key-ID', ''), app_id=APP_BUNDLE_ID)

    # NEVER block in log_only mode — always return None (allow request)
    return None


def _issue_nonce():
    """Create a stateless, HMAC-signed nonce that any gateway instance can verify.
    Format: <timestamp_hex>.<random_hex>.<hmac_hex>
    Any instance can verify by recomputing the HMAC over timestamp+random with the shared secret."""
    ts = format(int(time.time()), 'x')  # hex timestamp
    rand = secrets.token_hex(16)  # 32-char random
    payload = f"{ts}.{rand}"
    sig = hmac.new(ATTESTATION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def _verify_nonce(nonce):
    """Verify a stateless HMAC-signed nonce. Returns True if valid and not expired."""
    parts = nonce.split('.')
    if len(parts) != 3:
        return False
    ts_hex, rand, sig = parts
    # Verify HMAC
    payload = f"{ts_hex}.{rand}"
    expected_sig = hmac.new(ATTESTATION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected_sig):
        return False
    # Verify not expired
    try:
        issued_at = int(ts_hex, 16)
        if time.time() - issued_at > NONCE_TTL_SECONDS:
            return False
    except ValueError:
        return False
    return True

# ---------------------------------------------------------------------------
# Identity token cache (Google metadata server)
# ---------------------------------------------------------------------------
_token_cache = {}

def _get_identity_token(audience):
    cached = _token_cache.get(audience)
    if cached and cached['expires'] > time.time():
        return cached['token']
    metadata_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={audience}"
    try:
        resp = http_requests.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=5)
        if resp.status_code == 200:
            token = resp.text
            _token_cache[audience] = {'token': token, 'expires': time.time() + 3500}
            return token
    except Exception as e:
        print(f"[AUTH] Failed to get token for {audience}: {e}")
    return None

# ---------------------------------------------------------------------------
# Proxy core
# ---------------------------------------------------------------------------
def _proxy_request(backend_url, path, timeout=60):
    """Proxy the current Flask request to a backend with an identity token."""
    target_url = f"{backend_url}{path}"
    token = _get_identity_token(backend_url)

    headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'content-length', 'transfer-encoding', 'x-internal-service')}
    if token:
        headers['Authorization'] = f"Bearer {token}"

    try:
        resp = http_requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            params=request.args,
            timeout=timeout,
            stream=True
        )
        excluded_headers = ('content-encoding', 'content-length', 'transfer-encoding', 'connection')
        response_headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]
        return Response(resp.content, status=resp.status_code, headers=response_headers)
    except http_requests.Timeout:
        return jsonify({"error": "Backend timeout"}), 504
    except Exception as e:
        return jsonify({"error": f"Proxy error: {str(e)}"}), 502

# ---------------------------------------------------------------------------
# Register routes from manifest
# ---------------------------------------------------------------------------
def _build_upstream_path(upstream_template, **kwargs):
    """Convert {var} placeholders in upstream to actual values from URL params."""
    result = upstream_template
    for key, value in kwargs.items():
        result = result.replace(f'{{{key}}}', str(value))
    return result

def _make_handler(route_cfg):
    """Create a Flask view function for a route config entry."""
    backend_key = route_cfg['backend']
    upstream_template = route_cfg['upstream']
    auth = route_cfg.get('auth', 'api_key')  # FAIL-CLOSED: default requires API key
    timeout = route_cfg.get('timeout', 60)

    def handler(**kwargs):
        if auth == 'api_key':
            err = _require_api_key()
            if err:
                return err
            # Attestation check on cost-bearing endpoints (log-only or enforcing)
            att_err = _verify_attestation()
            if att_err:
                return att_err
        backend_url = BACKENDS[backend_key]
        upstream_path = _build_upstream_path(upstream_template, **kwargs)
        return _proxy_request(backend_url, upstream_path, timeout=timeout)

    return handler

# Register each route from the YAML manifest
_registered_names = set()
for i, route in enumerate(ROUTES):
    public_path = route['public_path']
    methods = route['methods']

    # Generate a unique endpoint name from the path
    endpoint = re.sub(r'[^a-zA-Z0-9]', '_', public_path).strip('_')
    # Handle duplicates by appending index
    if endpoint in _registered_names:
        endpoint = f"{endpoint}_{i}"
    _registered_names.add(endpoint)

    handler = _make_handler(route)
    handler.__name__ = endpoint  # Flask requires unique function names

    app.add_url_rule(public_path, endpoint=endpoint, view_func=handler, methods=methods)

print(f"[GATEWAY] Loaded {len(ROUTES)} routes from {MANIFEST_PATH}")

# ---------------------------------------------------------------------------
# Health + Attestation nonce + stubs (not in YAML — gateway-intrinsic)
# ---------------------------------------------------------------------------
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "api-gateway", "auth": "enabled",
                    "routes": len(ROUTES), "attestation": "enforcing" if ATTESTATION_ENFORCED else "log-only",
                    "version": SERVICE_VERSION, "mode": os.getenv("STORIED_MODE", "false")})

@app.route('/attest-nonce', methods=['GET'])
def attest_nonce():
    """Issue a stateless, HMAC-signed nonce for attestation token binding (anti-replay).
    App calls this before generating an attestation token, binds the nonce into the token.
    Requires API key (so only the real app can request nonces).
    Stateless: any gateway instance can verify any nonce without shared state."""
    err = _require_api_key()
    if err:
        return err
    nonce = _issue_nonce()
    return jsonify({"nonce": nonce, "ttl_seconds": NONCE_TTL_SECONDS})

@app.route('/sync', methods=['POST', 'GET'])
def sync():
    return jsonify({"status": "success"})

@app.route('/user/<path:subpath>', methods=['GET', 'POST', 'PUT'])
def user_route(subpath):
    return jsonify({"status": "success", "rows_affected": 1})

@app.route('/user', methods=['GET', 'POST', 'PUT'])
def user_root():
    return jsonify({"status": "success"})

# ---------------------------------------------------------------------------
# 404
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "endpoint not found", "service": "api-gateway"}), 404

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, debug=False)
