# UNWIRED AUDIT — LOCAL-108

**Branch:** `kiro/local108-unwired-audit`  
**Date:** 2026-08-01  
**Agent:** Mac Mini Kiro  
**Method:** Static analysis — AST parsing, grep, import graph construction  

---

## Category 1: `register_*_routes` / `init_*` / `setup_*` Functions

Every function matching these patterns in the repo, with call-site verification.

| Symbol | File | Called by a running service? | Verdict |
|--------|------|------------------------------|---------|
| `register_preference_routes(app)` | `swipe_preference_service.py:302` | **NO** — sole reference is its own `def` line. Zero call sites. | **UNWIRED** |
| `register_routes(app, get_db)` | `user-tracking/routes.py:4` | Called by `app_with_routes.py` only — NOT the Docker entry point (`user-tracking/app.py`) | **DEAD** |
| `init_database()` | `custom_audio_service.py:35` | Called only in its own `__main__` block; `custom_audio_service.py` is never deployed | **DEAD** |
| `init_db()` | `user-tracking/app_fixed_final.py:27` | Called in its own `__main__`; NOT the Docker entry point | **DEAD** |
| `setup_logging()` | `enhanced_logging.py:11` | Zero importers of this module | **DEAD** |
| `setup_worktree(...)` | `kiro_dispatcher.py:331` | Called internally by the dispatcher (a dev tool) | **INTENTIONAL** (dev tooling) |
| `setup_logging()` | `tests/test_boston_globe_auth_enhanced.py:12` | Test-internal | **INTENTIONAL** (test) |
| `setup_db(...)` | `tests/test_news_quota_integration.py:114` | Test-internal | **INTENTIONAL** (test) |
| `setup_db(...)` | `tests/test_tour_quota_integration.py:90` | Test-internal | **INTENTIONAL** (test) |
| `setup_driver()` | `browser_automation.py:21`, `tests/test_flutter_web_demo.py:22` | Class method, called by instances | **INTENTIONAL** |

**Count:** 10 total, **1 UNWIRED**, 4 DEAD, 5 INTENTIONAL.

### UNWIRED detail — `register_preference_routes`

**Why it should be called:** This registers `POST /user/<user_id>/stop-feedback`
and `GET /user/<user_id>/preferences` — the Subscribed swipe-to-rate endpoints
from LOCAL-101/LOCAL-105. Without registration, every swipe from every user
returns 404. The mobile app sends these requests; they silently fail.

**What breaks:** User taste signal is lost. The offline retry queue (LOCAL-105)
retries 10 times per failed swipe, then discards the signal permanently. The
persona engine never receives preference data from the field.

**Proposed task:** Wire `register_preference_routes(app)` call in
`generate_tour_text_service.py` or `tour_orchestrator_service.py` (whichever
hosts the user-facing API for the mobile app). Verify with a live
`POST /user/<id>/stop-feedback` → 200 test.

---

## Category 2: Modules With No Importer

### Method

1. Walked all 530 `.py` files (excluding `audio_tour_app/`, `.git/`, `__pycache__/`).
2. Used AST to extract all `import X` / `from X import ...` statements.
3. Built a map: module_stem → set of files that import it.
4. Cross-referenced against known entry points: Docker CMD targets from
   `docker-compose.yml`, `docker-compose-master.yml`, and all `Dockerfile.*` files.
5. **Exclusions (and why):**
   - Docker CMD targets (28 files) — entry points by definition.
   - `tests/` directory — test runners invoke these, not import graph.
   - `tools/` directory — CLI tools, run directly.
   - Files prefixed `run_*`, `test_*` — acceptance/pilot scripts, not library code.
   - Files in `scripts/`, `migrations/` — one-shot operations.
   - Files prefixed with verbs typical of one-off scripts: `check_*`, `decrypt_*`,
     `verify_*`, `analyze_*`, `cleanup_*`, etc.

**Risk of exclusion hiding unwired code:** A module named `run_something.py` that
is actually a daemon nobody starts would be missed. I verified no `run_*` file
appears in any Dockerfile CMD or docker-compose command.

### Results — Unwired production modules (not scripts, not entry points)

