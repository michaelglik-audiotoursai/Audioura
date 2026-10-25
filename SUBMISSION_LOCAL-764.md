# SUBMISSION_LOCAL-764.md — Subscribed cloud readiness

**Task:** LOCAL-764 — Subscribed gets its own API host in the app, a complete
gateway route manifest, the GCloud env manifest, and a migration dry run.
**Branch:** `LOCAL-764-subscribed-cloud-readiness`
**Base:** subscribed @ `1e740b0a` (`git merge-base --is-ancestor 1e740b0a HEAD` → exit 0, verified)
**code_sha:** branch tip of `LOCAL-764-subscribed-cloud-readiness` — run `git rev-parse HEAD` (the single commit on this branch above base `1e740b0a`).
**Rulings:** D712 (DECISIONS.md read, not edited), D708 (track `subscribed`), D594/D604 (local stack).
**No GCloud action taken** — nothing deployed, no `gcloud` run. This task produces
everything the GCloud_Storied (Windows) session needs to deploy without guessing.

---

## What LEAD asked for vs what shipped

| Deliverable | Status |
|---|---|
| A. App: Subscribed has its own cloud host | ✅ `endpoints.dart` → `https://subscribed-api.audioura.com`; Beta/Storied unchanged |
| B. Gateway route manifest for Subscribed | ✅ `gateway_routes.subscribed.yaml` (12 backends, every app call routed) + `GATEWAY_ROUTES_FILE` env; default unchanged |
| C. GCloud env manifest | ✅ `SUBSCRIBED_GCLOUD_ENV.md` (per service: image, port, every env var, secret names) |
| D. Migration dry run 010→050 | ✅ twice on a scratch DB; `SUBSCRIBED_MIGRATION_RUNBOOK.md` |
| Apple verify Production+Sandbox fallback | ✅ was a strict single-value pin; fixed with a red test |
| Live gateway smoke through the subscribed manifest | ✅ replayed read-only, budget $0 |

---

## A. App — Subscribed's own cloud host

`audio_tour_app/lib/config/endpoints.dart`:
- Added `_subscribedCloudBaseUrl = 'https://subscribed-api.audioura.com'`.
- `base()` cloud branch now delegates to a pure `baseForTrack(service, track)`
  seam: `subscribed → subscribed host`, `storied → storied host`,
  anything else → the Beta default (unchanged).
- **Beta and Storied behaviour is byte-for-byte unchanged** (Track B promise):
  the two existing host constants and the default path are untouched; only the
  new `subscribed` case was added.

**Red test (written first, failed, then passed):**
`audio_tour_app/test/endpoints_subscribed_host_test.dart` — 5 tests:
- subscribed track → subscribed host for **every** `Service` enum value;
- storied track → storied host (unchanged);
- beta track → beta host (unchanged);
- unknown/empty track → beta host (unchanged);
- the three hosts are distinct.
Initially RED (`Member not found: 'Endpoints.baseForTrack'`), GREEN after the
change (5/5).

## B. Gateway route manifest

`api-gateway/gateway_routes.subscribed.yaml` (NEW) — same format as the
Beta/Storied manifest, routes **every** call the Subscribed app makes:

- **12 backends** (the `-subscribed` services), each an env placeholder
  `${…_URL:-default}`: map-delivery, orchestrator, user-api, translation,
  news-orchestrator, newsletter, treats, tour-editing, tour-id-resolution,
  generator, voice, custom-audio.
- **Auth:** every app-facing route is `api_key` (the app always sends the key in
  cloud mode; the Beta manifest has no `none` routes either).
- **`internal_only`:** the 16 `/communities/admin/*` routes (ADMIN_API_KEY,
  which the app never carries) + newsletter `/decrypt_credentials` — documented
  as deliberately NOT publicly exposed.
- `/health` and `/sync` are left to the gateway's own intrinsic handlers (as on
  Beta), so no manifest route collides with them.

`api-gateway/main.py` (MODIFIED, minimal) — added `GATEWAY_ROUTES_FILE`:
unset = the previous default `gateway_routes.yaml` (byte-for-byte unchanged);
set = the chosen manifest (relative resolved beside `main.py`, absolute used
as-is). **The Beta/Storied manifest `gateway_routes.yaml` is NOT modified.**

