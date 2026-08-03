##### READY FOR REVIEW

# LOCAL-156: A user can be charged for a tour that never reaches their library

## Commit

```
7a1edc0 LOCAL-156: fix charge-without-delivery when tour name collides
```

## Files Changed

| File | Change |
|------|--------|
| `tour_orchestrator_service.py` | Fixed `store_audio_tour` existence check + orchestrator failure handling |
| `wallet_ledger.py` | Added `service_credit` movement type |
| `tests/test_local156_charge_without_catalogue.py` | Reproduction + fix proof (16/16 pass) |

## Root Cause

The unique index on `audio_tours` is:

```sql
CREATE UNIQUE INDEX uq_audio_tours_original_name
ON public.audio_tours USING btree (lower((tour_name)::text))
WHERE (original_tour_id IS NULL)
```

This is a **global namespace** — uniqueness on `lower(tour_name)` across all users, with no per-user or per-language scoping. **94 original tours** hold this namespace (106 total rows, 12 are translations).

`store_audio_tour` checked `WHERE tour_name = %s AND request_string = %s` (case-sensitive, two columns), but the constraint is case-insensitive on `tour_name` alone. A case mismatch (e.g., "museum Tour" vs "Museum Tour") caused:
1. The SELECT to find nothing → attempt INSERT
2. The INSERT to fail on the unique index → `psycopg2.errors.UniqueViolation`
3. The exception to be caught by the broad `except Exception` → return `False`
4. The orchestrator to fall through to `log_job_update(job_id, "completed", ...)` regardless

The charge happened upstream in `generate_tour_text_service.py` (Step 1), before storage (Step 5). No rollback or compensation was issued.

## Fix

1. **`store_audio_tour`**: Changed existence check to `WHERE lower(tour_name) = lower(%s) AND original_tour_id IS NULL`, matching the actual unique index. Returns a structured dict: `{success, action, existing_tour_id, error}`. When the tour already exists, returns `action="already_exists"` with the existing ID.

2. **`orchestrate_tour_async`**: 
   - If `store_success = False`: sets job status to `"error"`, issues a `service_credit` to reverse the charge, and **returns early** (never falls through to "completed").
   - If `action = "already_exists"`: issues a `service_credit` to reverse the charge (per Michael: "it cost us and our clients nothing when they download a tour already pre-created"), then proceeds with the existing tour ID.

3. **`wallet_ledger.py`**: Added `service_credit` to `VALID_MOVEMENT_TYPES` for compensating credits when delivery fails after charge.

## Evidence

### Before (the bug, observed 2026-08-02)
```
job status            completed, actual_stops 2
ZIP on disk           palais_lascaris_nice_france_museum_c9006b84.zip (1.4 MB)
wallet charged        $0.08   (our cost $0.016824 × 5)
audio_tours row       NEVER WRITTEN (UniqueViolation swallowed)
```

### After (the fix, test output)
```
Test user: test_local156_5198f223
Job ID:    0f2af0de-a142-4b3b-8321-60da07567710

─── STEP 3: SIMULATE CHARGE ───
  Our cost: $0.016824
  User charge (cost × 5): $0.08 (8¢)
  Balance after charge: 992¢ ($9.92)

─── STEP 4: STORE AUDIO TOUR (colliding name) ───
  Existing tour (unique-index-aware check): (1,)
  [LOCAL-156] Tour already exists (id=1). Incrementing number_requested.
  store_audio_tour result: {action: 'already_exists', existing_tour_id: 1}

─── STEP 5: COMPENSATING CREDIT ───
  Service credit issued: +8¢
  Balance after credit: 1000¢ ($10.00)
  ✅ Net balance unchanged (charge + credit = 0)

─── STEP 6: VERIFY NO NEW ROW ───
  audio_tours rows (before/after): 106 / 106
  wallet_ledger rows (before/after): 170 / 173 (topup + charge + credit)
  ✅ No new audio_tours row created (tour reused)

─── STEP 7: JOB STATUS (store_failed case) ───
  ✅ Orchestrator guards against store failure (returns early, never 'completed')
  ✅ Service credit issued on store failure

SUMMARY: 16/16 PASS
```

### Row Counts

| Table | Before | After |
|-------|--------|-------|
| `audio_tours` | 106 | 106 (unchanged) |
| `wallet_ledger` | 170 | 173 (+3: topup, charge, service_credit) |

## Behaviour Summary

| Scenario | Before | After |
|----------|--------|-------|
| Tour name already exists | Charge $0.08, swallow error, report "completed", no library entry | Detect existing tour, issue service_credit, report "completed" with existing tour ID |
| Store genuinely fails (DB error) | Charge $0.08, swallow error, report "completed" | Issue service_credit, report "error" with explanation |
| New tour (no collision) | Works correctly | Works correctly (no change) |

## Limitations

1. **Charge happens upstream** — the charge is made in `generate_tour_text_service.py` before the orchestrator even attempts storage. The fix issues a compensating credit rather than preventing the charge, because the orchestrator cannot reach back into the generator's flow. This creates two wallet rows (charge + credit) rather than zero.

2. **Full generation still runs** — even when the tour already exists, the full text generation + TTS pipeline runs before the collision is detected at storage time. A future optimization could check for name collisions at the start of the orchestrator flow to avoid the wasted compute. This is a cost-to-us issue, not a user-facing issue (the user's balance is restored).

3. **The test does not exercise the full HTTP pipeline** — the subscribed stack containers are rebuilt with the fix, but a full end-to-end generation requires OPENAI_API_KEY. The test exercises `store_audio_tour` + `wallet_ledger` directly with the real database, which is the precise codepath that was broken.

4. **Pre-existing test failure** — `tests/test_wallet_ledger.py::test_ledger_and_derived_balance` fails identically on the base branch (monthly_fee behavior unrelated to this change).