| Module | Key functions | Verdict | Justification |
|--------|--------------|---------|---------------|
| `persona_endpoints.py` | `persona_bp` Blueprint with `POST/GET /user/persona` | **UNWIRED** | Blueprint never registered. Mobile persona UI sends these requests to 404. |
| `referral_endpoints.py` | `referral_bp` Blueprint with `POST /referral/create`, `POST /referral/redeem` | **UNWIRED** | Blueprint never registered. Referral feature has no live endpoint. |
| `sharing_endpoints.py` | `sharing_bp` Blueprint with `POST /tour/share`, `GET /tour/<id>` | **UNWIRED** | Blueprint never registered. (Note: `tour_sharing.py` IS reachable via `deeplink_resolution_endpoint` in tour-id-resolution service for the GET path. The POST path — creating shares — is dead.) |
| `referral_engine.py` | `generate_referral_code()`, `store_referral()`, `record_referral_redemption()` | **UNWIRED** | Only importer is `referral_endpoints.py` which is itself never registered. Entire referral chain is dead. |
| `content_validation.py` | `validate_newsletter_url()`, `detect_garbage_content()` | **DEAD** | Zero importers. Newsletter processor does not use it. |
| `pdf_processor.py` | `extract_pdf_text()`, `should_attempt_pdf_processing()` | **DEAD** | Zero importers. PDF newsletters not handled. |
| `service_config.py` | `get_db_connection()`, URL constants for all services | **DEAD** | Zero importers. Every service has its own inline config. |
| `spine_quality_scorer.py` | `score_spine()` | **UNWIRED** | Scores spine quality (0–4) for retry logic. Zero importers. Spine generator produces output with no quality gate. |
| `tour_hook_generator.py` | `generate_tour_hook_audio()` | **UNWIRED** | Expands spine `tour_hook` into spoken intro. Zero importers. Spine generates a hook field that nothing consumes for TTS. |
| `custom_audio_service.py` | Full Flask service for user audio uploads | **DEAD** | No Dockerfile runs it. Self-contained `__main__` service never deployed. |
| `news_search_service.py` | `NewsSearchService` class | **DEAD** | Zero importers. Docker uses `simple_news_search_service.py` instead. |
| `voice_control_service.py` | Voice command processing Flask service | **DEAD** | Zero importers. Docker uses `voice_control/app.py` instead. |
| `coordinates_fromai_service.py` | Coordinates Flask service (port 5006) | **DEAD** | Zero importers. Docker uses `coordinates_fromAI/app.py`. |
| `store_audio_tours.py` | `store_audio_tour()` standalone | **DEAD** | Function is defined inline in `tour_orchestrator_service.py:333`. This file is a dead duplicate. |
| `tour_delivery_service.py` | Tours-near-location service | **DEAD** | Zero importers. Function moved to `map_delivery/app.py`. |

**Count:** 15 notable findings. **5 UNWIRED**, 10 DEAD.

### UNWIRED details

**`persona_endpoints.py` — Blueprint never registered:**  
The mobile app calls `POST /user/persona` after onboarding (LOCAL-45/S45).
`persona_preference_store.py` IS imported by `generate_tour_text_service.py`
to READ persona, but the WRITE endpoint (which the mobile app hits) returns 404.
Users can never SET their persona from the app.

**`referral_endpoints.py` — Blueprint never registered:**  
`POST /referral/create` and `POST /referral/redeem` have no live path.
`referral_engine.py` implements the logic correctly. The mobile app has
referral UI (LOCAL-52). All requests 404.

**`sharing_endpoints.py` — POST path dead:**  
`POST /tour/share` returns 404 (blueprint not registered). The GET path
(`GET /tour/<id>`) works only through `deeplink_resolution_endpoint.py` in the
tour-id-resolution service — but you cannot CREATE a share because the POST
endpoint is not live. Share button in app is non-functional for creating new
shares.

**`spine_quality_scorer.py` — no quality gate on spine generation:**  
`spine_generator.py` produces spine JSON. `spine_quality_scorer.py` scores it
on 4 criteria (climax position, beat variety, callback validity, closing
substance). Nothing calls the scorer. A low-quality spine passes through
unchecked.

**`tour_hook_generator.py` — hook field unused:**  
Spine JSON includes a `tour_hook` field. `tour_hook_generator.py` was written
to expand it into a spoken TTS introduction. Nothing calls it. The hook exists
in the data but never reaches the audio output.

---

## Category 3: Public Functions With Zero Call Sites

Scope: `generate_tour_text.py`, `tour_orchestrator_service.py`, `cost_meter.py`,
`entitlements.py`, and the Subscribed endpoint modules.

Flask route handlers are excluded (called by the framework). Internal-only calls
(same file) are excluded.