**Route-coverage gate** `api-gateway/test_subscribed_route_coverage.py` (NEW):
scans `audio_tour_app/lib` for `Endpoints.*(Service.X, '<path>')` (newline
tolerant) plus the two news cloud paths the app builds
(`/news-status/<id>`, `/news-download/<id>`), normalises query suffixes and
`${…}`/`$var` interpolation, and fails if any app path lacks a matching route.
**Result: all 77 app server-call paths covered.** (It found two gaps during
development — `/tour/<id>/role` and the `/communities/<id>/tours` query suffix —
both fixed, which is the gate doing its job.)

**In-process load/auth gate** `api-gateway/test_subscribed_gateway_loads.py`
(NEW): builds the real gateway app from the subscribed manifest with Flask's
test client; proves it loads (12 backends), 9 representative subscribed-only
routes are fail-closed (no-key = 401, good-key ≠ 401), and the default (env
unset) still loads `gateway_routes.yaml` where `/wallet` is 404 (subscribed-only).

## C. GCloud env manifest

`SUBSCRIBED_GCLOUD_ENV.md` (NEW) — per service: image source + Dockerfile, port,
and **every** env var read (grepped `os.environ`/`os.getenv`), with the GCloud
value or the Secret Manager secret NAME (never a value). Covers the required
vars (`TOUR_TRACK`/`DELIVERY_TRACK_FILTER=subscribed`, `DAILY_PAID_LIMIT_USD`,
`METER_ROLE*`, `RECOVERY_CODE_PEPPER`, `ADMIN_API_KEY`, `GATEWAY_API_KEY`,
`IAP_VERIFY_MODE`, `APPLE_IAP_ENVIRONMENT`, `IAP_ALLOW_STUB_STORE` /
`ALLOW_UNAUTHENTICATED_ENTITLEMENTS` unset = fail-closed, Google Play SA secret
file, `TTS_ENGINE=polly` + AWS secrets, OpenAI/Gemini/Serper secret names,
`L2_SEAT_JOB_ENABLED`, L2 seat cap = 100 via `plans.l2.seat_cap`). Flags the
Mac-only settings GCloud must NOT copy (`/meterlogs`, `host.docker.internal`,
`postgres-2`, dev-default keys) and their replacements. Tour storage is
Cloudflare **R2** (not GCS) — documented, with the safe shared-bucket note.

**Apple verify — Production with Sandbox fallback (red test first).** The
StoreKit 2 JWS verifier pinned `environment` to a single value, so a Production
deployment would reject every TestFlight (Sandbox) purchase. Fixed:
`apple_jws_verifier.verify_signed_transaction(expected_environment=…)` now
accepts a single string (strict pin, unchanged) OR an iterable
(`Production`, `Sandbox`); the HTTP layer parses a comma-separated
`APPLE_IAP_ENVIRONMENT` into that list (3 call sites in `entitlements_api.py` /
`communities_api.py`). Red test `user-tracking/test_local764_apple_env_fallback.py`
(5/5): Sandbox and Production both accepted under `Production,Sandbox`, an
unrelated env still rejected, single-string still strict. LOCAL-598 suite
unchanged (17/17).

## D. Migration dry run 010 → 050

Applied every file **twice** on a throwaway Postgres 15 container
(`local764-pg`, port 55432, torn down after) — **never the shared Cloud SQL**.
Runner: `local764_tooling/migration_dry_run.sh`. Full report + apply runbook:
`SUBSCRIBED_MIGRATION_RUNBOOK.md`.

