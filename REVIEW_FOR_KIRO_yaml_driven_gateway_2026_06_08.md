# REVIEW_FOR_KIRO — YAML-Driven Gateway (2026-06-08)

**Context:** Per Claude's Section 4 directive and Sir Michael's requirement — eliminate the hand-maintained route list that causes cloud/local drift. The gateway now loads routes from a declarative YAML manifest.

---

## Architecture Change

### Before (hand-maintained Python routes)
```python
# main.py — 200+ lines of @app.route decorators, one per endpoint
# Adding a route = editing Python = drift risk
@app.route('/generate-news', methods=['POST'])
def generate_news():
    auth_err = require_api_key()
    ...
```

### After (YAML-driven, zero-touch Python)
```yaml
# gateway_routes.yaml — one block per endpoint, no Python changes
- public_path: /generate-news
  backend: news-orchestrator
  upstream: /generate-news
  methods: [POST]
  auth: api_key
  timeout: 600
```

```python
# main.py — generic loader, registers routes from YAML at startup
for route in ROUTES:
    handler = _make_handler(route)
    app.add_url_rule(route['public_path'], ...)
```

**Adding an endpoint = adding a YAML block. No Python. No code review for routing.**

---

## Files

| File | Purpose |
|------|---------|
| `api-gateway/gateway_routes.yaml` | Single source of truth for all exposed routes |
| `api-gateway/main.py` | Generic loader + proxy core (no route-specific code) |
| `api-gateway/Dockerfile` | Added `pyyaml` dependency, copies both files |

---

## How the YAML manifest works

```yaml
backends:
  news-orchestrator: ${NEWS_ORCHESTRATOR_URL:-https://news-orchestrator-60899077572.us-central1.run.app}

routes:
  - public_path: /generate-news       # What the app calls
    backend: news-orchestrator         # Which backend to proxy to
    upstream: /generate-news           # What path the backend sees
    methods: [POST]                    # Allowed HTTP methods
    auth: api_key                      # 'api_key' or 'none'
    timeout: 600                       # Seconds (default 60)

internal_only:
  - backend: newsletter
    path: /decrypt_credentials
    reason: "Handles raw credentials; service-to-service only"
```

- `${ENV_VAR:-default}` syntax resolved at startup from environment
- `internal_only` section documents deliberate non-exposure (for parity audit)
- `auth: api_key` → enforces X-API-Key header (fail-closed if key not configured)
- `<var>` in `public_path` → Flask URL variable, forwarded to `{var}` in `upstream`

---

## main.py is now route-agnostic

The Python code does exactly three things:
1. Load and parse `gateway_routes.yaml` (resolve env vars)
2. For each route entry, register a Flask handler that: checks auth → builds upstream path → proxies request
3. Serve health/sync/user stubs (gateway-intrinsic, not service routes)

Total: ~160 lines. No service-specific logic. Never needs editing for new endpoints.

---

## All 19 routes loaded (confirmed)

`/health` returns `{"routes": 19}` — matches the count in the YAML.

Breakdown:
- Map delivery: 4 routes
- Tour orchestrator: 5 routes
- Translation: 1 route
- News orchestrator: 4 routes
- Newsletter processor: 5 routes

Plus gateway-intrinsic: `/health`, `/sync`, `/user`, `/user/<path>` (not in YAML, hardcoded as stubs).

---

## Deployment

| Service | Revision |
|---------|----------|
| `api-gateway` | `api-gateway-00011-j2s` |

Verified: `https://api.audioura.com/health` → `{"status": "healthy", "routes": 19}`

---

## How this prevents drift

1. **No Python to edit** — new endpoint = new YAML block. The Python never changes for routing.
2. **`internal_only` section** — deliberately hidden endpoints are documented, not accidentally missing.
3. **Future: parity test** — a CI script can parse service `@app.route` decorators and diff against the YAML. Any service endpoint not in `routes` or `internal_only` fails the build. (Not implemented this session — the YAML makes it trivial to add.)

---

## `py_compile` verification

```
python -m py_compile api-gateway/main.py → exit 0 (clean)
```

---

## Risk

- **YAML parsing at startup:** If `gateway_routes.yaml` is malformed, the gateway won't start (fail-fast). Cloud Run will show the previous revision until the fix deploys. This is the correct behavior — better to fail visibly than silently serve a broken route set.
- **`pyyaml` dependency:** Well-established, actively maintained library. Pinning not critical for the gateway (it's a thin proxy, not a long-lived service with complex deps).
- **Existing routes:** All 19 routes are identical to what was hand-coded in the previous `main.py`. No behavioral change — same paths, same methods, same auth, same backends.
