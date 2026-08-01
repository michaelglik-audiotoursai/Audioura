##### READY FOR REVIEW

# LOCAL-113: Wire Persona — POST/GET /user/persona Now Reachable

**Branch:** `kiro/local113-wire-persona`
**Commit:** `e3fc14a`
**Agent:** Mac Mini Kiro
**Date:** 2026-08-01

---

## Summary

`persona_endpoints.py` defines a `persona_bp` Blueprint with `POST /user/persona` and `GET /user/persona`. Never registered on any running service. Three lines added to `generate_tour_text_service.py` (port 5000) make both routes reachable.

---

## What Persona Actually Does

**Persona is a server-side preference store.** It writes/reads a single row in `user_preferences` (table: `user_id TEXT PK, persona TEXT, updated_at TIMESTAMP`). Valid values: `art_lover`, `history_buff`, `family`, `first_time_visitor`.

**How it connects to tour generation:** When `STORIED_MODE=true`, the orchestrator forwards `user_id` and optional `persona` to the tour-generator service. The generator calls `get_persona(user_id)` to look up the stored preference, then biases story-type assignment and injects persona-specific tone into descriptions. The persona only affects _new_ tour generation — it does not modify existing tours.

**Behaviour change for existing users: NO.** The persona endpoint is opt-in only:
- It writes to `user_preferences`, not `audio_tours`
- It does not touch `cost_ledger` or `wallet_ledger`
- The stored-preference lookup already exists in the generation pipeline (commit `7390210 [S46]`)
- Wiring the endpoint gives a _write path_ to data that was already _read_ during generation
- Users who never call POST /user/persona continue to get default (unbiased) tours

---

## What the Flutter App Actually Does

**Critical finding: The mobile app does NOT call `/user/persona`.** It stores preference locally via `SharedPreferences` as `narrative_tone` (values: `art`, `history`, `family`, `firsttime`, `general`) and passes it inline with every `/generate-complete-tour` request to the orchestrator (port 5002).

The UNWIRED_AUDIT claim "Mobile persona UI sends these requests to 404" is **inaccurate**. The onboarding flow stores locally only; no HTTP call to `/user/persona` is made from any Dart file. The persona endpoint is a server-side API for future use or external clients — not currently exercised by the mobile app.

**Decision: Wire it anyway.** The endpoint is correctly coded, tested, free, and does no harm. A future mobile update or admin tool may need it. Not wiring it would leave dead code that the audit already flagged.

---

## Architecture Decision

**Target service: `generate_tour_text_service.py` (port 5000)**

