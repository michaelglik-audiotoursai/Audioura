# SUBMISSION — LOCAL-718: a tour belongs to its creator (D678)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-718-tour-creator` (from `subscribed` = `4235f353`)
**Decision:** D678 — "A tour belongs to its creator; same name ≠ same tour."

## Problem (D678)
The orchestrator's save path matched an "existing tour" by **name only**
(`lower(tour_name) WHERE original_tour_id IS NULL`) and replaced it as a new
version. The DB enforced that global, cross-user namespace with the UNIQUE index
`uq_audio_tours_original_name` on `lower(tour_name)`. So a **second** person
generating an identical name overwrote the **first** creator's tour — a paid
tour included. The table recorded no creator.

## Ruling implemented
1. Record the creator at INSERT (`audio_tours.creator_user_id`, additive, no
   backfill — existing rows stay NULL = "unknown creator").
2. New version only for the **same** creator + same name.
3. A **different** creator, or an existing **NULL-creator** row → a NEW,
   separate tour (new id, own share code). Nothing is replaced across creators.
4. Unique index → non-unique `(lower(tour_name), creator_user_id)`. The DROP is
   reversible (exact `CREATE UNIQUE INDEX …` in the migration comment). LEAD
   applies the migration after merge.

## Changes

### 1. Migration — `migration/sql/041_tour_creator.sql`
Additive and idempotent:
- `ALTER TABLE audio_tours ADD COLUMN IF NOT EXISTS creator_user_id TEXT;`
- `CREATE INDEX IF NOT EXISTS idx_audio_tours_name_creator ON audio_tours (lower(tour_name), creator_user_id) WHERE original_tour_id IS NULL;`
- `DROP INDEX IF EXISTS uq_audio_tours_original_name;` — with the exact
  `CREATE UNIQUE INDEX …` to restore it in a comment.
- No backfill.

### 2. Orchestrator save path — `tour_orchestrator_service.py`
- `store_audio_tour(...)` gains a `user_id` parameter; the caller
  `orchestrate_tour_async` forwards the job's `user_id`.
- Self-healing additive `creator_user_id` column (works on any Postgres whether
  or not migration 041 has run), and the request user_id is normalised
  (empty/whitespace → NULL).
- The existing-tour lookup is now
  `lower(tour_name) = lower(%s) AND creator_user_id = %s AND original_tour_id IS NULL`.
  SQL NULL semantics give rule 3 for free: when the request creator is NULL,
  `creator_user_id = NULL` matches no row (unknown creator always creates new);
  when it is set, a NULL-creator existing row does not match it either.
- No match → the INSERT path, which now sets `creator_user_id` in all three
  INSERT branches.
