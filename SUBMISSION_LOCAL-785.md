# SUBMISSION — LOCAL-785: Record every failure (server + app), triage, prioritise

**Branch:** `LOCAL-785-failure-events` · **Base:** `subscribed @ 6733f580`
**Ticket/decision:** D723 (Michael, 2026-10-26)

> "Record all failures so later we can identify what happened. If it's our fault
> we fix it; if it's the user's mistake we make the interface more intuitive."

Today a failure vanishes: `tour_requests` only carries `'failed'` with no reason,
the generator's logs expire, and an APP failure leaves no trace at all. The
cloud downloads of 445/446 on 2026-10-26 failed **silently** and were only found
because GCloud_Storied read the raw container logs by hand. This builds the one
durable place every failure — server and app — is recorded, triaged and ranked.

---

## What was built

### 1. Migration — `migration/sql/054_failure_events.sql` (additive, next number)

`failure_events` with exactly the specified columns (id, ts, user_id,
app_version, platform, track, surface, error_code, message, request_text,
tour_id, job_id, exception_type, frames, http_status, service, `signature
CHAR(16)`, triage, triage_source, resolved_by) — 20 columns — plus indexes on
`(signature, ts)` and `(ts)`, and CHECK constraints pinning the triage
vocabularies. **No DROP, no DELETE**; `CREATE TABLE/INDEX IF NOT EXISTS` +
guarded constraint make it idempotent. A 90-day retention job is OUT of scope
(D723).

### 2. Server recorder — `failure_log.py`

`record(**kw)` writes one row to `failure_events`. Its hard contract:

* **Never raises** — a failure in the failure recorder must never turn a handled
  failure into a crash. Every path is wrapped.
* **1-second DB timeout** (`connect_timeout` + `statement_timeout`), overridable
  via `FAILURE_LOG_DB_TIMEOUT` (default 1).
* **stdout JSON fallback** — if the DB is unreachable the event is still emitted
  as a single `FAILURE_EVENT {…}` line, exactly how 445/446 would now be found.
* Supports **both** connection styles in the codebase (`DATABASE_URL`, or the
  discrete `DB_*` vars), and self-heals the table if migration 054 never ran.

**Signature** groups "the same failure" across ids/numbers/quotes:

```
signature = sha1(service + '|' + error_code + '|' + exception_type
                 + '|' + normalise(message))[:16]
```

`normalise()` strips quoted strings, hex/uuid ids and digit runs, so
`Tour 445 ("Boston") failed` and `Tour 446 ("Paris") failed` share one
signature.

**Auto-triage rules table** (`auto_triage`, first match wins):

| Rule | → triage | meaning |
|---|---|---|
| error_code ∈ {venue_no_verifiable_content, venue_misread, stops_not_colocated, request_unclassifiable, no_matching_places_in_area, content_quality_insufficient, factual_integrity, venue_closed, exhibition_closed} | `ux` | request can't be met as phrased → make the interface clearer |
| error_code ∈ {exhibition_not_found, by_reference_no_material} | `absence` | the thing isn't there / isn't researched yet |
| error_code == generation_failed (or purchase_required_for_creator) | `our_bug` | our pipeline failed / a creator was charged for their own tour |
| else http_status 5xx | `our_bug` | our server erred |
| else exception_type network/timeout-ish (timeout, connection*, socket, ssl, clientexception, oserror) | `external` | upstream/provider failure |
| else any other exception_type (a real crash) | `our_bug` | |
| else | `unknown` | a human should look |

### 3. Recorder wired into every server failure path

| Service | Where it records |
|---|---|
| **orchestrator** (`tour_orchestrator_service.py`) | `@errorhandler(Exception)` (records + re-raises the same 500); the job-failure sites (no-audio-files, store-failed, and the `orchestrate_tour_async` top-level except, which carries the forwarded LOCAL-774 `error_code`). "Generate Now" path. |
| **worker** (`tour_worker_service.py`) | `run_job` final-attempt terminal failure, carrying the structured refusal's `error_code`. "Generate in Background" path. |
| **generator** (`generate_tour_text_service.py`) | the clean-fail evidence block (`_LAST_CLEAN_FAIL_EVIDENCE`) — existence-gate "0 remain", PHASE 3C "rejected all", `thin_evidence`, `no_matching_places_in_area` — plus `@errorhandler(Exception)`. |
| **translation** (`translation-service/translation_service.py`) | `@errorhandler(Exception)`. |
| **tour-id-resolution** (`tour_id_resolution_service.py`) | 404 (tour/edit-id not found), 500 INTERNAL_ERROR, plus `@errorhandler(Exception)`. |
| **map-delivery** (`map_delivery/app.py`) | the `/download-tour` 5xx (the silent-445/446 class) plus `@errorhandler(Exception)`. A **normal 402 purchase gate is NOT recorded** (that is the paywall working). |