| Function | File | Verdict | Justification |
|----------|------|---------|---------------|
| `validate_poi_knowledge()` | `generate_tour_text.py:576` | **DEAD** | Zero call sites anywhere (internal or external). Was superseded by spine-based generation. |
| `call_coordinates_service()` | `tour_orchestrator_service.py:1167` | **DEAD** | Zero call sites. Orchestrator calls coordinates via `get_coordinates_direct()` in the worker or directly via HTTP in `orchestrate_tour_async()`. This function is a stale predecessor. |
| `get_operation_cost()` | `cost_meter.py:168` | **UNWIRED** | Retrieves cost ledger entries for a job. `record_operation()` (the write side) is called by both services. The read side (for monitoring/billing display) has no caller. |
| `register_preference_routes()` | `swipe_preference_service.py:302` | **UNWIRED** | (Repeated from Cat 1 for completeness) |
| `set_user_persona()` | `persona_endpoints.py` | **UNWIRED** | Route handler on unregistered blueprint. |
| `get_user_persona()` | `persona_endpoints.py` | **UNWIRED** | Route handler on unregistered blueprint. |
| `create_referral()` | `referral_endpoints.py` | **UNWIRED** | Route handler on unregistered blueprint. |
| `redeem_referral()` | `referral_endpoints.py` | **UNWIRED** | Route handler on unregistered blueprint. |
| `share_tour()` | `sharing_endpoints.py` | **UNWIRED** | Route handler on unregistered blueprint. |
| `score_spine()` | `spine_quality_scorer.py` | **UNWIRED** | (Repeated from Cat 2) |
| `generate_tour_hook_audio()` | `tour_hook_generator.py` | **UNWIRED** | (Repeated from Cat 2) |

**Count:** 11 findings. **9 UNWIRED**, 2 DEAD.

### UNWIRED detail — `get_operation_cost`

**Why it should be called:** The cost metering system (LOCAL-60) writes cost
records via `record_operation()`. `get_operation_cost(job_id)` is the
corresponding read function — meant to power the "tour cost" display in the
app and the monitoring dashboard. Without it, cost data is write-only: it
accumulates in `cost_ledger` but nothing ever reads it back.

**What breaks:** No tour-level cost visibility. The `/health` endpoint shows
aggregate ceiling stats but no per-tour cost breakdown is exposed to the app
or to monitoring.

**Proposed task:** Wire `get_operation_cost()` into a route (e.g.,
`GET /cost/<job_id>`) or call it from the `/status/<job_id>` response so the
app can display cost information.

---

## Category 4: `except ImportError` That Continues Silently

Total `except ImportError` blocks in non-Flutter Python files: **45**.

### Classification

| Handling | Count |
|----------|-------|
| Logs at ERROR level (names the missing symbol) | 21 |
| Prints warning/info (downgraded but visible) | 18 |
| **Silent `pass` or empty `{}` — no log at any level** | **6** |

### Silent blocks (no ERROR-level log, no warning, no print)

| File:Line | What is swallowed | Risk | Verdict |
|-----------|-------------------|------|---------|
| `content_qa_runner.py:768` | `practical_facts_gate.extract_practical_claims` | Low — info-only in QA tool, not production pipeline | **DEAD** (QA path only; production import at `generate_tour_text.py:6599` logs ERROR correctly) |
| `generate_tour_text_service.py:431` | `cost_ceiling_monitor.get_ceiling_stats` in health check | Medium — health endpoint silently omits ceiling data | **UNWIRED** |
| `tour_orchestrator_service.py:1215` | `cost_ceiling_monitor.get_ceiling_stats` in health check | Medium — same pattern | **UNWIRED** |
| `tests/test_tour_quota_integration.py:47` | `dotenv` optional | None — test convenience | **INTENTIONAL** |
| `tests/test_news_quota_integration.py:62` | `dotenv` optional | None — test convenience | **INTENTIONAL** |
| `tests/test_newsletter_cloud.py:40` | `dotenv` optional | None — test convenience | **INTENTIONAL** |

**Count:** 6 silent blocks. **2 UNWIRED** (should log ERROR), 1 DEAD, 3 INTENTIONAL.

### UNWIRED details — silent `cost_ceiling_monitor` fallbacks

**`generate_tour_text_service.py:431` and `tour_orchestrator_service.py:1215`:**

Both health endpoints import `cost_ceiling_monitor.get_ceiling_stats()` inside
a `try/except ImportError` block that silently returns `{}`. If the module
fails to import (e.g., Docker image drift, missing file, broken dependency),
the health check returns 200 with no ceiling data. **There is no log line.**
This is exactly the corpus-mining pattern: a swallowed ImportError that
renders a feature invisible.

The import at generation time (`generate_tour_text_service.py:201`) correctly
logs at ERROR. But the health-check fallbacks do not.