- The post-store id resolution was also made **creator-scoped**: on a replace it
  uses the id `store_audio_tour` returns; on a fresh insert it re-reads with the
  creator predicate (so an unscoped `ORDER BY id DESC LIMIT 1` can no longer pick
  the *other* creator's same-name tour).

### 3. Job-status payload — `tour_orchestrator_service.py`
- `store_audio_tour` returns `replaced_version_no` (int on a same-creator
  replace; `None` otherwise). 717 had not added a field on the orchestrator, so
  this is the single field to read.
- Surfaced on `ACTIVE_JOBS[job_id]["replaced_version_no"]` at completion and in
  the `/status/<job_id>` response (both the in-memory and database branches),
  always present on a completed job (int|null). Null = "an ordinary new tour"
  (D678 §6); int = "Updated your tour — now version N" (D677).

### 4. Promote endpoint — `tour_editing_phase2.py`
`POST /tour/<id>/promote` promotes an edited tour into `audio_tours`. It accepts
an optional `user_id`, self-heals the `creator_user_id` column, makes the
name-conflict check **creator-scoped** (a different creator is no longer blocked
by someone else's same-name tour, and a NULL request creator only conflicts with
other NULL-creator rows), and sets `creator_user_id` on INSERT. The
`UniqueViolation` fallback remains as defence (for a DB where the old unique
index has not yet been dropped) and now reports the creator-scoped conflicting
row.

## Every place that looks a tour up by name — audited
Grepped `lower(tour_name)` / `LOWER(tour_name)` across the orchestrator,
tour-generator, translation service and tour-update/map services.

| Location | Purpose | Action |
|---|---|---|
| `tour_orchestrator_service.py` store_audio_tour (~916) | existing-tour lookup for **replace/version** | **Creator-scoped** |
| `tour_orchestrator_service.py` post-store id lookup (~1888) | find the stored row's id | **Creator-scoped** + prefers the id store returns |
| `tour_editing_phase2.py` promote (~2325 & ~2363) | name-conflict check + UniqueViolation fallback | **Creator-scoped**; INSERT sets creator_user_id |
| `translation-service/translation_service.py` | attaches a translation by `content_id`/`id` → `original_tour_id` — **never by name** | No change needed (point 4 already satisfied) |
| `map_delivery_service.py` (426/451) | read-only map **search** (`LIKE`) | **Unchanged by design** — D678 shows all same-name tours under the green group marker with its list |
| `generate_tour.../generate_tour_text.py` (3476) | `LIKE '%restaurant%'` category heuristic, not a replace lookup | No change |

**Point 4 (translations):** a new same-name tour gets its own `english_tour_id`
at INSERT, and the orchestrator passes exactly that id to the translation
service as `content_id`; the service writes the translation with
`original_tour_id = <that id>`. A translation therefore always attaches to its
own parent tour's id, never to another person's tour.

## Tests — `tests/test_local718_tour_creator.py`
Run inside a throwaway Postgres schema (`tests/_isolated_db.py`); teardown drops
the schema and asserts `public` row counts are identical before/after. All 6
ticket scenarios, one test each:

```
test_1_same_creator_same_name_versions_same_id   PASSED
test_2_different_creator_new_id_first_unchanged  PASSED
test_3_null_creator_row_gives_new_id             PASSED
test_4_paid_tour_not_replaced_by_other_creator   PASSED
test_5_insert_stores_creator_user_id             PASSED
test_6_migration_idempotent                      PASSED
6 passed

[LOCAL-718] public row counts before/after (must be identical):
  public.audio_tours          before=0        after=0
  public.audio_tour_versions  before=0        after=0
  public.shared_tours         before=0        after=0
[LOCAL-718] OK — zero shared/production writes.
```

Harness notes: the cloned unique `lower(tour_name)` index is auto-renamed by
`LIKE … INCLUDING ALL`, so `setUpModule` discovers and drops **every** unique
`lower(tour_name)` index (simulating migration 041); `audiotours_test`'s
`audio_tour_versions` predates LOCAL-606's columns, so the clone is dropped and
recreated in-schema via the orchestrator's own `_ensure_versioning_objects`.

## Live test — own container, no shared DB, $0 spend
`docker run` a `postgres:15-alpine` as **`local718_pg`** on port **55718** (never
`-p audioura`, no `audioura-*` renamed), loaded from
`pg_dump --schema-only --no-owner --no-privileges` of `audiotours`.

1. **The bug, pre-migration:** with `uq_audio_tours_original_name` present, a
   second same-name original is rejected:
   `ERROR: duplicate key value violates unique constraint "uq_audio_tours_original_name"`.
2. **Migration 041 applied twice** — clean both times (2nd run only emits
   skip-notices, exit 0). Afterwards `uq_audio_tours_original_name` is gone and
   `idx_audio_tours_name_creator` exists.
3. **Two creators, same name → two rows** (raw SQL):
   ```
   id | tour_name     | creator_user_id | is_test
    1 | Freedom Trail | alice           | t
    2 | Freedom Trail | bob             | t
   ```
4. **End-to-end through the real `store_audio_tour`** (env pointed at the own
   container), name "Harbor Walk":
   - alice → `inserted` (id=3)
   - bob, same name → `inserted` (id=4) — **NOT a replace of alice**
   - alice re-generates → `replaced`, `replaced_version_no=1`
   ```
   id | tour_name   | creator_user_id | tour_content     | number_requested
    3 | Harbor Walk | alice           | Alice content v2 | 2
    4 | Harbor Walk | bob             | Bob content      | 1
   audio_tour_versions: tour_id=3 version_no=1 'Alice content'
   ```
   Alice's tour is intact and versioned; Bob's is a separate row.

Real generation was not required. Spend: **$0** (stub ZIPs + local container).
The container and all temp files were removed afterward; no `audioura-*`
container was touched.

## Files
- `migration/sql/041_tour_creator.sql` (new)
- `tour_orchestrator_service.py`
- `tour_editing_phase2.py`
- `tests/test_local718_tour_creator.py` (new)
- `SUBMISSION_LOCAL-718.md` (this file)

Not edited: DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE, `.continuous_dev`.
