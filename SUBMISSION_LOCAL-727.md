# SUBMISSION — LOCAL-727

**Two tracks, same tour name: never one merged row** (ClickUp wdvrdaz108, bug 432)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-727-track-name-key`
**Base:** `subscribed` = `46301f3d` (`git merge-base --is-ancestor 46301f3d HEAD` → exit 0)
**code_sha (base):** `46301f3dca17aec17e6286f6ee8264ce81285ff7`
**code_sha (this change):** the tip commit of `LOCAL-727-track-name-key` (this commit). Base is `46301f3d`.

---

## 1. The decision point in code

`tour_orchestrator_service.store_audio_tour` decides **new row vs. update** with a
single SELECT. Before this change (base `46301f3d`):

```python
# WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s
#   AND original_tour_id IS NULL
cur.execute(
    "SELECT id, tour_content, zip_filename, stops_count, lat, lng "
    "FROM audio_tours "
    "WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s "
    "AND original_tour_id IS NULL",
    (tour_name, _creator_user_id)
)
existing_tour = cur.fetchone()
```

If `existing_tour` is truthy the code takes the **replace/increment** branch
(LOCAL-606): it archives the old version, renames the old ZIP `<name>.v<N>.zip`
and overwrites `tour_content`, `audio_tour`, `zip_filename`, `stops_count`. If it
is `None` it falls through to **INSERT** a new row.

D678 / migration 041 made the lookup creator-scoped. **It does not include
`track`.** `track` ('beta' | 'storied') is **per-deployment**, not per-request:
Beta and Storied are separate Cloud Run services (TRACK_B_STORIED_VS_BETA.md)
that each always write their own value — into the **same shared GCloud DB**. In
the base code `_track` was only computed later, inside the INSERT path, so it had
no bearing on which row the lookup matched.

**Consequence (432):** a Beta tour and a Storied tour with byte-identical names,
the same (non-NULL) creator, generated ~1 s apart. The Storied store's lookup
matched the Beta row through this track-unaware, creator-scoped key and
**REPLACED** it — mixing columns and archiving the Beta ZIP — so the Beta tour
vanished while the job reported success.

(The NULL-creator case was already safe: `creator_user_id = NULL` matches no row
in SQL, so a NULL-creator store always inserts. The collapse requires a shared
**non-NULL** creator.)

A second, post-store lookup re-reads `english_tour_id` for a fresh insert; it was
creator-scoped but also track-unaware, so it too could pick the wrong track's row.

## 2. The fix

`tour_orchestrator_service.py` (+81 / −22):

1. **`store_audio_tour(..., track=None)`** — new optional parameter, documented.
   `None` falls back to the `TOUR_TRACK` env var (unchanged default behaviour);
   any value other than `beta`/`storied` is normalised to `beta`.
2. **Resolve `_track` BEFORE the lookup** (single source of truth) and
   **self-heal the `track` column** there (additive, idempotent) so the
   track-scoped lookup works on any Postgres.
3. **Add `track` to the lookup key** and take a **row lock**:
   ```sql
   WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s
     AND track = %s AND original_tour_id IS NULL
   FOR UPDATE
   ```
   A different track now always falls through to INSERT and gets its own row.
   `FOR UPDATE` serialises two concurrent stores of the **same** (name, creator,
   track) on the existing row so they version it one at a time instead of racing
   to replace it and mixing columns.
4. The **INSERT path reuses that one `_track`** (removed the duplicate
   `os.getenv` recompute), so the row is stored under the exact track the lookup
   keyed on.
5. The **post-store `english_tour_id` re-read** is now track-scoped too (both the
   non-NULL-creator and NULL-creator branches), resolving the same track.
6. The **call site** passes `track=` explicitly (resolved from `TOUR_TRACK`) so
   the store and the re-read key on the same value.

`migration/sql/043_tour_track.sql` (new): ensures the `track` column (additive),
creates `idx_audio_tours_name_creator_track` on
`(lower(tour_name), creator_user_id, track) WHERE original_tour_id IS NULL`, and
drops the superseded 041 `idx_audio_tours_name_creator`. Idempotent and
reversible (the reverse statement is in a comment beside the DROP). **LEAD applies
this at merge**; the orchestrator self-heals the column, so the code is correct
even before the index exists (the index only makes the lookup fast).

## 3. Red / green

Test: `tests/test_local727_track_name_key.py` (throwaway Postgres schema via
`tests/_isolated_db.py`; teardown DROPs the schema and asserts public row counts
are identical before/after — **no DELETE anywhere, no production write**).

### RED (base code, unfixed)

```
test_migration_043_idempotent            SKIPPED   (migration not present)
test_same_track_same_creator_versions_one_row  PASSED
test_two_tracks_null_creator_two_rows    PASSED    (NULL creator already safe)
test_two_tracks_same_creator_two_rows    FAILED
    AssertionError: 'replaced' != 'inserted'