**What breaks:** If `cost_ceiling_monitor.py` vanishes from an image or has a
syntax error, both health endpoints silently report healthy with no cost data.
Monitoring that reads `/health` sees no error. The cost ceiling becomes
unenforceable without any alert.

**Proposed task:** Add `logging.error(...)` naming the missing module in both
fallback blocks. One-line fix each, but the pattern is the exact one that hid
corpus mining for two days.

### Additional WARNING-level blocks worth noting

| File:Line | What is swallowed | Note |
|-----------|-------------------|------|
| `api-gateway/main.py:103` | `attestation_verifier` | Prints warning + returns None. Attestation silently disabled. Since `ATTESTATION_MODE=log_only` currently, impact is nil, but switching to enforce mode without this module present would silently fail open. |
| `generate_tour_text.py:4824` | `theme_thread_discoverer` | Prints info only. Module exists in image (`*.py` glob copy), so this should never fire. If it fires, it means the file was removed without anyone noticing. Should be ERROR level. |
| `generate_tour_text_service.py:419` | `manifest_check` | Returns `manifest_ok: False` with a drift message. Visible but not ERROR-level. |

---

## Summary

| Category | UNWIRED | DEAD | INTENTIONAL | Total |
|----------|---------|------|-------------|-------|
| 1. register/init/setup | 1 | 4 | 5 | 10 |
| 2. Orphan modules | 5 | 10 | — | 15 |
| 3. Dead public functions | 9 | 2 | — | 11 |
| 4. Silent ImportError | 2 | 1 | 3 | 6 |
| **Totals (deduplicated)** | **8** | **13** | **8** | — |

*Deduplicated UNWIRED count removes items that appear in multiple categories.*

### The 8 UNWIRED findings (features Michael thinks he has and does not)

1. **`register_preference_routes`** — swipe-to-rate 404s silently
2. **`persona_bp` Blueprint** — POST /user/persona 404s
3. **`referral_bp` Blueprint** — referral create/redeem 404s
4. **`sharing_bp` Blueprint (POST path)** — share creation 404s
5. **`spine_quality_scorer`** — no spine quality gate
6. **`tour_hook_generator`** — hook never becomes audio
7. **`get_operation_cost()`** — cost data is write-only
8. **Silent `except ImportError` on health checks** — cost ceiling can vanish unnoticed

---

## What This Method Cannot Detect

1. **Dynamic dispatch / `getattr` / string-based imports** — a function called
   via `getattr(module, func_name)()` appears to have zero static call sites.
   I found no evidence of this pattern in the core services but cannot rule it
   out for plugin-like structures.

2. **Flask decorator registration via `app.register_blueprint()` in code not
   in this repo** — if there is a separate deployment script that registers
   blueprints at container start, it would not appear here. I checked all
   Dockerfiles and docker-compose configs; none do this.

3. **Calls from the Flutter app to endpoints** — I verified server-side routes
   only. If the mobile app calls a URL that happens to match a route defined in
   a registered service, that route is live. But if the mobile app calls a URL
   that only a dead Blueprint defines, the call fails silently.

4. **Template references** — Jinja or other template engines could call
   functions. I found no template-based invocation of any flagged function.

5. **Cloud Run / GCloud production deployment** — this audit covers the local
   Docker stack and `docker-compose-master.yml`. The GCloud production
   deployment (`main` branch) may wire things differently. Per the constraint,
   `main` is not touched.

6. **Import-time side effects** — a module that registers itself via class
   decorators at import time would not show up in an explicit call-site search.
   The codebase uses Flask Blueprints for this pattern, and I checked all
   Blueprint registrations explicitly.

---

## Proposed Tasks (one per UNWIRED finding)

| # | Finding | Proposed task |
|---|---------|---------------|
| 1 | `register_preference_routes` | Register in service entry point + live 200 test |
| 2 | `persona_bp` unregistered | `app.register_blueprint(persona_bp)` in `generate_tour_text_service.py` + test |
| 3 | `referral_bp` unregistered | `app.register_blueprint(referral_bp)` in target service + test |
| 4 | `sharing_bp` POST path dead | `app.register_blueprint(sharing_bp)` — decide which service hosts it |
| 5 | `spine_quality_scorer` unused | Call `score_spine()` after `generate_spine()`, retry or log on score < 2 |
| 6 | `tour_hook_generator` unused | Call `generate_tour_hook_audio()` in TTS pipeline after spine |
| 7 | `get_operation_cost` no reader | Wire into `/status/<job_id>` response or new `/cost/<job_id>` route |
| 8 | Silent health ImportError | Add `logging.error(...)` to 2 fallback blocks (one-line each) |
