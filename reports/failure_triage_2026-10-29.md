# Failure triage — 2026-10-29 (last 7 days)

_Generated 2026-10-29 06:01 UTC by failure_triage.py (LOCAL-804, D723). Read-only; no DB writes._

- **8** distinct failure signatures, **91** events total.
- By class: our_bug=5, external=0, user_confusion=86, expected=0, unknown=0.
- **8** signatures are new since the last run (floated to the top).

## Top failure groups

### 1. `18c20b3c25e01f38` — user_confusion **[NEW]**

- score **74.0** · count **74** · severity 1
- first seen 2026-10-27 02:30 UTC · last seen 2026-10-29 04:43 UTC
- sources: failure_events · surfaces: generate
- suggested owner: LEAD → product/UI (make the interface guide the user)
- example: error_code=exhibition_closed · tour=test-local365-type
      message: The exhibition […] closed on 2024-12-01. A tour cannot be generated for a dismounted show.

### 2. `3cbf18a3195023a1` — user_confusion **[NEW]**

- score **11.0** · count **11** · severity 1
- first seen 2026-10-24 02:52 UTC · last seen 2026-10-28 15:10 UTC
- sources: tour_requests · surfaces: generate
- suggested owner: LEAD → product/UI (make the interface guide the user)
- example: error_code=tour_request_failed · tour=0a36d3be-1d15-41a6-8058-c22d4aebce62
      message: tour request failed

### 3. `9fefdfd57b6177f3` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:28 UTC · last seen 2026-10-28 14:28 UTC
- sources: failure_events · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=generation_failed · tour=df91b3c1-bc0d-43e5-a85e-2b6ee75d717a
      message: Tour generation failed for […] — no stops could be generated (all filtered or knowledge insufficient).

### 4. `f2d5f1d16dae778c` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:29 UTC · last seen 2026-10-28 14:29 UTC
- sources: failure_events · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=generation_failed · exc=Exception · tour=ab82adf4-78c3-4ea6-8271-0fa068585413
      message: Tour generation failed for […] — no stops could be generated (all filtered or knowledge insufficient).

### 5. `14821d0841704007` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 15:10 UTC · last seen 2026-10-28 15:10 UTC
- sources: failure_events · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=— · exc=Exception · tour=0a36d3be-1d15-41a6-8058-c22d4aebce62
      message: Text-generation abandoned after 241 polls — absolute 40-minute cap. The generator job was asked to stop. (ran 40.1 min, last progress 0.2 min ago.)

### 6. `d92fd9eeeaf19e26` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:28 UTC · last seen 2026-10-28 14:28 UTC
- sources: generator_jobs · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=generation_failed
      message: Tour generation failed for […] — no stops could be generated (all filtered or knowledge insufficient).

### 7. `4c494231f1d2102f` — our_bug **[NEW]**

- score **3.0** · count **1** · severity 3
- first seen 2026-10-28 14:29 UTC · last seen 2026-10-28 14:29 UTC
- sources: generator_jobs · surfaces: generate
- suggested owner: LEAD → engineering (fix the defect)
- example: error_code=cancelled
      message: generator job error

### 8. `0cbabeb3745ec767` — user_confusion **[NEW]**

- score **0.6** · count **1** · severity 1
- first seen 2026-10-27 01:52 UTC · last seen 2026-10-27 01:52 UTC
- sources: lookup_escalations · surfaces: dining
- suggested owner: LEAD → product/UI (make the interface guide the user)
- example: error_code=no_results_found
      message: no results found for dining/yak-wool

## User confusion — screens & actions for UI fixes

Michael (D723): turn these into interface fixes, not just bug tickets. Each row is a place the product asked the user for something it could not then deliver.

| signature | count | surface/action | example (redacted) |
| --- | --- | --- | --- |
| `18c20b3c25e01f38` | 74 | generate | The exhibition […] closed on 2024-12-01. A tour cannot be generated for a dismou… |
| `3cbf18a3195023a1` | 11 | generate | tour request failed |
| `0cbabeb3745ec767` | 1 | dining | no results found for dining/yak-wool |

