# SUBMISSION — LOCAL-797: Runtime DDL + "idle in transaction" readers freeze every tour

**Branch:** `LOCAL-797-db-locks` (base: subscribed = 416555e7)
**Scope:** generator path only. No live DB writes (localhost:5433 never touched). No `DELETE`.

---

## 1. What was happening (live, Mac DB, 2026-10-28 10:55–11:12)

A 2-stop Arnold Arboretum tour sat in `poi_selection` for **26 minutes**; a P1 benchmark
tour timed out at 25 min. `pg_stat_activity` showed the generator's only open socket was
Postgres, and three things stacked up:

- **pid A** — `idle in transaction` for 17 min after a `SELECT … FROM stop_corpus …`
  (the existence gate). The read never committed, so it kept an `AccessShare` lock.
- **pid B** — `ALTER TABLE venue_corpus ALTER COLUMN tier TYPE VARCHAR(20)` waiting on a
  relation lock. `venue_resolver._ensure_table` ran this ALTER **unconditionally, once per
  process** (every generator start / Cloud Run cold start). It needs `AccessExclusive`.
- **everyone else** — every `SELECT … FROM venue_corpus` queued behind the waiting ALTER.

`AccessExclusive` requested → granted only after pid A releases → but pid A is idle forever
→ the ALTER waits → and its queued `AccessExclusive` request blocks every reader behind it.
All tours frozen. Cancelling the ALTER drained the queue instantly.

The same class bit LOCAL-792 (a `stop_pool` ALTER behind an idle-in-transaction connection;
2 h hang), which is why `stop_pool_store.py` / `stop_pool_rejected.py` were already guarded.

---

## 2. The fix

Two independent defenses so neither a runtime DDL nor a forgotten read can ever freeze a tour.

### (a) No unconditional, unguarded runtime DDL — `db_safe_ddl.py` (new)

`safe_ddl(conn, sql, needed_check_sql=None, lock_timeout='3s', statement_timeout='10s', label)`:

1. runs the DDL in its **own transaction** (saves/restores the connection's autocommit),
2. `SET LOCAL lock_timeout` (+ `statement_timeout`) so it **gives up in ~3 s** instead of
   queueing behind a reader,
3. runs an optional `needed_check_sql` first and **skips** the DDL when it is a no-op,
4. on a lock timeout (`55P03`) or statement cancel (`57014`) — or any error — **logs and
   continues**, never raises:
   `[LOCAL-797] ddl skipped <table> (lock busy)`.

Also ships `CONNECT_OPTIONS = "-c idle_in_transaction_session_timeout=60000 -c lock_timeout=3000"`
and `harden_read_connection(conn)` (sets `autocommit=True`).

### (b) No idle-in-transaction readers

- Generator connections carry `idle_in_transaction_session_timeout=60000` (the **server**
  kills a transaction left idle for a minute — belt-and-braces for Cloud Run, where we
  cannot see the process) and `lock_timeout=3000`.
- The generator's read connections are **autocommit**, so a pure SELECT never leaves a
  transaction open holding a lock.
- The existence gate (which only ever reads) calls `_end_read_txn(db_conn)` after each stop
  so a non-autocommit caller connection cannot idle-in-transaction across the whole gate run.

---

## 3. Every call site changed

| File | Change |
|---|---|
| **`db_safe_ddl.py`** *(new)* | `safe_ddl`, `CONNECT_OPTIONS`, `harden_read_connection`. |
| **`venue_resolver.py`** | `_ensure_table`: `CREATE TABLE IF NOT EXISTS` kept (takes no lock on an existing table); the `ALTER … tier` and `CREATE INDEX idx_venue_corpus_expires` now go through `safe_ddl` with an `information_schema` / `pg_indexes` `needed_check` (ALTER only when `character_maximum_length < 20`/NULL; index only when missing). `_get_db_connection`: `psycopg2.connect(..., options=CONNECT_OPTIONS)` + `autocommit=True`. |
| **`work_story_searcher.py`** | `_get_db_connection`: `options=CONNECT_OPTIONS` + `autocommit=True`. `_ensure_work_stories_table`: `CREATE TABLE` kept; both `CREATE INDEX` via `safe_ddl` (needed-check on `pg_indexes`). |
| **`passage_role_tagger.py`** | `tag_all_passages`: `ALTER TABLE stop_corpus ADD COLUMN passage_roles` via `safe_ddl` (needed-check on `information_schema`). Batch tool, but it touches `stop_corpus` which the live gate reads. |
| **`stop_existence_gate.py`** | New `_end_read_txn(db_conn)` (commits a non-autocommit read txn; no-op on autocommit); called after each verify in `run_existence_gate` (main + retry loops). |
| **`generate_tour_text.py`** | Hardened the six direct `psycopg2.connect(...)` **fallbacks** on the gate/corpus read path (`_co_conn`, `_cs_conn`, `_seg_conn`, `_rep_conn`, `_inc_conn`, `_sc_conn`) with `CONNECT_OPTIONS` + autocommit. (Their primary path uses `venue_resolver._get_db_connection`, already hardened.) |
| **`stop_pool_orchestrator.py`** | Reuse miner connection (`~989`): `options=CONNECT_OPTIONS` + autocommit (read-only SELECT over `audio_tours`, then closes). |

**Already guarded (LOCAL-792) — left unchanged, verified equivalent:**
`stop_pool_store.py` and `stop_pool_rejected.py` already wrap their `ALTER`/`CREATE INDEX`
in `SET LOCAL lock_timeout = '3s'` + a `SAVEPOINT` that rolls back and continues on a busy
lock.

**Deliberately out of scope** (not the generator process): the microservices
`tour_orchestrator_service.py`, `map_delivery/app.py`, `user-tracking/entitlements_api.py`,
`tour_reviews_service.py`, `recovery_code_service.py`, `cost_meter.py`, `job_store.py`,
`tour_cache_layer1.py`, `news_cache_layer1.py`, `wallet_ledger.py`, `user_quality_index.py`,
`tour_scoring_service.py`, `tour_sharing.py`, `translation-service/*`, plus migration /
backfill one-off scripts (`migrate_*`, `tour_editing_phase2.py`).

---

## 4. Tests — `test_local797_db_locks.py`

Against a **throwaway** Postgres only (`LOCAL797_TEST_DSN`, or `DB_*` when the port is not
5433); the suite refuses port 5433 outright and SKIPs when no throwaway DB is reachable.

```
LOCAL797_TEST_DSN=postgresql://admin:password123@localhost:5799/audiotours \
  python3 -m pytest test_local797_db_locks.py -v
```

5 tests, **all pass** (5.5 s):

- `SafeDdlUnitTests.test_needed_check_false_skips_ddl` — a falsy `needed_check` skips the DDL.
- `SafeDdlUnitTests.test_success_path_applies_ddl` — a needed DDL with a free lock is applied.
- `VenueCorpusLockTests.test_ensure_table_issues_no_alter_when_tier_already_wide` — on a
  `VARCHAR(20)` tier, the ALTER is skipped (no-op); **no ALTER fires**.
- `VenueCorpusLockTests.test_ensure_table_not_blocked_by_idle_reader` — **the core test**:
  connection A opens a read transaction on `venue_corpus` and stays idle; `_ensure_table` on
  connection B returns in **< 8 s** (skipped + logged), and a SELECT on connection C is not
  blocked.
- `VenueCorpusLockTests.test_safe_ddl_skips_and_continues_under_lock_contention` — with an
  `ACCESS EXCLUSIVE` lock held by another session, `safe_ddl` returns `False` within its
  `lock_timeout` without raising.

**Non-vacuous:** a repro of the pre-fix behaviour (unconditional ALTER, no `lock_timeout`)
stays **BLOCKED > 6 s** behind the idle reader — confirming the test exercises the real
hazard, and the fix is what clears it.

### Regression vs baseline

Ran 19 test files that import the changed modules (DB-touching ones pointed at the throwaway
DB). **144 passed, 24 skipped, 1 failed.** The single failure —
`test_local589_canonical_set_chrome_free.py::test_corpus_canonical_set_has_no_chrome_and_keeps_shows`
— **fails identically on baseline** (verified by `git stash` of the 6 modified files, re-run:
still fails in 0.92 s). It is a content/network-dependent chrome-rejection assertion unrelated
to DB locking. **Zero new failures from LOCAL-797.**

---

## 5. Live proof (OWN containers, never 5433)

- Seeded an **own** throwaway DB `local797-postgres` (host port 5799) from an isolated
  schema dump (89 tables). To force **both** DDL paths, narrowed `venue_corpus.tier` to
  `VARCHAR(15)` and dropped `idx_venue_corpus_expires`.
- `run_local797_container.py` generates a 2-stop **"Arnold Arboretum, Boston"** tour through
  the real `generate_tour_text.generate_tour_text(...)` path, while a background `IdleReader`
  holds `venue_corpus` **idle in transaction for the entire run** (the live pid A). `$1.00`
  hard cap via `tests/live_run_meter.py`; refuses 5433.
- Run in `audioura-tour-generator:latest` with the **worktree mounted** (`-v "$PWD":/app`) so
  it executes the LOCAL-797 code.

**Result:**

- Tour **completed in 273 s (~4.5 min)** — two stops ("The Arnold Arboretum of Harvard
  University", "Hunnewell Building"), stored as one additive `is_test` row (id = 9). **Not**
  the 26-minute freeze.
- Cost **$0.2130** (openai $0.0987, gemini_grounding $0.1060, tokens $0.0073, serper $0.0010)
  — under the $1.00 cap. Network failures: **0**.
- `venue_corpus.tier` stayed `VARCHAR(15)` — the ALTER was correctly **skipped** under the
  busy lock rather than waited on.
- Direct guard proof (cheap, separate invocation under the same idle reader):
  ```
  [LOCAL-797] ddl skipped venue_corpus (lock busy)
  [LOCAL-797] ddl not needed for venue_corpus (skipped)
  _ensure_table returned in 3.02s (no freeze); conn autocommit=True
  ```
  `_ensure_table` bounded by `lock_timeout` (3 s), not minutes.

---

## 6. How to reproduce

```bash
# Throwaway DB (never 5433)
docker run -d --name local797-postgres -p 5799:5432 \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=audiotours postgres:15

# Unit/integration tests
LOCAL797_TEST_DSN=postgresql://admin:password123@localhost:5799/audiotours \
  python3 -m pytest test_local797_db_locks.py -v

# Live 2-stop tour with an idle reader (OWN network/DB; see run_local797_container.py header)
docker network create local797_net
docker network connect --alias local797-postgres local797_net local797-postgres
docker run --rm --name local797-tg --network local797_net --env-file .env \
  -e DATABASE_URL=postgresql://admin:password123@local797-postgres:5432/audiotours \
  -e DB_HOST=local797-postgres -e DB_PORT=5432 -e DB_NAME=audiotours \
  -e DB_USER=admin -e DB_PASSWORD=password123 \
  -e VENUE_CACHE_DB_URL=postgresql://admin:password123@local797-postgres:5432/audiotours \
  -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
  -e STOP_EXISTENCE_GATE_MODE=log_only \
  -e TEST_GEMINI_MAX_USD=1.00 -e COST_HARD_LIMIT_USD=1.00 \
  -v "$PWD":/app -w /app audioura-tour-generator:latest \
  python -u run_local797_container.py
```

---

## 7. Files in this change

- `db_safe_ddl.py` *(new)*
- `venue_resolver.py`
- `work_story_searcher.py`
- `passage_role_tagger.py`
- `stop_existence_gate.py`
- `generate_tour_text.py`
- `stop_pool_orchestrator.py`
- `test_local797_db_locks.py` *(new)*
- `run_local797_container.py` *(new, live harness)*
- `SUBMISSION_LOCAL-797.md` *(this file)*

Generated tour artifacts written into the worktree by the mounted live run
(`Arnold_Arboretum__Boston_walking_tour_*.txt` / `_evidence.json`) are **not** committed.
