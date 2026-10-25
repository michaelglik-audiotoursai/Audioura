# SUBMISSION — LOCAL-765

**Storied must never serve or reuse a Subscribed tour — track-scoped lookup + read-path isolation** (backport of LOCAL-727 to `storied`)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-765-storied-track-isolation`
**Base:** `storied` = `354da345` — `git merge-base --is-ancestor 354da345 HEAD` → exit 0 (verified)
**code_sha (base):** `354da3456ad226ed203b375d4e2e2bcce9117630`
**code_sha (this change):** the tip of `LOCAL-765-storied-track-isolation`. The WIP tip handed over was `2be965fe` (saved by LEAD); this submission verifies it, fixes three serving-path gaps it missed, fixes one regression, and documents the whole.
**Ruling:** D712, D708, D678/D689 (not edited; see note below)

> **Note on the base.** The worktree is checked out at local `storied` = `354da345`.
> `origin/storied` (`d5e6d62f`) is 7 commits *ahead on a divergent line* that local
> `storied` does not have (GCS‑C1 coordinate guard, BUILD_NUMBERS, remind_mobile_ai,
> GCLOUD_STORIED_START_HERE), so `git diff origin/storied..HEAD` is misleading — it shows
> those 7 commits as deletions. The real change set is `354da345..HEAD` (per the BASE
> instruction and D358: never measure against the stale `origin`). All comparisons below
> use `354da345` as the baseline.
>
> **Note on the rulings.** D712/D708/D678/D689 are newer than this base — `DECISIONS.md` at
> `354da345` ends at D611 — so they could not be read here and were not edited. The task
> description carries their intent (D708: Subscribed shares the GCloud Cloud SQL DB with
> Beta/Storied, writing `track='subscribed'`), which this change implements.

---

## 1. The problem

After the Subscribed → GCloud Cloud SQL move (**D708**), Beta, Storied and Subscribed are
separate Cloud Run services that **share one `audio_tours` table**, each writing its own
`track` (`'beta'` / `'storied'` / `'subscribed'`). On `storied` (`354da345`):

- **Write/lookup:** `tour_orchestrator_service.store_audio_tour` keyed the existing-tour
  lookup on `lower(tour_name)` **alone** (no track, no creator). A Storied store of
  "Salem Witch Museum" would **match and reuse a same-name Subscribed row**, returning its
  id as `already_exists` — handing a Storied listener a members-only/paid Subscribed tour
  for free (and, for Beta vs Storied, collapsing two tours into one — the LOCAL-432 bug this
  backports).
- **Read paths:** every storied-side `SELECT ... FROM audio_tours` had no track predicate,
  so `/tours-near`, `/search`, `/download-tour/<id>`, `/tour-info`, `/tour-by-code`,
  tour-id resolution and the translation service would all surface Subscribed rows.

## 2. The fix

**Rule:** every storied-side query on `audio_tours` is track-isolated. The store lookup is
scoped to this deployment's own track; every read excludes `track = 'subscribed'`
(`track IS NULL OR track <> 'subscribed'` — NULL = legacy pre-track rows = Beta, kept). A
download/resolve by id of a Subscribed row finds nothing → the handler's 404.

**Deviation from LOCAL-727 (on `subscribed`):** that branch keyed on
`(lower(tour_name), creator_user_id, track)` because it has D678's `creator_user_id` column.
`storied` has **no `creator_user_id`** column in this path, so the key here is
`(lower(tour_name), track)` — track is the only scoping dimension storied has. No Subscribed
tables are added (not storied's concern).

**Column guard / self-heal.** The `track` column is self-healed (additive, idempotent) by
the orchestrator before the lookup, and every read-path exclusion is guarded on the column
existing — on a DB that never had `track`, no Subscribed row can exist, so the predicate is
omitted rather than 500-ing a shared Beta+Storied endpoint. In `tour_id_resolution_service`
the guard is a `SAVEPOINT` + `UndefinedColumn` fallback that re-runs the original unscoped
query, keeping the caller's transaction usable and consuming exactly one `fetchone()`.

### Files changed (committed to `LOCAL-765-storied-track-isolation` only)

| File | Change |
|---|---|
| `tour_orchestrator_service.py` | store lookup + post-store re-read track-scoped; **`/download/<job_id>` serve-by-id excludes subscribed (gap fixed)** |
| `map_delivery_service.py` | `_exclude_subscribed_sql()` helper; applied to all 10 reads |
| `map_delivery/app.py` | same helper; applied to all 5 reads (deployed via `docker-compose-beta-local.yml` / `-master.yml`) |
| `sharing_endpoints.py` | `/share` builds no share from a subscribed tour |
| `tour_editing_phase2.py` | `_exclude_subscribed_sql()` helper; applied to the read paths |
| `tour_id_resolution_service.py` | `_resolve_from_column` + **filesystem fallback + `/tour/<id>/resolve` (2 gaps fixed)**; `_fetchone_excluding_subscribed` helper |
| `translation-service/translation_service.py` | excludes subscribed originals; **translations inherit the original's track** |
| `migration/sql/043_tour_track.sql` | adds `idx_audio_tours_name_track` on `(lower(tour_name), track)` (LEAD applies at merge) |
| `tests/test_local765_subscribed_isolation.py` | red/green + unchanged-behaviour guards |
| `SUBMISSION_LOCAL-765.md` | this file |

### Three serving-path gaps the handed-over WIP (`2be965fe`) missed — now fixed

1. **`tour_orchestrator_service.py` `/download/<job_id>`** (`SELECT tour_name, audio_tour …
   WHERE id = %s`): the DB-backed serve path for a numeric id. Unguarded, it served a
   Subscribed tour's audio by id. Fixed with the self-heal-guarded exclusion → subscribed id
   404s.
2. **`tour_id_resolution_service.py` filesystem fallback** (`SELECT tour_name … WHERE id`):
   the WIP guarded `_resolve_from_column` (primary) but not the fallback, which would still
   resolve a Subscribed id. Fixed.
3. **`tour_id_resolution_service.py` `/tour/<id>/resolve`** (`SELECT tour_name … WHERE id`):
   unguarded. Fixed. (Also removed a duplicate `cur = conn.cursor()` here.)

## 3. The query list — every `FROM audio_tours` on storied-side serving code

**Live storied services** (`docker-compose.yml` commands): tour_generation, tour_orchestrator,
map_delivery, coordinates, treats, news_*, polly_tts, tour_editing_simple,
tour_generation_modernized, tour_editing_phase2, translation-service. `map_delivery/app.py`
is deployed via `docker-compose-beta-local.yml:197` (`build ./map_delivery`) and
`docker-compose-master.yml:250`. `tour-id-resolution` has its own compose (port 5025).

### Track-isolated (this change)

- **`tour_orchestrator_service.py`**
  - `:622` store existing-tour lookup — `AND track = %s` (this deployment's track)
  - `:1292` post-store `english_tour_id` re-read — `AND track = %s`
  - `:2085` `/download/<job_id>` serve-by-id — excludes `subscribed` *(gap fix)*
- **`map_delivery_service.py`** — all 10 reads exclude `subscribed`:
  `:202` /tours-near, `:300` resolve_tour_id, `:364` download-tour, `:456` search-tours,
  `:536` get_tour_version, `:588` check_multiple_versions, `:628` tour-info,
  `:713` extract_tour_stops, `:819` get_tour_edit_info, `:942` create_custom_tour
- **`map_delivery/app.py`** — all 5 reads exclude `subscribed`:
  `:80` tour-by-code, `:220` tours-near, `:289` download-tour, `:362` tour-info, `:419` search
- **`sharing_endpoints.py`** — `:106` /share source lookup excludes `subscribed`
- **`tour_editing_phase2.py`** — `:520` source content-language, `:580`/`:586` resolve-from-db,
  `:652` resolve-numeric-to-uuid, `:2369` promote scoring read — all exclude `subscribed`
- **`tour_id_resolution_service.py`** — `:105` `_resolve_from_column` (SAVEPOINT), `:230`
  filesystem fallback *(gap fix)*, `:312` `/tour/<id>/resolve` *(gap fix)*. (`:114` is the
  unscoped fallback inside the SAVEPOINT try/except, reached only when `track` doesn't exist.)
- **`translation-service/translation_service.py`** — `:239` original-tour read excludes
  `subscribed` and selects `track` (index 11) so the translation **inherits the original's
  track**

### Deliberately NOT changed (justified)

- **`tour_editing_phase2.py:2302`/`:2341`** — `promote_custom_tour` **name-uniqueness** check
  (`WHERE LOWER(tour_name)=LOWER(%s) AND original_tour_id IS NULL`). Write-side conflict guard,
  not a content serve; a same-name Subscribed row *should* still block to protect the shared
  unique-name index. No tour is served.
- **`translation_service.py:286`** — child-translation existence check
  (`WHERE original_tour_id = %s AND content_language = %s`). Reached only *after* the original
  passed the `subscribed` exclusion at `:239`, so a Subscribed original never gets here.
- **`amenities_near_service.py:87`** — `is_museum_tour` reads only `tour_name` to classify;
  serves no content, and the service is not in storied's `docker-compose.yml`.
- **`tour_worker_service.py:172`/`:209`** — an older generation worker whose store lookup is
  keyed on `(tour_name, request_string)` and is **not** track-scoped. It is referenced **only**
  in `docker-compose-beta-local.yml`, is **not** in storied's `docker-compose.yml`, is not
  imported by any live service, and is not named in this task. Flagged here as a follow-up
  (it would collapse same-name rows across tracks if ever run against the shared DB), but out
  of scope for this storied backport.
- **`run_*.py`, `tests/run_local*.py`** — developer harness scripts against throwaway/local
  DBs; not serving code.
- **`tour_editing_simple.py`** — a live storied service, but it has **no** `audio_tours` query.
- Code-generator scripts (`create_/extend_/improve_/safe_extend_/modified_*map_delivery*`,
  `extend_existing_app.py`, top-level `app.py`) — not run by any compose; they emit service
  code, they are not the running services.

## 4. Migration 043 — KEEP (and why)

`migration/sql/043_tour_track.sql` is kept for storied. Reasoning:

- The orchestrator **self-heals** the `track` column, so the code is correct **without** the
  migration — the migration only makes the new lookup key
  `(lower(tour_name), track) WHERE original_tour_id IS NULL` **fast** (it is now the hot path
  for every store; without an index it is a full scan).
- Adapted for storied: it creates `idx_audio_tours_name_track` on `(lower(tour_name), track)`
  (not LOCAL-727's creator-scoped index — storied has no `creator_user_id` here) and
  **drops no 041 index** (storied never had the creator index).
- Additive, idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) and
  reversible (the exact `DROP INDEX` is in a comment). LEAD applies it at merge.

## 5. Translations inherit the original's track — VERIFIED

`translation_service.py` now selects `track` as index 11 of the original-tour row (excluding
subscribed originals), and both the main path (`:361`) and the fallback path (`:1740`) set the
new translation's `_track` from `original_tour[11]` instead of this deployment's `TOUR_TRACK`
env. A translation of a Beta tour is Beta; of a Storied tour, Storied; a Subscribed original is
refused before this point, so the value is only ever `beta`/`storied`.

## 6. Red tests + baseline comparison

**Test:** `tests/test_local765_subscribed_isolation.py` (10 tests). Drives the **real** service
handlers (loaded by file path, `get_db_connection` monkeypatched to a pinned connection) and
the **real** `store_audio_tour`, against an ISOLATED throwaway schema.

> **Runner:** use `python3 -m unittest tests.test_local765_subscribed_isolation`. Under
> `pytest` the module-level schema setup does not take for the handler clients and every test
> errors with `relation "audio_tours" does not exist`; `unittest` runs `setUpModule`/the
> role search_path correctly. Env:
> `LOCAL765_DB_HOST=localhost LOCAL765_DB_PORT=5465 LOCAL765_DB_NAME=audiotours_local765 LOCAL765_DB_USER=admin LOCAL765_DB_PASSWORD=password123`.

### RED — baseline `354da345` (worktree `/tmp/local765-baseline`, this test file copied in)

```
Ran 10 tests
FAILED (failures=8)
```
The 8 failures are exactly the LOCAL-765 bugs:
- `/tours-near` lists the subscribed tour (`'subscribed' in {'storied','beta','subscribed'}`)
- `/search-tours` returns the subscribed id
- `/download-tour`, `/tour-info`, `/tour/<id>/resolve`, `/tour-by-code` of a subscribed id → `200 != 404`
- storied store **reuses** the subscribed row (`'already_exists' != 'inserted'`; `sub_id == sub_id`)
- beta + storied same-name **collapse** (`'already_exists' != 'inserted'`)

The 2 that pass on baseline are the unchanged-behaviour guards (same-track regeneration
versions one row).

### GREEN — this branch

```
Ran 10 tests
OK            # 10/10
```
Storied store over an existing subscribed row → `action='inserted'`, a NEW storied row; the
subscribed row survives untouched; same-track regeneration still versions one row; beta+storied
remain two rows.

### Regression (existing suites, branch vs baseline `354da345`, identical results)

| Suite | Result |
|---|---|
| `test_local50_deterministic_resolution` | 6/6 pass (see note) |
| `test_local476_orchestrator_empty_type` | 5/5 pass |
| `test_local325_lazy_resolution` | 5/5 pass |
| `test_local153_tour_editing_shims_guard` | 2/2 pass |
| `test_translation_implementation` | 2/2 pass |
| `test_orchestrator_pipeline` | 1/1 pass |
| `test_tour_editing` | 1 error — **identical on baseline** (pre-existing live-endpoint fixture error, not this change) |

> **Regression caught and fixed during this work.** My first version of the
> `tour_id_resolution_service` guard did a separate `information_schema` probe, which consumed
> an extra `fetchone()` from `test_local50`'s mock cursor and broke 3 of its 6 tests. I
> replaced it with `_fetchone_excluding_subscribed(cur, base_sql, params)` — mirroring
> `_resolve_from_column`'s `SAVEPOINT` + `UndefinedColumn` fallback, consuming exactly one
> `fetchone()` and adding no catalog round trip. `test_local50` is now 6/6, matching baseline.

## 7. Live test & cost

- **Own container only:** a scratch Postgres `local765-scratch-pg` (`postgres:13`,
  db `audiotours_local765`, port **5465**) — a dedicated container, never `-p audioura`, never
  renaming/replacing `audioura-*`, never the shared DB.
- Each run creates a **uniquely-named throwaway schema** it owns and **drops** in teardown;
  the role's `search_path` is reset. The real handlers run against seeded rows in that schema.
- **Isolation verified after the runs:** no leftover `local765_*` schemas; role `search_path`
  config back to `None`; `public.audio_tours` count `0` in the scratch DB (tests only ever used
  throwaway schemas); the container is not an `audioura-*` one.
- **$ spent: $0.00.** No tour generation, no model/API calls. `store_audio_tour()` is driven
  with a tiny fixture ZIP (`index.html` + a 2-byte mp3). Budget respected.

## 8. Process

Committed to `LOCAL-765-storied-track-isolation` only (named files, **no `git add -A`**). No
edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, or `GCLOUD_STORIED_START_HERE.md`. Branched from local
`storied` HEAD (`git merge-base --is-ancestor 354da345 HEAD` → exit 0), never from
`origin/storied`. Pushed `origin LOCAL-765-storied-track-isolation`.