Every call goes through a tiny guarded `_record_failure(**kw)` helper in each
service, so a missing/failing recorder can never break a request.

### 4. `POST /client-failure` on user-api + gateway route

`user-tracking/app.py` gains `POST /client-failure`:

* body **≤ 8 KB** (413 otherwise), JSON object required (400), empty report 400,
* **rate-limited 20/hour per user** (sliding window keyed on user_id, or IP when
  anonymous; 429 over the limit, stores nothing),
* stores via the shared `failure_log.record(service='app', platform=…)`, returns
  the computed signature.

Gateway: one new route in `api-gateway/gateway_routes.subscribed.yaml`
(`/client-failure` → `user-api`, POST, `api_key`). Not added to the Beta/Storied
manifest, which has no user-api backend (its `/user` goes to news-orchestrator);
Subscribed is the authoritative stack for this (D708).

### 5. Flutter `FailureReporter` — `audio_tour_app/lib/services/failure_reporter.dart`

* `report(...)` sends **in the background, never blocks the UI, never throws**.
* **Offline queue** in SharedPreferences, up to **50**, FIFO (oldest dropped),
  flushed on the next report and at app start / `flush()`.
* **`FlutterError.onError` + `PlatformDispatcher.instance.onError`** installed in
  `main()` (uncaught errors), throttled to **5/min** (that throttle applies only
  to the uncaught path).
* Wired into the central error surface (`ErrorHandlerService.showError`, which
  skips 402), and the known **silent** failures: the post-download save/resolve
  failure (`home_screen.dart` batch download, `tour_translation_helper.dart`
  save/validate), and **auto-play not starting** (`voice_methods.dart`).

### 6. `failure_report.py` (read-only) + `--mark`

```
python3 failure_report.py --since 24h
python3 failure_report.py --since 7d --top 15
python3 failure_report.py --mark <signature> <triage> [resolved_by]
```

Groups by signature over the window and prints count, distinct users, first/last
seen, triage, one example (request text + message + top frame) and the

```
priority score = distinct_users × severity × recency_weight
  severity:  our_bug 3 (blocking) · external/absence 2 (degraded) · ux/unknown 1 (cosmetic)
  recency:   ≤1 day 1.0 · ≤7 days 0.6 · older 0.3
```

`distinct_users` uses 1 for a userless group so a real-but-userless failure still
scores. The report path is a single read-only SELECT; `--mark` is a single
UPDATE of the triage columns (`triage`, `triage_source='lead'`, optional
`resolved_by`) for LEAD.

### 7. `SUBSCRIBED_GCLOUD_ENV.md`

Appended §14: which services record (all reuse their EXISTING DB env — **no new
var**), the one optional tunable `FAILURE_LOG_DB_TIMEOUT` (default 1), the
test-only `FAILURE_LOG_TEST_HOOK`, the one new gateway `/client-failure` route,
the auto-triage table, and that 90-day retention is out of scope.

---

## Tests (red-first)

**Python (18, all green):**
* `tests/test_local785_recorder.py` — signature is 16 hex chars; stable across
  ids/numbers/quotes; differs on a real difference; the auto-triage rules;
  `record()` never raises with the DB down and still emits on stdout; never
  raises on bad arguments; fills exception fields from `exc`; the report ranks
  our_bug above ux at equal reach, recency lowers the score, a userless failure
  still scores; `parse_since` units.
* `tests/test_local785_client_failure.py` — a valid report is stored
  (`service='app'`, platform from the body); empty 400; non-JSON 400; oversized
  413; the rate limit allows 20 then 429 and stores only the 20.
