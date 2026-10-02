# SUBMISSION — LOCAL-476: Test the service the app actually calls

**Branch:** `LOCAL-476-orchestrator-empty-type-test`
**Base:** `storied` @ `bd109fa` (verified `git merge-base --is-ancestor bd109fa HEAD` → exit 0)
**Supersedes:** LOCAL-474 — its production code is correct and kept verbatim; this task adds the missing coverage.

## The gap

LOCAL-474 relaxed the *same* validation guard in two services:

| Service | Endpoint | Covered by LOCAL-474? |
|---|---|---|
| `generate_tour_text_service.py` | `/generate` | ✅ yes (test_client) |
| `tour_orchestrator_service.py` | `/generate-complete-tour` | ❌ **no** |

The app (and Michael's phone, and LEAD's 2026-09-03 production repro) hits
`/generate-complete-tour` on the **orchestrator**. LEAD's break-the-code check (D242)
restored the old guard in the orchestrator and the suite stayed green — the only
endpoint that mattered for this bug had zero coverage (D418/D421: green over the
unverified path).

## What I added

`tests/test_local476_orchestrator_empty_type.py` — a `TestOrchestratorValidationGate`
class that drives `tour_orchestrator_service.app` with a Flask `test_client()`, exactly
mirroring how LOCAL-474 drove the text service. The handler's real side effects — the
quota check (`entitlements.check_tour_quota`), the usage-recording DB insert
(`psycopg2.connect`), user tracking (`track_user_tour`), and the background generation
thread (`threading.Thread`) — are all stubbed, so a request that clears the validation
gate returns the queued response without touching a live service. Nothing real runs; no
tour is generated.

Coverage on the ORCHESTRATOR:

- `test_ac1_empty_tour_type_is_accepted` — `tour_type=''` → 200 `queued`
- `test_ac1_missing_tour_type_key_is_accepted` — no `tour_type` key → 200 `queued`
- `test_ac3_missing_location_still_400s_and_names_location` — 400, message names `location`
- `test_ac3_empty_location_still_400s` — 400
- `test_ac2_explicit_tour_type_still_wins` — explicit `tour_type='restaurant'` → 200 `queued`

No production behaviour changed. `git diff` on `tour_orchestrator_service.py`,
`generate_tour_text_service.py`, and `generate_tour_text.py` is empty — LOCAL-474's code
is byte-for-byte intact.

## Proof it can fail (D242 break-the-code)

### AC1 — break the ORCHESTRATOR → RED (this is the whole task)

Restored the old guard in `tour_orchestrator_service.py`:

```python
if not location or not tour_type:
    return jsonify({"error": "location and tour_type are required"}), 400
```

```
FAIL: test_ac1_empty_tour_type_is_accepted (tests.test_local476_orchestrator_empty_type.TestOrchestratorValidationGate)
AssertionError: 400 != 200 : empty tour_type must be accepted by the orchestrator, got 400: b'{"error":"location and tour_type are required"}\n'
FAIL: test_ac1_missing_tour_type_key_is_accepted (tests.test_local476_orchestrator_empty_type.TestOrchestratorValidationGate)
AssertionError: 400 != 200 : missing tour_type key must be accepted by the orchestrator, got 400: b'{"error":"location and tour_type are required"}\n'
Ran 18 tests in 0.035s
FAILED (failures=2)
```

Restored to correct code → GREEN:

```
Ran 18 tests in 0.033s
OK
```

### AC2 — break the TEXT SERVICE → RED (LOCAL-474 coverage kept)

Restored the old guard in `generate_tour_text_service.py`:

```
FAIL: test_ac1_empty_tour_type_is_accepted (tests.test_local474_empty_tour_type.TestTextServiceValidationGate)
FAIL: test_ac1_missing_tour_type_key_is_accepted (tests.test_local474_empty_tour_type.TestTextServiceValidationGate)
Ran 18 tests in 0.035s
FAILED (failures=2)
```

Restored to correct code → GREEN:

```
Ran 18 tests in 0.033s
OK
```

## Acceptance criteria

1. ✅ Breaking `tour_orchestrator_service.py` turns tests red (2 failures on the orchestrator class).
2. ✅ Breaking `generate_tour_text_service.py` still turns tests red (LOCAL-474's coverage kept).
3. ✅ All 18 tests pass unbroken.
4. ✅ Both break-runs pasted above, red and green.

## Live verification (for LEAD, post-merge)

```
{"location":"Bread Thyme restaurant tour in West Roxbury, MA","tour_type":"","total_stops":1}
```

Not run here — generating a real tour costs money/time and the task explicitly scopes this
to unit coverage of the validation gate. No Docker rebuild performed (disk constrained,
machine in use).
