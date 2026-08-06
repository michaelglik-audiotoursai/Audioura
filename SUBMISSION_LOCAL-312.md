##### READY FOR REVIEW

**Commit:** 3164ac3b81b1cc9e0f5d9377b32fbcae015d6ea8
**Branch:** kiro/local312-quality-comms-and-user-index
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `quality_guardrails.py` | MESSAGE_THRESHOLD default changed from 60.0 → 50.0 |
| `user_quality_index.py` | **NEW** — private per-user aggregate + author edit recording (no Flask routes) |
| `tour_orchestrator_service.py` | Wire user index update after scoring generated tours |
| `tour_editing_phase2.py` | Wire author-edit below-threshold internal recording; no message to author |
| `storied_feature_flags.md` | Updated QUALITY_MESSAGE_THRESHOLD default to 50.0 |
| `tests/init_test_db.sh` | Added user_quality_index and author_edit_scores table creation |
| `tests/test_local307_quality_guardrails.py` | Updated test score from 50→45 to reflect new threshold |
| `tests/test_local312_quality_comms_and_user_index.py` | **NEW** — 17 tests covering all acceptance criteria + leak test |

---

## Verbatim evidence

### 1. Threshold 50.0, env-overridable, documented

```
THRESHOLD DEFAULT: 50.0
GUARDRAILS ENABLED: False
```

Feature flags doc row:
```
| `QUALITY_MESSAGE_THRESHOLD` | `50.0` | tour-orchestrator | Score below which an UNAVAILABLE tour gets a user-facing message. Set per Michael (LOCAL-312); env-overridable. |
```

### 2. Generated tour below threshold → listener messaged

```
[GUARDRAILS] score=42.0 cause=UNAVAILABLE delivered=3/5 PL=0 UA=2 thin=3/3 enabled=True is_retry=False
--- GENERATED TOUR BELOW THRESHOLD ---
Action: message
User message: We found 3 well-documented places for this area rather than the 5 you asked for. Here is the shorter tour.
Flag enabled: True
```

### 3. Author edit below threshold → NO message, internal record written

```
--- EDITED TOUR BELOW THRESHOLD (score=38.5 < 50.0) ---
Author message emitted: NONE (asymmetry rule)
[AUTHOR_EDIT] Recorded below-threshold edit: secret_id=demo-loc... tour_id=42 score=38.5
Internal record written: YES
  score: 38.5
  delta.sourced_facts_removed: 4
  delta.classifications_changed: [{'after': 'THIN', 'index': 2, 'before': 'ADEQUATE'}]
  recorded_at: 2026-08-06 17:14:31.224130+00:00
```

### 4. Per-user aggregate over ≥3 tours, not reachable from client

```
--- PER-USER AGGREGATE (3 tours) ---
  mean_score: 60.0
  tour_count: 3
  last_scored_at: 2026-08-06T17:14:40.416152+00:00

Is this reachable from any client endpoint? NO
  - user_quality_index.py has no @app.route
  - user_quality_index.py does not import jsonify
  - No orchestrator or editing endpoint returns user index data
```

### 5. Leak test catches deliberate introduction

```
--- LEAK TEST DEMONSTRATION ---
Injected: return jsonify({'status': 'created', 'tour_id': new_id, 'quality_message': msg})
Caught forbidden field: "quality_message"
Test would FAIL — leak protection working.
```

### 6. All tests passing

```
tests/test_local312_quality_comms_and_user_index.py  17 passed in 0.17s
tests/test_local307_quality_guardrails.py            12 passed in 0.10s
tests/test_local306_inflight_scoring.py               5 passed in 0.21s
```

### 7. Production count unchanged

```
SELECT count(*) FROM audio_tours WHERE is_test = false OR is_test IS NULL;
→ 29
```

---

## Limitations

1. **Author secret_id lookup depends on tour_requests table.** If a tour was generated before the tour_requests linkage existed (very early tours), the `secret_id` will be "unknown" in the author_edit_scores record. The record is still written with full delta data.

2. **Guardrails remain OFF.** `QUALITY_GUARDRAILS_ENABLED=false` means the listener message only fires when explicitly enabled. The threshold change takes effect the moment the flag is turned on.

3. **User quality index update is append-only.** There is no mechanism to re-aggregate from historical data. If the incremental mean drifts due to a bug, a corrective script would need to re-scan tour_scores joined to tour_requests.

4. **No container rebuilt.** Schema additions applied via direct SQL to both production and test databases. The `init_test_db.sh` will recreate them on next full schema rebuild.
