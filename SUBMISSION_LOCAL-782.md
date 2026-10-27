# SUBMISSION — LOCAL-782: Redact sensitive request headers from service logs

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-782-redact-header-logs`
**Base:** `subscribed` @ `c982ebe0` (`git merge-base --is-ancestor c982ebe0 HEAD` → exit 0)

## Problem

`map-delivery-subscribed` (and the other services sharing its `@app.before_request`
logger) printed the full request header mapping to Cloud Logging on every request:

```python
print(f"Headers: {dict(request.headers)}")
```

That line shipped the client's `X-Api-Key` into logs verbatim
(`map_delivery_service.py:87`, `map_delivery/app.py:231`), along with any
`Authorization`, `Cookie`, `X-Goog-*` auth, and purchase/receipt tokens a caller sent.
The key ships inside the app anyway, but it must not sit in logs.

## Fix

### 1. Shared helper — `safe_headers.py` (repo root, stdlib-only)

`safe_headers(headers)` returns a plain dict safe to print. A header is redacted when
its name is one of `X-Api-Key`, `Authorization`, `Proxy-Authorization`, `Cookie`,
`Set-Cookie`, `X-Attestation-Token`, `X-App-Attestation`, **or** its name contains
(case-insensitive) any of `token`, `secret`, `key`, `x-goog-`, `password`, `auth`.
Redacted values show only the last 4 characters as `…abcd` (values ≤ 4 chars are hidden
entirely). Non-sensitive headers pass through unchanged.

The module is the companion to `build_manifest.py`, which every service image already
copies, so `COPY *.py` images (`Dockerfile.cloudrun`, `Dockerfile.generator`) pick it up
automatically. `Dockerfile.orchestrator` copies sources one-by-one, so an explicit
`COPY safe_headers.py /app/` line was added.

### 2. Call sites replaced (file:line after the fix)

| Service | Before | After |
|---|---|---|
| `map_delivery_service.py` | `:87` `dict(request.headers)` | `:99` `safe_headers(request.headers)` |
| `map_delivery/app.py` | `:231` `dict(request.headers)` | `:248` `safe_headers(request.headers)` |
| `coordinates_fromAI/app.py` | `:57` `dict(request.headers)` | `:69` `safe_headers(request.headers)` |
| `tour_orchestrator_service.py` | `:2599` `dict(request.headers)` | `:2611` `safe_headers(request.headers)` |

`map_delivery/` and `coordinates_fromAI/` build from their own subdirectory context
(`docker-compose-master.yml`: `context: ./map_delivery`, `context: ./coordinates_fromAI`),
which does not include the repo-root module. Per the task's allowance, each of those two
files carries a 5-line inline equivalent (import the root module if present, else define
it inline) — the inline copy is what runs in those images. Verified identical output to the
shared helper. Single-header reads like `request.headers.get('User-Agent')` were left
untouched; they do not leak.

Raw request **bodies**: the only body logs in shipped services are on
`tour_orchestrator_service.py`'s `/generate-complete-tour` (a tour-generation payload, not
a purchase/receipt) and in one-off deploy helper scripts (`add_*.py`, `enhance_*.py`,
`improve_*.py`) that no Dockerfile ships. No purchase_token/receipt body log exists in a
shipped service, so no body redaction was needed.

## Tests (red first)

`test_local782_header_redaction.py` (repo root):

- **Unit (5):** `safe_headers` redacts `X-Api-Key`/`Authorization`/`Cookie`/`Set-Cookie`/
  `X-Goog-*`/`*token`/`*secret` to `…abcd`, preserves `User-Agent`/`Content-Type`/`Accept`/
  `X-Request-ID`, accepts a Flask `(k, v)` pair-iterable, and fully hides a ≤4-char secret.
- **AST guard (4, parametrized over the 4 services):** parses each service and fails if a
  `print`/logging call dumps the **whole** header mapping (`dict(request.headers)` or a bare
  `request.headers`) without wrapping it in `safe_headers`. The guard deliberately does
  **not** flag `request.headers.get(...)`/`request.headers[...]` single-header reads.

Red-first evidence: before the call-site edits, the 4 guard cases failed naming exactly
`map_delivery_service.py:87`, `map_delivery/app.py:231`, `tour_orchestrator_service.py:2599`,
`coordinates_fromAI/app.py:57`; the 5 unit tests passed. After the fix: **9 passed**.

## Live test (own container, budget $0)

Built `./map_delivery` from this worktree → `map-delivery-local782:latest`; ran as
`map-delivery-local782`, host port **5782 → 5005** (never `-p audioura`). Curled `/health`
with secret headers:

```
curl -H "X-Api-Key: sk-live-SUPERSECRET-ABCD1234" \
     -H "Authorization: Bearer ey.jwt.tokenZZZZ" \
     -H "Cookie: session=topsecretvalue9999" \
     -H "X-Goog-Iap-Jwt-Assertion: googjwtWXYZ" \
     http://localhost:5782/health          → HTTP 200
```

Resulting log line:

```
Headers: {'Host': 'localhost:5782', 'User-Agent': 'curl/8.7.1', 'Accept': '*/*',
          'X-Api-Key': '…1234', 'Authorization': '…ZZZZ', 'Cookie': '…9999',
          'X-Goog-Iap-Jwt-Assertion': '…WXYZ'}
```

A grep of the full container log for `SUPERSECRET|tokenZZZZ|topsecretvalue|sk-live` returned
nothing. Container and image were torn down; `audioura-map-delivery-1` was never touched.

## Storied (D720)

Local `storied` has the identical offending lines (`map_delivery_service.py`,
`map_delivery/app.py`, `coordinates_fromAI/app.py`, `tour_orchestrator_service.py`). See the
cherry-pick note appended below for cleanliness.

### Cherry-pick result onto `storied` — NOT fully clean (one trivial conflict)

Tested by cherry-picking `0481d8d3` (no-commit) onto a throwaway branch off local `storied`
(`storied` itself was never modified; the test branch was reset and deleted afterward).

- **7 of 8 files auto-merged cleanly**, including the redaction fix on **all four**
  services — every `dict(request.headers)` → `safe_headers(request.headers)` call-site swap
  applied with zero conflicts (`map_delivery_service.py`, `coordinates_fromAI/app.py`,
  `tour_orchestrator_service.py` had 0 conflicts; `map_delivery/app.py`'s call-site swap also
  applied cleanly).
- **One conflict, in `map_delivery/app.py`, confined to the import block only.** On
  `subscribed` the helper import was anchored right after `import personal_match`
  (a subscribed-only LOCAL-689 line). `storied` has no `import personal_match`, so that anchor
  is absent and the inserted block has nowhere to attach — a pure context mismatch, not a
  semantic conflict. The sensitive-line fix is unaffected.

**Resolution on storied (mechanical):** place the `safe_headers` import/inline-fallback block
near the top of `map_delivery/app.py` (e.g. just after the `from flask import ...` line)
instead of after `import personal_match`. Everything else cherry-picks as-is. So the change
applies to `storied` with a single, trivial, well-understood manual placement of the import
block; no logic changes are required.

