# SUBMISSION — LOCAL-792: incorrect stops leave the pool; far-away stops stay

**Branch:** `LOCAL-792-stop-quarantine` (base `subscribed` @ `acc75176`)
**Michael:** "Why do we keep incorrect material for future usage?"

Tour 463 (War Remnants Museum, Subscribed Preview) reused two bad stops from
`stop_pool` — a news headline ("Khai mạc Hội thảo Quốc tế …") and Independence
Palace (a real place, but filed under the wrong venue). The pool kept whatever a
delivered tour contained; nothing ever marked a stop bad. This change gives the
pool a notion of "incorrect; never reuse", under the three-case ruling D726 (as
amended by Michael 2026-10-27).

## Ruling (D726 amended) — three cases, three actions

| case | example | action | where |
|---|---|---|---|
| Out of scope for THIS tour | Byblos (Norwood) for West Roxbury | **skip this tour only, keep in pool** | LOCAL-788 (`_revalidate_pooled_scope`) — NOT this ticket's move |
| Wrong pin | 461 Opera House 0.7 km off | **correct coords in place, keep** | `fix_stop_coords.py` |
| Incorrect content | news headline, "Interesting", "Balcony", fabricated fact | **MOVE out of pool → `stop_pool_rejected`** | `reject_stops.py --apply` / auto-reject |
| Filed under wrong venue | Independence Palace in a War Remnants tour | re-file if it resolves to one place, else treat as incorrect content | human re-file / reject |

## What this delivers

1. **Migration `migration/sql/056_stop_pool_rejected.sql`** (additive) — table
   `stop_pool_rejected` = all `stop_pool` columns + `reject_reason`,
   `rejected_by`, `rejected_at timestamptz`, `source_tour_id int`; PK
   `(pool_key, title_norm)`; two indexes. `CREATE … IF NOT EXISTS` +
   guarded `ALTER ADD COLUMN`, one transaction, idempotent. No DROP/DELETE; never
   touches `audio_tours`.

2. **`stop_pool_rejected.py`** — the ONLY place a `stop_pool` row is removed, and
   only after a verified copy, in ONE transaction (`move_to_rejected`: copy →
   verify copy count == intended → delete, else raise/rollback). `restore_from_rejected`
   is the exact inverse. Plus the SKIP lookups (`rejected_title_norms`,
   `rejected_norms_by_identity`) every reuse read and the LOCAL-778 miner use.

3. **`reject_stops.py`** `--tour-id N [--stop K …] --reason "…" --by <who>` —
   dry-run by default; `--apply` does the verified copy-then-remove in one
   transaction; `--restore` moves rows back. Prints both tables' row counts
   before/after. Never touches `audio_tours`.

