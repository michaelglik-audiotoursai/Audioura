##### READY FOR REVIEW

## LOCAL-88: Test Tour Pollution Prevention (R2 — Bounce Fix)

**Commit:** (see below)
**Branch:** `kiro/local88-test-tour-pollution`

---

### What was wrong (bounce)

1. The `is_test` filter was added to `map_delivery_service.py` at repo root — a **dead code** file. The running container builds from `map_delivery/app.py` (per `docker-compose-master.yml: build: ./map_delivery`).
2. Coordinates were restored but `is_test` was left `false`, causing 11 test tours to appear in Michael's Nice list.

### What this commit fixes

1. **`map_delivery/app.py`** — the file that actually runs — now has `AND (is_test IS NOT TRUE)` in both the `tours-near` and `search-tours` queries.
2. Container rebuilt and confirmed FRESH (MD5 match between container and host file).
3. Real coordinates restored on known test rows (ids 39–43, 49–55) from `scratchpad/testrows_backup.txt`. LEAD already set `is_test=TRUE` on ids 36–55; this commit did not change that flag.
4. The `is_test` flag alone now hides test tours — coordinates are intact.

### Dead code note: `map_delivery_service.py` (repo root)

This file is referenced only by `docker-compose.yml` (line 41: `command: python map_delivery_service.py`) — an older/alternate compose file. The **live** compose file is `docker-compose-master.yml` which uses `build: ./map_delivery` → `map_delivery/app.py`. The root file already has the `is_test` filter from the first attempt (lines 146, 382) but it never executes in the current deployment.

### Per-file changes

| File | Change |
|------|--------|
| `map_delivery/app.py` | Added `AND (is_test IS NOT TRUE)` to `tours-near` query (line 111) and `search-tours` query (line 303) |
| `SUBMISSION_LOCAL-88.md` | This file (updated) |

### DB changes

- **Coordinates restored** on ids 39, 40, 41, 42, 43, 49, 50, 51, 52, 53, 54, 55 (from `scratchpad/testrows_backup.txt`)
- `is_test` flag unchanged (already `TRUE` on ids 36–55, set by LEAD)
- **No rows deleted. No schema changes.**
- Row count: 52 → 55 (3 rows added by acceptance test, all flagged `is_test=TRUE`)

---

### Acceptance Evidence

#### AC1: `tours-near/43.7009358/7.2683912?radius=50` returns exactly 9 real tours

```
$ curl -s 'http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50' | python3 -c "..."
Total tours: 9
IDs: [1, 12, 14, 17, 21, 24, 27, 28, 29]
```

#### AC2: Test-mode tour exists, is flagged, excluded from tours-near

```
Created test tour id=63
Row exists: id=63, is_test=True, lat=43.7009, lng=7.2684
tours-near result (should not contain 63): [1, 12, 14, 17, 21, 24, 27, 28, 29]
✅ PASS — tour exists, is flagged, excluded from tours-near
```

#### AC3: Helper cleanup removes only ids it created

```
Created tour A: id=64
Created tour B: id=65
After cleanup_specific([64]):
  Tour A: id=64, lat=None, lng=None, is_test=True
  Tour B: id=65, lat=43.71, lng=7.28, is_test=True
✅ PASS — cleanup_specific only touched the specified ID
```

#### AC4: Known test rows backfilled with flag + coordinates

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

#### AC5: Row count

```
Row count before: 52
Row count after:  55 (delta +3 from acceptance test, all is_test=TRUE)
No DROP.
```

#### Image freshness

```
$ python3 check_image_freshness.py --container audioura-map-delivery-1 --host-dir ./map_delivery
✅ audioura-map-delivery-1                  FRESH
   Image: local-88-map-delivery:latest
   Created: 2026-07-31 23:37:01 -0400 EDT
   Files checked: 1, drifted: 0
```

#### Container has the filter deployed

```
$ docker exec audioura-map-delivery-1 grep -n "is_test" /app/app.py
104:        # Exclude test-generated tours (is_test flag set by test-mode generation)
111:            AND (is_test IS NOT TRUE)
303:            AND (is_test IS NOT TRUE)
```

---

### Limitations

- `check_image_freshness.py` reports STALE when run without `--host-dir` because it compares `/app/app.py` in the container against the repo root (where no `app.py` exists); the actual match requires `--host-dir ./map_delivery`. The tool's default mode was designed for containers that build from the repo root.
- The root-level `map_delivery_service.py` also has the filter (from the first attempt) but is dead code for the current deployment. If the old `docker-compose.yml` is ever used, it would also filter correctly.
- Ids 36, 37, 38, 44, 45, 46, 47, 48 are flagged `is_test=TRUE` but don't have coordinates restored (no entry in `testrows_backup.txt` for them). They remain safely hidden by both NULL coords and the flag.
