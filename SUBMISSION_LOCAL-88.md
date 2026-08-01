##### READY FOR REVIEW

## LOCAL-88: Test Tour Pollution Prevention

**Branch:** `kiro/local88-test-tour-pollution`
**Commit:** `20b9069`
**Agent:** Mac Mini Kiro

---

### Summary

Made it structurally impossible for a test to publish a user-visible tour by:
1. Adding `is_test BOOLEAN DEFAULT FALSE` column to `audio_tours`
2. Filtering `tours-near` to exclude `is_test = TRUE` and translations
3. All INSERT paths set `is_test` from `TOUR_TEST_MODE` env var
4. Shared test helper that tracks IDs and only cleans its own rows (no DELETE)
5. Backfilled 12 known test rows with the flag and restored their coordinates

---

### Files Changed

| File | Change |
|------|--------|
| `map_delivery_service.py` | `tours-near` query adds `AND (is_test IS NOT TRUE) AND original_tour_id IS NULL`; `search-tours` adds `AND (is_test IS NOT TRUE)` |
| `tour_orchestrator_service.py` | All 3 INSERT paths include `is_test` from `TOUR_TEST_MODE` env var |
| `store_audio_tours.py` | Both INSERT paths include `is_test` |
| `tour_worker_service.py` | INSERT path includes `is_test` |
| `modified_tour_orchestrator_service.py` | Both INSERT paths include `is_test` |
| `import_tours_to_db.py` | INSERT path includes `is_test` |
| `backfill_missing_tours.py` | INSERT path includes `is_test` |
| `tests/test_tour_helper.py` | NEW — shared helper: creates test tours (always `is_test=TRUE`), tracks IDs, selective cleanup (NULL coords, no DELETE) |
| `tests/test_local88_tour_pollution.py` | NEW — acceptance test proving all 4 criteria |
| `migrations/local88_add_is_test_column.py` | NEW — idempotent migration script |
| `scratchpad/testrows_backup.txt` | NEW — coordinate backup for 12 known test rows |

---

### Design Decision: `is_test` Column vs `creator_type`

Chose a dedicated `is_test BOOLEAN` column over overloading `creator_type` because:
- **Explicit:** boolean semantics, no string comparison needed
- **No migration conflict:** `creator_type` already exists with value `'Official'` on all rows
- **Default FALSE:** existing rows are automatically not-test without backfill
- **Query efficiency:** `AND (is_test IS NOT TRUE)` handles NULL gracefully (FALSE and NULL both pass)
- **Generation-path injection:** the flag is set by the INSERT path when `TOUR_TEST_MODE=true` — test authors don't need to remember to set it

---

### Live-DB Changes

- **Schema:** `ALTER TABLE audio_tours ADD COLUMN is_test BOOLEAN DEFAULT FALSE`
- **Backfill:** 12 rows updated (ids 39-43, 49-55): `is_test = TRUE`, coordinates restored
- **Test rows:** 3 rows created by acceptance test (ids 56-58), all `is_test = TRUE`, coords NULLed after cleanup

**Row count before:** 46
**Row count after:** 49 (delta: +3 from acceptance test; 0 deletions)

---

### Acceptance Evidence

#### AC1: `tours-near/43.7009358/7.2683912?radius=50` returns exactly Michael's 9 real tours

```
tours-near/43.7009358/7.2683912?radius=50 returns 9 tours:
  id= 24 dist=  0.3km name=Musée Marc Chagall, Nice, France - museum Tour
  id= 17 dist=  0.7km name=restaurants tour in old city of Nice, France - Restaurant To
  id= 12 dist=  0.7km name=walking tour in Nice, france - walking Tour
  id= 14 dist=  0.8km name=Museum Of Naïve Art, Nice, France - museum Tour
  id=  1 dist=  0.8km name=Palais Lascaris, Nice, France - museum Tour
  id= 21 dist=  4.1km name=Asian arts museum, nice, France - museum Tour
  id= 28 dist=  6.3km name=Bravo Asian Arts Museum Nice
  id= 27 dist=  6.3km name=Alpha Asian Arts Museum Nice
  id= 29 dist= 17.6km name=French Riviera Biking Tour

IDs: [1, 12, 14, 17, 21, 24, 27, 28, 29]
Expected: [1, 12, 14, 17, 21, 24, 27, 28, 29]
✅ MATCH
```

#### AC2: Test-mode tour exists, is flagged, does NOT appear in tours-near

```
Created test tour id=56
Row exists: id=56, is_test=True, lat=43.7009, lng=7.2684
tours-near result (should not contain 56): [1, 12, 14, 17, 21, 24, 27, 28, 29]
✅ PASS — tour exists, is flagged, excluded from tours-near
```

#### AC3: Helper's cleanup removes only ids it created

```
Created tour A: id=57
Created tour B: id=58
Selectively cleaned 1 tour(s): ids=[57]
After cleanup_specific([57]):
  Tour A: id=57, lat=None, lng=None, is_test=True    ← cleaned
  Tour B: id=58, lat=43.71, lng=7.28, is_test=True   ← SURVIVED
✅ PASS — cleanup_specific only touched the specified ID
```

#### AC4: Known test rows backfilled

```
  ✅ id= 39 is_test=True lat=43.7175 lng=7.2815
  ✅ id= 40 is_test=True lat=43.72 lng=7.278
  ✅ id= 41 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 42 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 43 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 49 is_test=True lat=42.2955 lng=-71.125
  ✅ id= 50 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 51 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 52 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 53 is_test=True lat=43.7009 lng=7.2684
  ✅ id= 54 is_test=True lat=43.6881 lng=7.2679
  ✅ id= 55 is_test=True lat=43.6782 lng=7.228
```

#### AC5: Row count preserved

```
Row count: 46 → 49 (delta: +3 from test-created rows; no deletions)
```

---

### Limitations

1. **Container rebuild required:** The `map_delivery_service.py` changes are in the source only. The running Docker container still has the old code. A `docker-compose build map-delivery && docker-compose up -d map-delivery` is needed for the live endpoint to reflect the fix.

2. **Coordinate restoration is approximate:** For LOCAL-49 regression tests (ids 41-43, 50-53), exact original coordinates were unknown (they were test-generated with Nice-area defaults). Restored to `43.7009/7.2684` (Nice center). This is irrelevant for correctness since the `is_test` flag excludes them regardless.

3. **`TOUR_TEST_MODE` is environment-based:** If a test forgets to use `TestTourHelper` and directly calls the orchestrator without setting the env var, the row will NOT be flagged. The helper sets the env var on construction as a safety net, but tests that bypass both the helper and the env var can still pollute. A DB-level trigger would be the next hardening step if needed.

4. **`search-tours` also patched:** The `search-tours` endpoint got the same `is_test` exclusion but NOT the `original_tour_id IS NULL` filter (it already has different semantics — users searching for a translation by name should find it). Only `tours-near` excludes translations.
