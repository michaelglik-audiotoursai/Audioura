##### READY FOR REVIEW

## LOCAL-190: stops_count is 0 on tours that have 15 stops

**Commit:** `acd88f7`  
**Branch:** `kiro/local190-stops-count-backfill`  
**Files changed:** `tour_worker_service.py`, `backfill_stops_count.py` (new)

---

## Root Cause

**File:** `tour_worker_service.py`  
**Function:** `store_audio_tour` (lines 148–193, before fix)  
**Specific lines:** INSERT at line 182, UPDATE at line 173

The Cloud Tasks worker (`tour_worker_service.py`) has its own
`store_audio_tour` function, written separately from the orchestrator's
version. When the orchestrator's `store_audio_tour` was fixed (round 11)
to include `stops_count` in its INSERT, the worker's copy was never
updated. It omits `stops_count` from both its INSERT and UPDATE SQL.

Any tour generated via `GENERATION_MODE=cloud_tasks` (the Cloud Run path)
goes through the worker's store function and gets `stops_count = 0`
(column default), regardless of how many stops were actually generated.

The older tours (ids 4–7) went through this same worker path; the newer
ones (154, 156) from LOCAL-183 also went through it. Same code path, same
symptom, two eras.

---

## Fix (tour_worker_service.py)

1. Added `stops_count=None` parameter to `store_audio_tour` signature.
2. Added `stops_count=%s` to both the UPDATE SET clause and the INSERT
   column list + VALUES.
3. Updated the call site (line 370) to pass `stops_count=actual_stops`
   (already computed from ZIP audio file count at line ~332).

---

## Backfill (backfill_stops_count.py)

Uses `parse_tour_stops` from `tests/stop_anchor_detector_v2.py` — the
same parser the rest of the system uses — to count stops from
`tour_content`. Only updates rows where `stops_count` is 0 or NULL and
parsed count > 0.

### Before/After Table

```
id     old    new    tour_name
----------------------------------------------------------------------
1      0      3      Palais Lascaris, Nice, France - museum Tour
2      0      5      Camel Tour in a desert of Abu Dhabi, UAE - museum Tour
3      0      4      Camelback riding your in Abu Dhabi desert, UAE - museum Tour
4      0      5      Camel tour in Abu Dhabi desert, UAE - museum Tour
5      0      5      Camelback riding tour in Abu Dhabi desert, UAE - museum Tour
6      0      2      dog ridding tour, Big Lake, AK - museum Tour
7      0      2      тур по верховой езде на собаках, Большое озеро, шт...
154    0      15     French Riviera cycling tour, France - Cycling Tour
156    0      15     French Riviera Cycling Tour [LOCAL-183 test]
```

**9 rows updated.**

---

## Evidence

### Row count preserved
```
Row count BEFORE: 117
Row count AFTER:  117
```

### Nice list [1,12,14,17,21,24,27,28,29] verification
```
id=1   stops_count=3
id=12  stops_count=10
id=14  stops_count=9
id=17  stops_count=5
id=21  stops_count=8
id=24  stops_count=6
id=27  stops_count=8
id=28  stops_count=8
id=29  stops_count=15
```
All non-zero, all present.

### Spot-check: re-parse two backfilled tours
```
id=1: db stops_count=3, re-parsed=3, match=True
id=2: db stops_count=5, re-parsed=5, match=True
```

### git status clean
```
$ git status --short
(empty)
```

### Commit on branch
```
$ git rev-list --count storied..HEAD
1
```

---

## Limitations

- **Deployment required:** The fix to `tour_worker_service.py` is committed
  but not deployed (per D48 — tasks propose, LEAD deploys). New tours
  generated via the Cloud Tasks worker will still get stops_count=0 until
  the container is rebuilt.
- **Backfill only covers rows with `tour_content`:** If any row has
  stops_count=0 but no tour_content, it cannot be backfilled from content
  parsing. No such rows were found in this run (all 9 candidates had
  content and were updated).
- **Id 1 was in both the zero-count set and the nice list:** It had
  stops_count=0 and tour_content with 3 parseable stops. The backfill
  correctly set it to 3 per the rule "only touch rows where stops_count
  is 0 or NULL and parsed count > 0."