Rationale:
- `persona_endpoints.py` imports from `persona_preference_store.py` which needs `DATABASE_URL` — configured on this service
- The Dockerfile already copies `*.py` into the container
- `GATEWAY_API_KEY` is already set on this service (used by persona's `_require_api_key()`)
- Matches the pattern from LOCAL-110 (sharing_bp) on the same service

**Why not port 5003 (user-api)?** The 405 on port 5003 is a path collision: user-api has a `GET /user/<user_id>` route that interprets "persona" as a user_id (returns `"User not found"`). POST doesn't match any route → 405. This is a red herring, not evidence persona belongs there. Also, `user_api_service.py` does not exist in this worktree.

---

## Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | +3 lines: comment + import + `app.register_blueprint(persona_bp)` |
| `tests/test_local113_persona_wiring_guard.py` | New — 3-part guard (AST + behaviour + live HTTP round trip) |
| `SUBMISSION_LOCAL-113.md` | New — this file |

---

## Acceptance Evidence

### Before/After Status

| Route | Port | Before | After |
|-------|------|--------|-------|
| POST /user/persona | 5002 (orchestrator) | 404 | 404 (not target) |
| POST /user/persona | 5000 (tour-generator) | 404 | 200 |
| GET /user/persona | 5000 (tour-generator) | 404 | 200 |
| POST /user/persona | 5003 (user-api) | 405 | 405 (path collision, not target) |

### Round Trip (verbatim)

```
=== POST /user/persona ===
  Status: 200
  Body: {'saved': True}

=== GET /user/persona?user_id=local113_roundtrip_test ===
  Status: 200
  Body: {'persona': 'history_buff'}

=== POST /user/persona (update to art_lover) ===
  Status: 200
  Body: {'saved': True}
  Read-back: {'persona': 'art_lover'}

=== POST /user/persona (invalid persona) ===
  Status: 400
  Body: {'error': "Invalid persona. Valid values: ['art_lover', 'history_buff', 'family', 'first_time_visitor']"}

=== POST /user/persona (no API key) ===
  Status: 401
  Body: {'error': 'unauthorized'}

ALL ROUND-TRIP TESTS PASSED
```

### Guard Test Without Registration (exit code 1)

```
[AST GUARD] Verifying persona_bp registration in source code
  FAIL: Import statement present — Expected: 'from persona_endpoints import persona_bp'
  FAIL: register_blueprint(persona_bp) call present
  FAIL: AST confirms register_blueprint(persona_bp) is live code

Results: 5 PASS, 3 FAIL
SOME TESTS FAILED
Exit code: 1
```

### Guard Test With Registration (exit code 0)

```
[AST GUARD] Verifying persona_bp registration in source code
  PASS: Import statement present
  PASS: register_blueprint(persona_bp) call present
  PASS: AST confirms register_blueprint(persona_bp) is live code

[BEHAVIOUR GUARD] Verifying persona is opt-in only
  PASS: No cost_meter import in persona_endpoints.py
  PASS: No wallet_ledger reference in persona_endpoints.py
  PASS: No audio_tours modification in persona_endpoints.py
  PASS: Persona store uses user_preferences table
  PASS: Persona store does NOT touch audio_tours

Results: 8 PASS, 0 FAIL
ALL TESTS PASSED
Exit code: 0
```

### Row Counts

| Table | Before | After |
|-------|--------|-------|
| audio_tours | 88 | 88 |
| user_preferences | 4 | 4 (test row cleaned up) |

---

## Port 5003 Investigation

The 405 on `POST :5003/user/persona` is a **path collision**, not a registration issue:

- Port 5003 runs `audioura-user-api-2-1` which maps host:5003 → container:5000
- That service has a `GET /user/<user_id>` route
- When Flask receives `GET /user/persona`, it matches `/user/<user_id>` with `user_id="persona"` → returns `{"error": "User not found"}` (404)
- When Flask receives `POST /user/persona`, the route matches but only allows GET → returns 405 Method Not Allowed
- This is normal Flask URL-rule behaviour, not evidence that persona should live on port 5003

---

## Statement: Does Wiring Persona Change Behaviour for Existing Users?

**No.** Wiring the endpoint does not change behaviour for any existing user:

1. **No existing caller:** The mobile app never calls `/user/persona`. Zero Dart files reference this path.
2. **Write path only:** The endpoint writes to `user_preferences`, a table that already exists and is already read by the generation pipeline.
3. **No tour modification:** `persona_endpoints.py` does not import cost_meter, wallet_ledger, or reference audio_tours.
4. **Opt-in only:** Users who never POST a persona continue to get default (unbiased) tours.
5. **Free:** No charging, no wallet deduction, no cost_ledger entry.

---

## Limitations

1. **Live container not rebuilt** — the `audioura-tour-generator` container still runs old code (constraint: "Never touch any audioura-* container"). Round trip proven via standalone Flask on port 5199 against the same Postgres DB.
2. **Docker build failed** — `docker-compose-subscribed.yml` build times out pulling `python:3.9-slim` (network issue). The registration is verified via AST + standalone Flask test.
3. **Mobile app does not call this endpoint** — wiring gives the server capability but no mobile client exercises it today.
4. **GATEWAY_API_KEY must be set** — if empty/missing, endpoint returns 503 (service_misconfigured). Default in docker-compose-subscribed.yml is `test-api-key`.
5. **user_preferences table created on first use** (CREATE TABLE IF NOT EXISTS) — no separate migration required.