4. **`fix_stop_coords.py`** `--tour-id N --stop K` — re-geocode the place and
   UPDATE coords in place (pool row + the tour's stored `Coordinates:` line).
   UPDATE only; never INSERT/DELETE/move. Prints old/new coords and distance moved.

5. **Automatic, no human** (`stop_pool_orchestrator._auto_reject_junk_titles`) —
   a reuse candidate failing the LOCAL-791 junk-title / other-venue check is MOVED
   to `stop_pool_rejected` (reason `auto:junk_title_or_other_venue`, by
   `auto:junk_title_guard`) and dropped from this tour. A SCOPE/distance failure
   is NOT moved — skip-only (LOCAL-788). The miner skips any rejected
   `(venue identity, title_norm)` so a quarantined stop can't walk back in from a
   delivered tour.

6. **Seed `reject_seed_2026-10-27.txt`** — applied LATER by GCloud_Storied with
   Michael's OK (not run by the build): 463 news headline + "Interesting" →
   reject; 463 Independence Palace → re-file; 461 "Balcony" → reject; 461 Opera
   House / Ben Thanh / War Remnants → fix coords; Byblos → nothing.

## LEAD note — production lock fix (18:5x / 19:3x)

The 18:5x hang: a runtime `ALTER TABLE stop_pool ADD COLUMN IF NOT EXISTS …` in
`stop_pool_store._ensure_table` takes `ACCESS EXCLUSIVE`; with any connection idle
in a transaction holding a lock on the table, the ALTER waits forever AND its
queued `ACCESS EXCLUSIVE` request blocks every reader behind it — stalling every
generator.

Fix (per the note's option "set lock_timeout around runtime DDL"): the
lock-taking DDL in `stop_pool_store._ensure_table` and
`stop_pool_rejected.ensure_table` now runs inside a `SAVEPOINT` with
`SET LOCAL lock_timeout = '3s'`. On a lock timeout the DDL rolls back to the
savepoint and the caller carries on — the columns already exist on any migrated
DB (authoritative schema is migration 056 + the earlier 0xx files), so the read
path is unaffected. The 19:3x test fix (`_current_schema` COMMITs before the code
under test opens its own connection) is kept.

**Verified live** against a throwaway Postgres: with a connection idle in a
transaction holding `ACCESS SHARE` on `stop_pool` (the exact 18:5x shape), the
old code would wait forever; with the fix `_ensure_table` returns in **3.01 s**
(`ok=True`) instead of hanging, and a healthy DB still applies every additive
column.

## Tests — all green

### Unit (`tests/test_local792_stop_quarantine.py`), DB-backed (throwaway schema)
```
6 passed in 0.44s
  TestRejectedNeverReused::test_get_pool_stops_excludes_rejected   PASSED
  TestRejectedNeverReused::test_miner_skips_rejected               PASSED
  TestRestore::test_restore_round_trip_intact                      PASSED
  TestScopeFailureDoesNotMove::test_revalidate_scope_never_rejects_from_pool PASSED
  TestCopyCountMismatchAborts::test_mismatch_raises_and_pool_unchanged PASSED
  TestAutoRejectJunkTitles::test_junk_title_moved_good_kept        PASSED
```
Covers the four required properties: (1) a rejected row is never returned by any
reuse path; (2) `--restore` brings it back intact; (3) a scope failure does NOT
move the row; (4) a copy-count mismatch aborts the transaction.

### Regression vs baseline (same empty throwaway Postgres)
Selection: LOCAL-597 / 778 / 786 / 788 + every `stop_pool` test + LOCAL-792.

| | passed | errors |
|---|---|---|
| baseline `acc75176` (unmodified) | 69 | 20 |
| this branch | 75 | 20 |

The 20 errors are identical on both and are environmental — the `_isolated_db`
harness clones `LIKE public.<t>` and the throwaway DB has no seeded `public`
proof tables (`audio_tours`, `users`, …). **Zero NEW failures.** The +6 passing
are the new LOCAL-792 unit tests.

### Migration idempotency
`056_stop_pool_rejected.sql` applied twice against a real Postgres: first run
creates everything; second run only NOTICEs "already exists". Schema verified:
all stop_pool columns + `reject_reason`/`rejected_by`/`rejected_at`/`source_tour_id`,
PK `(pool_key, title_norm)`, both indexes.

## Live test (own isolated schema, `-p local792` discipline)

Seed a pool with a GOOD and a BAD stop, reject the BAD one, request the same
venue via the real reuse read (`get_pool_stops`):

```
seeded pool rows: 2  (GOOD='Independence Palace',
                      BAD='Khai mạc Hội thảo Quốc tế về Biển Đông')
reject moved: 1 row(s)
after reject:  stop_pool=1   stop_pool_rejected=1
reuse returned 1 stop(s): ['Independence Palace']
GOOD stop present in reuse: True
BAD stop EXCLUDED from reuse: True
miner reject-skip set contains BAD: True
VERDICT: PASS
```

Row counts: `stop_pool` 2 → 1, `stop_pool_rejected` 0 → 1 (one moved, nothing
lost). During the reuse read the 18:5x shape occurred naturally (an open
transaction held a lock); the DDL failed fast and the read still returned the
correct result — the lock fix proving itself live.

**Paid-API spend: $0.00** (seeded pool; no geocoding / LLM calls). Well under the
$1.00 cap.

## Files

New:
- `migration/sql/056_stop_pool_rejected.sql`
- `stop_pool_rejected.py`
- `reject_stops.py`
- `fix_stop_coords.py`
- `reject_seed_2026-10-27.txt`
- `tests/test_local792_stop_quarantine.py`

Modified:
- `stop_pool_store.py` — reuse SKIP of rejected rows in `get_pool_stops`;
  `lock_timeout` + savepoint around runtime DDL in `_ensure_table` (18:5x fix).
- `stop_pool_orchestrator.py` — `_auto_reject_junk_titles` (automatic
  incorrect-content reject) wired into `maybe_generate_with_pool`; miner skips
  rejected `(venue identity, title_norm)` in `_reuse_first_existing_tour_rows`.

The only removal of a `stop_pool` row is the verified copy-then-remove move; no
other DELETE, and `audio_tours` is never touched.
