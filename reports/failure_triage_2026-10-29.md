# Failure triage — 2026-10-29 (last 7 days)

_Generated 2026-10-29 07:21 UTC by failure_triage.py (LOCAL-804/804B, D723). Read-only; no DB writes._

- **4** distinct failure signatures, **14** events total.
- By class: our_bug=2, external=0, budget=0, user_confusion=1, expected=0, unknown=11.
- **4** signatures are new since the last run (floated to the top).
- 77 test/harness events excluded (test/TEST/p1- ids, LOCAL-NNN harnesses); run with `--include-tests` to audit them.

## Top failure groups

### 1. `3cbf18a3195023a1` — unknown **[NEW]**

- score **11.0** · count **11** · severity 1
- first seen 2026-10-24 02:52 UTC · last seen 2026-10-28 15:10 UTC
- sources: tour_requests · surfaces: generate
- suggested owner: LEAD (triage by hand)
- example: error_code=tour_request_failed · tour=0a36d3be-1d15-41a6-8058-c22d4aebce62
      message: tour request failed

### 2. `d92fd9eeeaf19e26` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:28 UTC · last seen 2026-10-28 14:28 UTC
- sources: generator_jobs · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=generation_failed
      message: Tour generation failed for […] — no stops could be generated (all filtered or knowledge insufficient).

### 3. `4c494231f1d2102f` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:29 UTC · last seen 2026-10-28 14:29 UTC
- sources: generator_jobs · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=cancelled
      message: generator job error

### 4. `0cbabeb3745ec767` — user_confusion **[NEW]**

- score **0.6** · count **1** · severity 1
- first seen 2026-10-27 01:52 UTC · last seen 2026-10-27 01:52 UTC
- sources: lookup_escalations · surfaces: dining
- suggested owner: LEAD → product/UI (make the interface guide the user)
- example: error_code=no_results_found
      message: no results found for dining/yak-wool

## Budget / credit — paid-API cap, not a defect

_No budget/credit-caused failures in this window._

## User confusion — screens & actions for UI fixes

Michael (D723): turn these into interface fixes, not just bug tickets. Each row is a place the product asked the user for something it could not then deliver.

| signature | count | surface/action | example (redacted) |
| --- | --- | --- | --- |
| `0cbabeb3745ec767` | 1 | dining | no results found for dining/yak-wool |