| Result | Detail |
|---|---|
| Clean + idempotent | 40/42 files apply cleanly both passes on a schema that has the storied base |
| Row counts Pass1 == Pass2 | users 3→3, audio_tours 1→1, plans 9→9, communities 0→0 (idempotent for data) |
| 033/034 | Need the consolidation base tables (`device_consolidation_history`, `recovery_codes`) that pre-010 self-heal creates — present on Cloud SQL. VERIFIED: with them pre-created, 033+034 apply cleanly TWICE. Base-schema prerequisite, not a defect. |
| 024 | NOT re-runnable after 026 (026 widens the tier CHECK to 1..41 and adds tiers 8..41; 024 re-narrows to 1..7 → violation). **Forward-only: apply each migration once.** |
| 041 | DROPs `uq_audio_tours_original_name`, adds `creator_user_id` + non-unique name+creator index. Lets Beta create duplicate names at the DB level; safe only with the D678 orchestrator code deployed (code-first). |
| 043 | adds `track`, replaces 041's index with `idx_audio_tours_name_creator_track`. Fixes bug 432 (cross-track name collapse). Code-first. |
| Mutating | 013/014 backfill `device_entitlement` (3× l2 + 1 admin); 038 DELETEs owner self-membership + grandfathers free members (no-op on clean data). No tour/user content deleted. |

Beta/Storied blast radius, backup command, exact forward-only apply order,
per-migration verification queries and rollback notes are in the runbook.

## Live gateway smoke (budget $0)

Ran `api-gateway` as a plain local process (NOT a container — the shared
`audioura-*` stack was untouched, no `-p` conflict) on port 8788 with
`GATEWAY_ROUTES_FILE=gateway_routes.subscribed.yaml` and backend URLs pointed at
the running local services (5002/5003/5005/…). Read-only replay:

- no-key → **401** (auth enforced);
- `tours-near` → 200 (13 tours), `search-tours` → 200;
- `download-tour/686` → 404 service JSON (normal not-found);
- `tour/686/resolve` → 404 (tour-id-resolution reached);
- **`entitlements/me` → 200** (user-api reachable — the gap vs Beta's gateway, proven closed);
- `communities/map` → 200 (real data), `communities/mine` → 200 `[]`;
- `tour/686/role` → 200 (LOCAL-762);
- `price-tiers` → 200, `treats-near` → 200, `user/<x>` → 404 (normal).

Every route resolved to the correct `-subscribed` backend. Gateway process stopped.

---

## Tests

**Flutter** (`flutter test`, full suite): **+1109 / −7**. The 7 are exactly the
known baseline — 6 in `local109_swipe_e2e_test.dart` (SocketException /
connection-refused; need a live local DB bound to random ports; environment-
dependent, pre-existing) and 1 in `storied_compat_screens_404_test.dart`
("Your plan" buy buttons; confirmed pre-existing via `git stash`). **No new
failures.** New `endpoints_subscribed_host_test.dart` passes (5/5).

**Python** (touched + importing suites, all green):
`api-gateway/test_subscribed_route_coverage.py` (77 paths),
`test_subscribed_gateway_loads.py`, `test_editing_routes.py` (default manifest
unchanged), `user-tracking/test_local764_apple_env_fallback.py` (5/5),
`test_local598_apple_jws.py` (17/17),
`tests/test_local734_per_store_verify.py` (15), `test_local699_purchases_mode.py` (4),
`test_local596_api.py` (11), `test_local595_api.py` (10),
`test_local728_admin_moderation.py` (11).

---

## Files in this change (committed individually; never `git add -A`)

Modified:
- `audio_tour_app/lib/config/endpoints.dart`
- `api-gateway/main.py`
- `user-tracking/apple_jws_verifier.py`
- `user-tracking/entitlements_api.py`
- `user-tracking/communities_api.py`

New:
- `audio_tour_app/test/endpoints_subscribed_host_test.dart`
- `api-gateway/gateway_routes.subscribed.yaml`
- `api-gateway/test_subscribed_route_coverage.py`
- `api-gateway/test_subscribed_gateway_loads.py`
- `user-tracking/test_local764_apple_env_fallback.py`
- `local764_tooling/migration_dry_run.sh`
- `SUBSCRIBED_GCLOUD_ENV.md`
- `SUBSCRIBED_MIGRATION_RUNBOOK.md`
- `SUBMISSION_LOCAL-764.md`

Not touched (per task): DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`,
GCLOUD_STORIED_START_HERE.md, `my_tours_screen.dart`, `home_screen.dart`.
The Beta/Storied gateway manifest `api-gateway/gateway_routes.yaml` is unchanged.
