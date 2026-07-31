##### READY FOR REVIEW

## Commit

Branch `kiro/local50-deterministic-tour-zip-mapping`, single commit ahead of `storied`.

## Changes per file

| File | What changed |
|------|-------------|
| `tour_id_resolution_service.py` | Rewrote `find_edit_tour_id()`: primary path reads `zip_filename` column; filesystem scan is a fallback that logs WARNING and refuses ambiguous matches (returns error dict). Deleted all four hardcoded venue branches (boston, harvard, clark, american wing). HTTP endpoint returns 409 `AMBIGUOUS_RESOLUTION` with candidate list. Added `resolution_method` to response. |
| `store_audio_tours.py` | Persists `zip_filename = os.path.basename(zip_path)` on both INSERT and UPDATE of audio_tours rows. |
| `tour_orchestrator_service.py` | Same: persists `zip_filename` on all INSERT/UPDATE paths (has_tour_content, has_lat, and fallback). |
| `tour_worker_service.py` | Same: persists `zip_filename` on INSERT and UPDATE in `store_audio_tour()`. |
| `migration/sql/004_zip_filename_column.sql` | Idempotent DDL: `ALTER TABLE audio_tours ADD COLUMN zip_filename VARCHAR(512)` + partial index on non-NULL values. |
| `backfill_zip_filename.py` | Standalone backfill script. Matches legacy rows to ZIPs using generic keyword extraction. Sets column only on unambiguous single-match. Reports ambiguous/no-match rows without writing. |
| `docker-compose-tour-id-resolution.yml` | Added DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT env vars so the containerized service can reach postgres. |
| `tests/test_local50_deterministic_resolution.py` | 6-test regression suite (column resolution, fallback single match, ambiguity error, collision test, no hardcoded venues, HTTP 409). |

## Evidence: Tours 21, 24, 27, 28, 29 resolve correctly

Live run against the running service (new code, migration applied, zip_filename populated):

```
--- Tour 21 ---
{
    "directory_name": "Asian arts museum, nice, France_9cb7181b",
    "download_id": 21,
    "edit_tour_id": "9cb7181b",
    "editable": true,
    "resolution_method": "column",
    "status": "success",
    "stops_count": 6,
    "tour_name": "Asian arts museum, nice, France - museum Tour"
}

--- Tour 24 ---
{
    "directory_name": "musée_marc_chagall_nice_france_museum_c3101e45",
    "download_id": 24,
    "edit_tour_id": "c3101e45",
    "editable": true,
    "resolution_method": "column",
    "status": "success",
    "stops_count": 6,
    "tour_name": "Musée Marc Chagall, Nice, France - museum Tour"
}

--- Tour 27 ---
{
    "directory_name": "Alpha Asian Arts Museum Nice_9392ad2f",
    "download_id": 27,
    "edit_tour_id": "9392ad2f",
    "editable": true,
    "resolution_method": "column",
    "status": "success",
    "stops_count": 8,
    "tour_name": "Alpha Asian Arts Museum Nice"
}

--- Tour 28 ---
{
    "directory_name": "Bravo Asian Arts Museum Nice_53b1a41a",
    "download_id": 28,
    "edit_tour_id": "53b1a41a",
    "editable": true,
    "resolution_method": "column",
    "status": "success",
    "stops_count": 8,
    "tour_name": "Bravo Asian Arts Museum Nice"
}

--- Tour 29 ---
{
    "directory_name": "French Riviera Biking Tour_c6195a89",
    "download_id": 29,
    "edit_tour_id": "c6195a89",
    "editable": true,
    "resolution_method": "column",
    "status": "success",
    "stops_count": 15,
    "tour_name": "French Riviera Biking Tour"
}
```

All five resolve via `column` method. Edit tour IDs and stop counts match the pre-change baseline.

## Evidence: Deliberate collision test

Tours 27 ("Alpha Asian Arts Museum Nice") and 28 ("Bravo Asian Arts Museum Nice") share their first two long keywords (`asian`, `arts`). Under the old code, both would match all Asian arts ZIPs and resolve to whichever `iterdir()` yielded first.

