# SUBMISSION — LOCAL-769: Meter AWS Polly & Translate boto3 calls

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-769-meter-boto3`
**Base:** `subscribed` @ `c6a0879c` (`git merge-base --is-ancestor c6a0879c HEAD` → exit 0)
**code_sha (fix commit):** `a0efba7f224f1e3bdf818470c1303b5f9f2710fe`

## Problem (GCloud_Storied wdvrdaz5yt, 2026-10-25, proven on Cloud Run)

Tour 446 → es (tour 447) ran AWS Translate + Polly and wrote **ZERO**
`paid_api_calls` rows. `_meter/paid_api_meter.py` `install()` patches
`requests` / `urllib` / `httpx` / `aiohttp`, but **botocore uses its own vendored
urllib3 stack**, so no Polly or AWS Translate call is ever recorded — on any
service, on the Mac or on GCloud. `check_daily_limit()` already runs before those
boto3 calls (LOCAL-673), so the cap *can stop* them, but their cost never counts
toward it, and Michael's daily spend report (wdvrdaz5yt Part C) would miss them.
Michael: "I do not want to get surprised in the end of the month."

Confirmed locally before the fix: `SELECT count(*) FROM paid_api_calls WHERE kind
IN ('polly','aws_translate')` = **0**.

## Fix

### 1. `_meter/paid_api_meter.py` — meter botocore at one choke point
`install()` now also patches **`botocore.client.BaseClient._make_api_call`**.

**Why `_make_api_call` and not per-service `after-call` events:** it is the one
choke point every operation of every boto3 client passes through — sync, retried
or not — so a single patch covers Polly `SynthesizeSpeech`, the async long-form
`StartSpeechSynthesisTask`, and Translate `TranslateText`, on every client
created before *or* after `install()`, with the request params **and** the parsed
response in hand. Registering per-service `after-call` handlers would instead
need hooking each client's event system via `create_client`, missing clients
already built.

Per metered call it writes **exactly one** `paid_api_calls` row:
- `kind` = `polly` / `aws_translate` (derived from the client endpoint host via
  the existing `_host_kind`, with a `service_name` fallback — every other AWS
  service is ignored).
- `status` = `ResponseMetadata.HTTPStatusCode` (defaults to 200 for a response
  that returned normally); a boto exception records a `$0` row and re-raises
  unchanged.
- `model` = Polly `Engine`+`VoiceId` (e.g. `neural/Joanna`) or `translate`.
- `usd` from **billed characters** × the `cost_rates.py` rate: Polly prefers the
  response's `RequestCharacters` (AWS's own billed figure, SSML tags included)
  and falls back to `len(Text)`, priced by `Engine`; Translate uses `len(Text)` ×
  the per-character rate. A non-200 costs `$0`.
- `role` via `_meter_role()` exactly like every other row (listener proof).

**Same fail-open rules as the rest of the meter:** `check_daily_limit()` runs
*before* the call (it may raise `DailyPaidLimitExceeded`, the intended STOP, or
fail open); the call itself is never altered; recording never raises into the
caller; the Polly `AudioStream` is **never read** (reading it would consume the
caller's stream).

**No double counting:** `grep record_call(` shows Polly/Translate are recorded
explicitly nowhere (only Serper uses `record_call`). The deployed Polly/
translation services meter via `cost_meter.record_operation` into the **separate**
`cost_ledger` table, not `paid_api_calls`, so this botocore path is the only
writer of Polly/Translate `paid_api_calls` rows — no row is written twice.

### 2. `cost_rates.py` — add the missing Polly engines
Added Long-Form ($100/M) and Generative ($30/M) rates and a
`POLLY_COST_PER_CHAR_BY_ENGINE` table; `tts_cost()` is now engine-aware for all
four engines (unknown engine → neural rate, which never under-bills standard).

### 3. `translation-service/_meter/` refreshed
`cp _meter/*.py translation-service/_meter/`; `tests/test_translation_meter_copy.py`
passes (byte-identical + the translation Dockerfile bakes the meter at
`/opt/meter` with `PYTHONPATH`). No new Python module was added, so no Dockerfile
COPY lists change.

## Tests — `tests/test_local769_boto3_metered.py` (6 tests)

Red-first, with a botocore `Stubber` (no real network / paid call / DB); the
meter's JSONL log is redirected to a tmp file and the DB write + daily-limit check
are stubbed (same pattern as `test_local707_serper_metered.py`).

**RED on the base** (botocore not yet wired) — 4 failed:
```
FAILED test_polly_synthesize_speech_metered   # IndexError: no rows
FAILED test_translate_text_metered            # no rows
FAILED test_no_double_row                      # 0 != 1
FAILED test_role_listener_when_proven          # no rows
(2 passed: meter_db_error_does_not_raise trivially; db_write_targets_paid_api_calls
 exercises the pre-existing _db_write that already INSERTs paid_api_calls)
```

**GREEN after the fix** — 6 passed:
```
test_polly_synthesize_speech_metered  PASSED   # one polly row, usd = chars×neural, role present, model has VoiceId
test_translate_text_metered           PASSED   # one aws_translate row, usd = chars×translate rate
test_meter_db_error_does_not_raise    PASSED   # _db_write raising does not propagate into the caller
test_no_double_row                    PASSED   # one boto3 call → exactly one row
test_role_listener_when_proven        PASSED   # role='listener' only with env label + mounted token file
test_db_write_targets_paid_api_calls  PASSED   # row is INSERTed into paid_api_calls (the table the cap sums)
```

Existing meter / cost tests stay green:
`test_local707_serper_metered`, `test_local673_daily_paid_limit`,
`test_local323_tts_metering`, `test_local578_translation_metering`,
`test_translation_meter_copy` → **37 passed**;
`test_local143_cost_model_matches_deploy` + `test_pricing` → **36 passed**.

## Live test (own container, local DB, budget ≤ $0.02)

Own throwaway container only — `docker run --rm --name local769-livetest
--label com.docker.compose.project=local769`, stock `python:3.9-slim`, boto3 +
psycopg2-binary pip-installed, bind-mounting the new `_meter/` at `/opt/meter`
(+`cost_rates.py`), `PYTHONPATH=/opt/meter`, AWS creds read from the running
`audioura-polly-tts-1-1`, DB at `host.docker.internal:5433` (the local
`development-postgres-2-1`). No `audioura-*` container touched, host Kokoro on
:5181 untouched, no custom image built, container auto-removed.

```
=== BEFORE ===
[]                                   # 0 polly/aws_translate rows — the bug

Polly chars: 69   → RequestCharacters: 69, audio 31436 bytes
Translate chars: 60 → "Verificación de medición en tiempo real de LOCAL-769…"

=== AFTER ===
[('aws_translate', 1, Decimal('0.000900')), ('polly', 1, Decimal('0.001104'))]

=== LATEST ROWS (id, kind, status, model, usd, role, caller) ===
(59778, 'aws_translate', 200, 'translate',    0.000900, None, 'local769_live.py:71')
(59777, 'polly',         200, 'neural/Joanna', 0.001104, None, 'local769_live.py:62')
```

- Polly: 69 chars × $16/M (neural) = **$0.001104** ✓
- Translate: 60 chars × $15/M = **$0.000900** ✓
- Total real AWS spend ≈ **$0.002** ≪ $0.02 budget.
- `role=None` is correct: the throwaway container has no mounted listener-token
  file, so it cannot qualify as a listener (fail-safe — test spend never counts
  toward the listeners' cap).

Cleanup: the 2 live rows (id 59777, 59778) were deleted from the dev DB after
verification (`DELETE 2`; count back to 0); the container was auto-removed.

## Price sources (verified 2026-10-26)

- **AWS Polly** — https://aws.amazon.com/polly/pricing/ (read 2026-10-26):
  Standard **$4.00**/1M chars, Neural **$16.00**/1M, Long-Form **$100.00**/1M,
  Generative **$30**/1M characters.
- **AWS Translate** — https://aws.amazon.com/translate/pricing/ (read 2026-10-26):
  pay-as-you-go per character of text translated; Standard Text Translation
  **$15.00**/1M characters (the long-standing published rate kept in
  `cost_rates.py`).

## Files changed (committed explicitly, no `git add -A`)

- `_meter/paid_api_meter.py` — botocore `_make_api_call` meter + Polly/Translate
  costing helpers.
- `translation-service/_meter/paid_api_meter.py` — refreshed copy (byte-identical).
- `cost_rates.py` — Polly Long-Form/Generative rates + engine-aware `tts_cost()`.
- `tests/test_local769_boto3_metered.py` — new red→green test suite.
- `SUBMISSION_LOCAL-769.md` — this file.

(`scratch/local769_live.py`, the live-test driver, is intentionally NOT committed —
it is a throwaway harness, not part of the fix.)

No GCloud deploy (GCloud_Storied deploys after LEAD review). DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md untouched.
