##### READY FOR REVIEW

## LOCAL-211: Create the subscribed database and schema

**Branch:** `kiro/local211-subscribed-db-prep`
**Commit:** `a7e1216` (see `git log --oneline -1`)
**Base:** `subscribed`

---

### Summary

Created `audiotours_subscribed` on `development-postgres-2-1` with a 20-table
schema derived from code analysis. The database starts empty (no data copied).
This removes the final blocker for the subscribed stack deploy noted in
SUBMISSION_LOCAL-204.md.

---

### Files Changed

| File | Purpose |
|------|---------|
| `migration/sql/010_create_subscribed_database.sql` | Idempotent DDL: all 20 tables, indexes, seed data for `plans` |
| `migration/create_subscribed_db.sh` | Re-runnable shell wrapper: creates DB + applies migration |

---

### Schema Derivation Method

Tables were derived by reading:
1. **`wallet_ledger.py`** → `wallet_ledger`, `wallet_balance_cache`, `wallet_subscription`
2. **`cost_meter.py`** → `cost_ledger` (with `ceiling_breach` from 006, `description` from 007)
3. **`wallet_api.py`** → reads `wallet_ledger`, `wallet_subscription`, `cost_ledger` (no new tables)
4. **`tour_orchestrator_service.py`** → `audio_tours`, `users`, `tour_requests`, `job_status`, `coordinates`, `map_requests`, `article_requests`, `news_audios`
5. **`news_orchestrator_service.py`** → `article_requests`, `news_audios` (already covered)
6. **`migration/sql/003_entitlements.sql`** → `plans`, `usage_counters`
7. **`migration/sql/005_subscription_state.sql`** → `subscriptions`, `subscription_transactions`, `low_balance_events`
8. **`migration/sql/008_news_cache.sql`** → `news_cache`
9. **`migration/sql/008_swipe_preferences.sql`** → `user_stop_feedback`, `user_class_prefs`

Column definitions taken from the live `audiotours` schema (via `\d`) and
migration SQL files. FK relationships preserved (plans→users→tour_requests etc).

---

### Evidence

#### 1. `audiotours_subscribed` exists with schema (20 tables, all empty except plans=3)

```
 schemaname |         tablename         | row_count
------------+---------------------------+-----------
 public     | article_requests          |         0
 public     | audio_tours               |         0
 public     | coordinates               |         0
 public     | cost_ledger               |         0
 public     | job_status                |         0
 public     | low_balance_events        |         0
 public     | map_requests              |         0
 public     | news_audios               |         0
 public     | news_cache                |         0
 public     | plans                     |         3
 public     | subscription_transactions |         0
 public     | subscriptions             |         0
 public     | tour_requests             |         0
 public     | usage_counters            |         0
 public     | user_class_prefs          |         0
 public     | user_stop_feedback        |         0
 public     | users                     |         0
 public     | wallet_balance_cache      |         0
 public     | wallet_ledger             |         0
 public     | wallet_subscription       |         0
(20 rows)
```

#### 2. Idempotency — second run is a no-op

```
Step 1: Creating database 'audiotours_subscribed' (if not exists)...
  Database already exists — skipping CREATE.

Step 2: Applying schema migration...
BEGIN
NOTICE:  relation "plans" already exists, skipping
...
NOTICE:  relation "user_class_prefs" already exists, skipping
COMMIT
  Schema applied successfully.
```

Same 20 tables, same row counts.

#### 3. `audiotours` untouched

Before:
```
43 tables, audio_tours count = 124
```

After:
```
43 tables, audio_tours count = 124
```

(Table list identical — same 43 tables in same order.)

#### 4. No containers started, stopped, or replaced

Before container IDs:
```
c8139603567a  audioura-tour-orchestrator-1    Up 19 hours
674ac0e8ce3a  audioura-tour-generator-1       Up 19 hours (healthy)
1a4271178938  development-postgres-2-1        Up 21 hours
...
```

After container IDs:
```
c8139603567a  audioura-tour-orchestrator-1    Up 19 hours
674ac0e8ce3a  audioura-tour-generator-1       Up 19 hours (healthy)
1a4271178938  development-postgres-2-1        Up 21 hours
...
```

All 23 containers identical by ID and uptime.

#### 5. `git status --short` clean after commit

```
$ git status --short
(empty)
```

#### 6. Pre-existing wallet_ledger test failures (before this change)

```
FAILED tests/test_wallet_ledger.py::test_ledger_and_derived_balance
  AssertionError: Expected 690¢, got 890
  (test expects monthly_fee to debit balance; D20 makes it $0 movement)

FAILED tests/test_wallet_ledger.py::test_zero_balance_stop
  AssertionError: Charge should be blocked
  (test expects zero-balance block; D41 overdraft rule allows charge to proceed)

========================= 2 failed, 6 passed in 8.42s =========================
```

These are test-vs-code divergences predating LOCAL-211. The tests were written
for an earlier design (pre-D20, pre-D41). My change does not touch any `.py`
files and cannot have caused or fixed them.

---

### Limitations

1. **`audio_tours` count is 124, not 118.** The task spec says 118; the actual
   count is 124. This was already 124 before my change and remains 124 after.
   Six tours were added by other work since the spec was written.

2. **No data in subscribed database.** By design — the subscribed stack starts
   fresh. Users must register/subscribe separately. Production tour data stays
   exclusively in `audiotours`.

3. **Deploy is LEAD-only (D48).** The subscribed containers are not running
   against this database yet. When Michael approves deploy, LEAD will
   `docker compose -p subscribed-204 -f docker-compose-subscribed.yml up -d`
   and the services will connect to `audiotours_subscribed`.

4. **Tables not included from audiotours (23 storied-only tables):** Tables like
   `shared_tours`, `treats`, `venue_corpus`, `stop_corpus`, `stop_metrics`,
   `newsletters`, `tour_cache`, `referral_codes`, etc. are not needed by the
   subscribed services. If future features require them, a follow-up migration
   can add them.