```
=== COLLISION TEST: Tours 27 and 28 ===
Tour 27: 'Alpha Asian Arts Museum Nice'
Tour 28: 'Bravo Asian Arts Museum Nice'

These share keywords 'asian' and 'arts' (first two >3 char words).
Under OLD code: both would match ALL Asian arts ZIPs → first-iterdir-wins coin flip
Under NEW code: each resolves to its stored zip_filename

=== VERIFY DISTINCT ZIPS ===
✅ PASS: Tour 27 → Alpha Asian Arts Museum Nice_9392ad2f
✅ PASS: Tour 28 → Bravo Asian Arts Museum Nice_53b1a41a
Tours resolve to DIFFERENT ZIPs as expected.
```

## Evidence: Regression suite

```
======================================================================
LOCAL-50: Deterministic Tour→ZIP Resolution Tests
======================================================================

=== TEST 1: Column-based resolution ===
  ✅ Resolved via column: edit_tour_id=a1b2c3d4
  PASSED

=== TEST 2: Filesystem fallback (single match) ===
  ✅ Fallback resolved: edit_tour_id=9cb7181b
  PASSED

=== TEST 3: Ambiguous resolution → error ===
  ✅ Ambiguity detected: ['asian_arts_museum_nice_evaluation_a_ff11ee22', 'asian_arts_museum_nice_france_9cb7181b']
  PASSED

=== TEST 4: Collision test — two similar names, both resolve correctly ===
  ✅ Tour A → aaaa1111 (asian_arts_museum_nice_evaluation_a_aaaa1111.zip)
  ✅ Tour B → bbbb2222 (asian_arts_museum_nice_evaluation_b_bbbb2222.zip)
  PASSED

=== TEST 5: No hardcoded venue names ===
  ✅ No hardcoded Boston-area venue names in source
  PASSED

=== TEST 6: HTTP 409 on ambiguity ===
  ✅ Got 409 with 2 candidates
  PASSED

======================================================================
RESULTS: 6 passed, 0 failed, 6 total
======================================================================
```

## Evidence: Full resolution table (all DB tours)

```
ID | STATUS               | ZIP                                        | STOPS | METHOD
---|----------------------|--------------------------------------------|-------|--------
1  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback (16 palais ZIPs)
2  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
3  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
4  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
5  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
6  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
7  | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
8  | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
9  | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
10 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
11 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
12 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
14 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
17 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
19 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
20 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
21 | success              | Asian arts museum, nice, France_9cb7181b   | 6     | column
22 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
23 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin, no ZIP
24 | success              | musée_marc_chagall_nice_france_museum_c3101e45 | 6 | column
27 | success              | Alpha Asian Arts Museum Nice_9392ad2f      | 8     | column
28 | success              | Bravo Asian Arts Museum Nice_53b1a41a      | 8     | column
29 | success              | French Riviera Biking Tour_c6195a89        | 15    | column
30 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin translation
31 | EDIT_ID_NOT_FOUND    | —                                          | —     | French translation
32 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin translation
33 | EDIT_ID_NOT_FOUND    | —                                          | —     | French translation
34 | EDIT_ID_NOT_FOUND    | —                                          | —     | non-Latin translation
35 | EDIT_ID_NOT_FOUND    | —                                          | —     | French translation
36 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
37 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
39 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
40 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
41 | AMBIGUOUS_RESOLUTION | —                                          | —     | fallback
```

No two IDs share a ZIP. Legacy rows without `zip_filename` that have multiple candidate ZIPs report AMBIGUOUS_RESOLUTION (409) rather than guessing. Non-Latin translation rows and rows with no matching ZIP on disk get EDIT_ID_NOT_FOUND (404).

## What is NOT proven

- The backfill script was run in `--dry-run` mode only. It correctly identifies 16 ambiguous and 13 no-match legacy rows. The 5 acceptance-criteria tours were manually set. Full backfill of ambiguous rows requires human decision on which ZIP is canonical for each legacy tour.
- Tours 7, 9, 11, 19, 20, 22, 23, 30–35 are translations (Russian/French) with no corresponding ZIP file on disk. These are expected to remain unresolvable until their parent English tour's ZIP is associated.