* `tests/test_local785_orchestrator_records.py` — the forced-failure hook makes a
  request raise and the `@errorhandler` records `service='orchestrator'`,
  `http_status=500`, with an exception type.

**Flutter (5, all green)** — `audio_tour_app/test/failure_reporter_test.dart`:
a successful send is not queued; an offline send is queued then flushed when back
online; the queue is capped at 50; a download failure produces a report with
`surface='download'`; uncaught errors are throttled to ≤5.

**No regressions (base vs branch):** LOCAL-774 orchestrator + worker refusal (5),
user-tracking apple-env + entitlements-auth (10), actionable-failure / generator
/ map (21). The subscribed route-coverage test still passes (78 app paths).

---

## Live test

Own throwaway Postgres (`-p local785`-style container `local785_pg`, spare port
**55432**, DB **`audiotours_test`** — never `-p audioura`, nothing `audioura-*`
touched). Applied migration 054 → verified **20 columns, 2 indexes, 2 CHECK
constraints**. Then exercised all four failure classes as **real rows against the
real DB using the actual service code**:

* **(c) forced exception** — through the **real orchestrator Flask app**
  (`X-Force-Failure: 1`, `FAILURE_LOG_TEST_HOOK=1`): the `@errorhandler` stored
  `service=orchestrator, http_status=500, triage=our_bug`.
* **(a) refused Free request** — `error_code=by_reference_no_material` →
  `triage=absence`.
* **(b) existence-gate 0-stop** ("yak-wool cafés" style) —
  `error_code=no_matching_places_in_area` → `triage=ux`.
* **(d) one client failure** — through the **real `/client-failure` endpoint** on
  the user-api app → `service=app, surface=download`.

`failure_report.py --since 1h` ranked them by priority score:

```
#1 score=3.0 [orchestrator/http]    our_bug  HTTP 500  RuntimeError (forced test failure)
#2 score=2.0 [generator/generate]   absence  by_reference_no_material  (Griffin Museum, Winchester MA)
#3 score=1.0 [app/download]         unknown  tour_download_save_failed (Boston Common: 409)
#4 score=1.0 [generator/generate]   ux       no_matching_places_in_area (yak-wool cafes, West Roxbury MA)
```

`--mark 61621bf9123a442e our_bug LOCAL-790` then set that row's
`triage=our_bug, triage_source=lead, resolved_by=LOCAL-790` (verified in the DB).
Container torn down afterwards. **Row count: 4. Model API spend: $0.00.**

**Scope note (honest):** the full microservice **generation pipeline** producing
(a)/(b), and a **physical Android emulator** debug build for (d), were not run —
that needs the whole 10-service stack with real model spend plus an APK build,
and the local subscribed compose is bound to Michael's own environment (host
Kokoro, `/Users/micha/Audioura`, live keys), which this task must not disturb.
Those paths emit the **same** `failure_log.record(...)` / `POST /client-failure`
calls that were verified here directly against a real Postgres with the actual
service code and endpoint.

---

## Files

**Created:** `migration/sql/054_failure_events.sql`, `failure_log.py`,
`user-tracking/failure_log.py` (copy baked into the user-api image),
`failure_report.py`, `audio_tour_app/lib/services/failure_reporter.dart`,
`tests/test_local785_recorder.py`, `tests/test_local785_client_failure.py`,
`tests/test_local785_orchestrator_records.py`,
`audio_tour_app/test/failure_reporter_test.dart`, `SUBMISSION_LOCAL-785.md`.

**Modified:** `tour_orchestrator_service.py`, `tour_worker_service.py`,
`generate_tour_text_service.py`, `translation-service/translation_service.py`,
`tour_id_resolution_service.py`, `map_delivery/app.py`, `user-tracking/app.py`,
`api-gateway/gateway_routes.subscribed.yaml`, `SUBSCRIBED_GCLOUD_ENV.md`,
`audio_tour_app/lib/main.dart`,
`audio_tour_app/lib/services/error_handler_service.dart`,
`audio_tour_app/lib/services/tour_translation_helper.dart`,
`audio_tour_app/lib/screens/home_screen.dart`,
`audio_tour_app/lib/screens/voice_methods.dart`.
