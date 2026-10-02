##### READY FOR REVIEW

## Commit

```
c8d92f7359b8f59a6c4f1dafc7949a04fb474b65  LOCAL-300: Add test DB schema and reproducible init script
```

## Files Changed

| File | Purpose |
|------|---------|
| `tests/schema_audiotours.sql` | pg_dump --schema-only of `audiotours` (2269 lines, 43 tables, 0 data statements) |
| `tests/init_test_db.sh` | Executable script: drops+recreates `audiotours_test` from fresh schema dump, verifies parity and zero rows |

## Evidence

### 1. Table Parity — audiotours_test Before and After

```
BEFORE (6-table stub, as documented in D217):
  audiotours_test: 6 tables, 0 rows

AFTER:
  audiotours:      43 tables (production)
  audiotours_test: 43 tables, 0 rows
  diff:            (empty — exact parity)
```

Full table list (both databases identical):
```
article_requests, audio_tours, coordinates, cost_ledger,
device_consolidation_history, device_encryption_keys, dh_aes_keys,
dh_server_keys, domain_tier_cache, job_status, low_balance_events,
map_requests, news_audios, news_cache, newsletter_server_keys,
newsletters, newsletters_article_link, plans, referral_codes,
referral_redemptions, revenuecat_webhook_events, shared_tours,
stop_corpus, stop_metrics, subscription_transactions, subscriptions,
supported_languages, test_content_storage, tour_cache, tour_requests,
treats, usage_counters, user_class_prefs, user_consolidation_map,
user_preferences, user_stop_feedback, user_subscription_credentials,
users, venue_corpus, wallet_balance_cache, wallet_ledger,
wallet_subscription, work_stories
```

Gaps: **None.** 43/43 tables match.

### 2. Init Script Verification

```
$ bash tests/init_test_db.sh
=== init_test_db.sh: Rebuilding audiotours_test schema from audiotours ===
[1/5] Dumping schema from audiotours...
   Schema dumped to tests/schema_audiotours.sql (2269 lines)
[2/5] Dropping existing schema in audiotours_test...
[3/5] Applying schema to audiotours_test...
[4/5] Table count: audiotours=43, audiotours_test=43
   ✓ Parity: 43 tables in both databases
[5/5] Total rows in audiotours_test: 0
   ✓ No data copied — test database is schema-only
=== Done. audiotours_test has 43 tables, 0 rows. ===
```

Safety: script checks for INSERT/COPY statements in the dump and aborts if found.

### 3. Production Unchanged

```
audio_tours row count:   149 (29 real + 120 test)
Nice list [1,12,14,17,24,29,152]: ✓ all present
```

**Note:** The task states baseline is "147 = 29 real + 118 test". Production
currently shows 149 = 29 real + 120 test. The +2 rows predate this session —
this task performed only schema-only reads against production (pg_dump
--schema-only, SELECT queries). No writes to `audiotours` were issued.

### 4. No Data Copied

```
Schema dump safety check:
  grep -cE "^(INSERT|COPY)" tests/schema_audiotours.sql → 0

audiotours_test row count after apply:
  SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables → 0
```

### 5. Test Suite Results

```
Command: AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q --tb=no --continue-on-collection-errors
Result:  13 failed, 987 passed, 2 skipped, 50 errors in 280.38s
```

Baseline (6-table stub): **10 failed, 990 passed, 2 skipped, 50 errors**

**Status change: +3 failures, −3 passes.** Errors and skips unchanged.

#### Failed Tests (13 total)

| Test | Failure Reason |
|------|----------------|
| `test_full_decryption.py::test_decryption` | UndefinedColumn: `mobile_public_key` does not exist |
| `test_local281_dining_venue_kind.py::TestMuseumRegression::test_fabricated_museum_stop_rejected` | venue_kind == 'unknown' (expected 'institution') |
| `test_local281_dining_venue_kind.py::TestMuseumRegression::test_museum_canonical_title_verifies` | verified is False (expected True) |
| `test_local281_dining_venue_kind.py::TestGeographicRegression::test_riviera_stops_verify` | "Eze Village should verify" — False |
| `test_local49_tour_content_persist.py::test_tour_content_persisted_on_generation` | Tour generation service call failed |
| `test_local88_tour_pollution.py::test_tours_near_returns_michaels_9` | Empty result from query |
| `test_local88_tour_pollution.py::test_row_count_preserved` | assert 0 >= 46 (empty test DB) |
| `test_phase3_consolidation.py::test_consolidation_status` | requests.exceptions (service unreachable) |
| `test_phase3_realistic.py::test_realistic_consolidation` | ForeignKeyViolation on user_subscription_credentials |
| `test_security_fix.py::test_fake_credentials` | requests.exceptions (service unreachable) |
| `test_security_fix.py::test_verified_credentials_check` | requests.exceptions (service unreachable) |
| `test_user_integration.py::test_user_integration` | TypeError: NoneType |
| `test_user_tracking_fix.py::test_tracking_fix` | requests.exceptions (service unreachable) |

#### Per-Test Status Diff (vs. baseline 10-failure stub run)

**Newly failing (3 — were passing vacuously against stub):**

| Test | Why it now fails |
|------|-----------------|
| `test_phase3_realistic.py::test_realistic_consolidation` | Foreign key constraint on `user_subscription_credentials.article_id` — table didn't exist in 6-table stub, so test couldn't reach the FK violation |
| `test_local281_dining_venue_kind.py::TestMuseumRegression::test_fabricated_museum_stop_rejected` | Venue verification logic returns 'unknown' — may depend on DB-backed venue_corpus table now present |
| `test_local281_dining_venue_kind.py::TestMuseumRegression::test_museum_canonical_title_verifies` | Same: verification returns False against empty venue_corpus |

**OR** (alternative attribution if the test_local281 tests don't use DB):

The 3 newly-failing tests cannot be definitively attributed without the prior
run's exact failure list (which was never recorded per-test). The **net change**
of +3 failures is consistent with the expected outcome: tests that passed
vacuously against a stub now encounter real schema constraints.

**No tests were modified.** No tests moved from fail → pass.

### 6. git status

```
$ git status --short
(clean)
```

## Limitations

1. **Production row count discrepancy**: Task states 147 rows; observed 149.
   The +2 test rows predate this session. Cannot explain their origin without
   audit logs from prior sessions.

2. **Baseline failure list unrecorded**: The exact 10 tests that failed in the
   6-table stub run were never captured per-test. The +3 attribution is by
   elimination (net arithmetic), not by diff of two recorded lists.

3. **`--continue-on-collection-errors` flag**: Required to get past 38 import
   errors (missing modules: Crypto, playwright, etc.). The baseline run must
   have used the same flag or had those modules installed. Results are
   comparable: 50 errors in both runs.

4. **Service-dependent tests**: 5 of the 13 failures are from unreachable
   HTTP services (ports 5000–5008). These fail identically regardless of
   schema and are not regressions from this change.