```

Captured orchestrator log on the failing test (the collapse):

```
Existing tour (creator-scoped check, creator='creator-aae7537d'): None     # beta INSERT, id=7168
Existing tour (creator-scoped check, creator='creator-aae7537d'): 7168     # storied MATCHED beta row
[LOCAL-606] Tour id=7168 regenerated with DIFFERENT text ... Replacing stored content; archiving old version.
[LOCAL-606] Renamed superseded ZIP beta.zip -> beta.v1.zip
==== AUDIO TOUR CONTENT REPLACED — id=7168 ====
```

→ ONE row, Beta tour archived away. Bug 432 reproduced.

### GREEN (fixed code)

```
test_migration_043_idempotent                  PASSED
test_same_track_same_creator_versions_one_row   PASSED
test_two_tracks_null_creator_two_rows           PASSED
test_two_tracks_same_creator_two_rows           PASSED
====================== 4 passed in 0.46s ======================
```

Captured orchestrator log on the now-passing test:

```
Existing tour (creator+track-scoped check, creator='creator-295f45a8', track='beta'): None
Inserted new tour: LOCAL727 Venue bee292d0 (zip=beta.zip)       # row 1
Existing tour (creator+track-scoped check, creator='creator-295f45a8', track='storied'): None
Inserted new tour: LOCAL727 Venue bee292d0 (zip=storied.zip)    # row 2
```

The GREEN test asserts: **row count +2**; one row per track; each row its own
`track`, `storied_mode` (beta=false, storied=true), `lat`/`lng` (42.1/−71.1 vs
48.8/2.3), `stops_count` (4 vs 7), `zip_filename` (beta.zip vs storied.zip); and
the Beta row byte-for-byte unchanged (nothing archived, `number_requested` not
bumped). `test_same_track_same_creator_versions_one_row` proves the legitimate
same-track regeneration still versions the single row (action `replaced`).

### Isolation proof (every run)

```
[LOCAL-727] public row counts before/after (must be identical):
  public.audio_tours          before=0        after=0
  public.audio_tour_versions  before=0        after=0
  public.shared_tours         before=0        after=0
[LOCAL-727] OK — zero shared/production writes.
```

### Regression checks

- `tests/test_local718_tour_creator.py` — **6/6 PASSED**: creator scoping intact.
- `tests/test_local606_replace_on_change.py` — 4 failed / 1 passed, **but these
  fail IDENTICALLY on the unfixed base code** (verified by `git stash` of my
  change and re-running). They are a pre-existing NULL-creator interaction from
  LOCAL-718 / 041 (the 606 suite uses a NULL creator, which the creator-scoped
  lookup never matches), **not** caused by this change.

## 4. Row counts & cost

- **Row counts:** two tracks → **+2 rows** (one per track), vs. the base code's
  collapse to **1 row**. Isolation proof shows the public (production) tables
  unchanged: `audio_tours`, `audio_tour_versions`, `shared_tours` all 0 → 0.
- **$ spent:** **$0.00.** No live tour generation, no model/API calls, no cloud
  resources. All tests run against a local throwaway Postgres schema
  (`audiotours_test`, host port 5433). Budget ≤ $1 respected.

## 5. Files changed (committed to `LOCAL-727-track-name-key` only)

- `tour_orchestrator_service.py` — track in the lookup key + row lock; `track`
  param; track-scoped post-store re-read; self-heal.
- `migration/sql/043_tour_track.sql` — new track-aware index (LEAD applies at merge).
- `tests/test_local727_track_name_key.py` — red/green + regression guards.

No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
or SUBSCRIBED_COMMUNICATION_01.MD. ClickUp status unchanged.
