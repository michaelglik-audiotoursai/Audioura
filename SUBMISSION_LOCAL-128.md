##### READY FOR REVIEW

# SUBMISSION_LOCAL-128: Write `stop_metrics.tour_id` — resubmission (test exercises production path)

**Task:** LOCAL-128 — Write stop_metrics.tour_id  
**Branch:** `kiro/local128-stop-metrics-tourid`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-02 (resubmission after bounce)  

---

## Bounce Summary

First submission had the correct change and correct diagnosis but the test
reproduced the SQL inline rather than exercising the production code path.
LEAD commented out the UPDATE and the test still passed — proving nothing.

This resubmission extracts the UPDATE into a named function
`link_stop_metrics_to_tour()` and has the test import and call that function.

---

## Commit

```
git rev-list --count storied..HEAD: 1
Commit: e96d96f
```

---

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `tour_orchestrator_service.py` | +34 (function) / -17+6 (call site) | Extract `link_stop_metrics_to_tour` + call from orchestrate_tour_async |
| `tests/test_local128_stop_metrics_tourid.py` | +155 (rewritten) | Imports and calls the production function |
| `SUBMISSION_LOCAL-128.md` | this file | Submission artifact |

---

## 1. Write path

**stop_metrics INSERT:** `generate_tour_text_service.py`, function `_persist_icon_metrics(icon_result, job_id)` (line 74). Writes with `job_id` but no `tour_id` (tour doesn't exist yet).

**tour_id backfill:** `tour_orchestrator_service.py`, function `link_stop_metrics_to_tour(tour_id, job_id)` (line 580). Called from `orchestrate_tour_async` at ~line 956, after `store_audio_tour` creates the row and `english_tour_id` is retrieved.

---

## 2. The function

```python
def link_stop_metrics_to_tour(tour_id, job_id):
    """LOCAL-128: Set tour_id on stop_metrics rows that were written before the tour existed."""
    import psycopg2
    try:
        conn = psycopg2.connect(...)
        cur = conn.cursor()
        cur.execute(
            "UPDATE stop_metrics SET tour_id = %s WHERE job_id = %s AND tour_id IS NULL",
            (tour_id, job_id)
        )
        updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return updated
    except Exception as e:
        print(f"[LOCAL-128] link_stop_metrics_to_tour failed: {e}")
        return -1
```

The call site:
```python
if english_tour_id and job_id_1:
    _sm_updated = link_stop_metrics_to_tour(english_tour_id, job_id_1)
```

---

## 3. Test proves both directions

The test imports the real function:
```python
from tour_orchestrator_service import link_stop_metrics_to_tour
```

Then calls it on a test row and asserts:
- `link_stop_metrics_to_tour(test_tour_id, test_job_id)` returns 1
- The `stop_metrics` row's `tour_id` resolves via JOIN to `audio_tours`
- A second call returns 0 (idempotency)

### PASS (UPDATE intact):
```
======================================================================
LOCAL-128 GUARD TEST: link_stop_metrics_to_tour (production path)
======================================================================

  BEFORE: audio_tours=94, stop_metrics=1002

  Step 2: Created test tour id=123
  Step 3: Inserted stop_metrics row with job_id=LOCAL128_TEST_b6b4797f8a1d, tour_id=NULL
  Step 4: Confirmed tour_id=NULL (pre-fix state)
  Step 5: link_stop_metrics_to_tour returned: 1
  Step 6: ✓ GUARD PASSED — tour_id=123 resolves to audio_tours.id=123
           tour_name: LOCAL-128 Guard Test LOCAL128_TEST_b6b4797f8a1d
  Step 7: ✓ FK integrity verified — no orphan references
  Step 8: ✓ Idempotency verified — second call updated 0 rows

  AFTER (before cleanup): audio_tours=95, stop_metrics=1003
  AFTER (cleanup): audio_tours=94, stop_metrics=1002
  ✓ No data leaked — counts restored to original

======================================================================
LOCAL-128 GUARD TEST: ALL PASSED
======================================================================
EXIT CODE: 0
```

### FAIL (UPDATE commented out):
```
======================================================================
LOCAL-128 GUARD TEST: link_stop_metrics_to_tour (production path)
======================================================================

  BEFORE: audio_tours=94, stop_metrics=1002

  Step 2: Created test tour id=122
  Step 3: Inserted stop_metrics row with job_id=LOCAL128_TEST_6c95d73185f1, tour_id=NULL
  Step 4: Confirmed tour_id=NULL (pre-fix state)
  Step 5: link_stop_metrics_to_tour returned: 0

  ✗ ASSERTION FAILED: FAIL: link_stop_metrics_to_tour updated 0 rows, expected 1. The UPDATE in the production function may be missing or broken.
EXIT CODE: 1
```

---

## 4. Historical rows: UNRECOVERABLE

The 1002 existing `stop_metrics` rows remain `tour_id = NULL`. Reasons unchanged from first submission:
- No stored mapping between `audio_tours` and `stop_metrics.job_id`
- Evaluated text differs from stored `tour_content` (LOCAL-127 evidence)
- Title collision between tours 21/27/28 makes heuristic matching wrong

---

## 5. Row counts

```
audio_tours BEFORE:   94
audio_tours AFTER:    94 (unchanged)
stop_metrics BEFORE:  1002
stop_metrics AFTER:   1002 (unchanged)
```

---

## 6. Constraints verified

```
tours-near/43.7009358/7.2683912?radius=50 = [1, 12, 14, 17, 21, 24, 27, 28, 29]  ✓
python3 -m py_compile tour_orchestrator_service.py → SYNTAX OK  ✓
No DELETE FROM audio_tours  ✓
No DELETE FROM stop_metrics  ✓
No Docker builds  ✓
No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md  ✓
```

---

## Limitations

1. **Runtime verification impossible.** The orchestrator runs inside Docker. Without a build (blocked), the live path `orchestrate_tour_async → link_stop_metrics_to_tour` cannot be exercised end-to-end. The test exercises the exact production function against the live database, which is the strongest verification available without Docker.

2. **Non-fatal error handling.** If `link_stop_metrics_to_tour` fails (DB down, unexpected state), it returns -1 and the orchestrator logs it but continues. Tour generation succeeds regardless — the linkage is best-effort, matching the existing pattern.

3. **Historical rows permanently NULL.** The 1002 existing rows cannot be attributed. Only tours generated AFTER this fix get the linkage.

4. **i_con aggregates remain NULL.** This fix establishes the KEY. Computing `i_con_avg`/`i_con_min` on `audio_tours` is a follow-up step once future tours have linked `stop_metrics` rows.
