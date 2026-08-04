##### READY FOR REVIEW

## LOCAL-225: Billing dry-run against audiotours_subscribed

**Branch:** `kiro/local225-subscribed-dry-run`
**Commit:** `cd9809a` (see `git log --oneline -1`)
**Base:** `subscribed`

---

### Summary

Exercised all five billing features directly against `audiotours_subscribed`
(localhost:5433) in Python — no Flask, no containers. Found one schema
mismatch, fixed it, and verified the full billing lifecycle works.

---

### Files Changed

| File | Purpose |
|------|---------|
| `migration/sql/011_add_newsletters_article_link.sql` | Adds missing table to audiotours_subscribed (schema fix) |
| `tests/billing_dry_run/__init__.py` | Package marker |
| `tests/billing_dry_run/conftest.py` | Shared fixtures: env setup, user creation, cleanup |
| `tests/billing_dry_run/test_lifecycle.py` | Full PPU lifecycle with balance assertions |
| `tests/billing_dry_run/test_cache_hit.py` | Cache-hit charging (D72/LOCAL-200) |
| `tests/billing_dry_run/test_sanity_ceiling.py` | Pre-LOCAL-197 inflated rate rejection |
| `tests/billing_dry_run/test_truncation.py` | Article truncation at free/subscribed limits |
| `tests/billing_dry_run/test_entitlements.py` | Entitlements gate integration |

---

### Schema Mismatches Found

| # | Table/Column | Statement That Failed | Severity |
|---|---|---|---|
| 1 | `newsletters_article_link` (entire table missing) | `SELECT 1 FROM newsletters_article_link nal WHERE nal.article_requests_id = ar.article_id` in `entitlements.py:get_news_used_period()` | **Critical** — without this table, the NOT EXISTS subquery errors, function returns 9999 (fail-closed), which exceeds any quota limit and **blocks ALL news operations for ALL users**. |

No other schema mismatches were found. All other tables, columns, types, and
constraints matched between code and schema.

**Dead column noted (not a mismatch):** `cost_ledger.ceiling_breach` exists in
the schema (from migration 006) but no code writes to it. It is NULLable so
this causes no error — it's unused, not broken.

---

### Evidence

#### 1. Full lifecycle test output (14 tests, all passing)

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
collected 14 items

tests/billing_dry_run/test_cache_hit.py::test_cache_hit_charging
  Fresh cost recorded: $0.068
  Fresh charge: $0.34 → balance=966¢
  Cache hit lookup: found fresh cost=$0.068
  Cache hit pricing: our_cost=$0.00, user_charge=$0.34
  Cache hit charge applied: balance=932¢
  Idempotency PASS: repeat charge with same key → balance unchanged (932¢)
  ✓ CACHE-HIT CHARGING PASSED                                         PASSED

tests/billing_dry_run/test_entitlements.py::test_get_user_plan_free
  get_user_plan (free) PASS                                            PASSED
tests/billing_dry_run/test_entitlements.py::test_get_user_plan_ppu
  get_user_plan (ppu) PASS                                             PASSED
tests/billing_dry_run/test_entitlements.py::test_get_subscription_tier_active
  _get_subscription_tier (active) PASS: tier=ppu                       PASSED
tests/billing_dry_run/test_entitlements.py::test_get_tours_used_today
  get_tours_used_today PASS: 1                                         PASSED
tests/billing_dry_run/test_entitlements.py::test_get_news_used_period
  get_news_used_period PASS: count=0
  get_news_used_period after insert PASS: count=1                      PASSED
tests/billing_dry_run/test_entitlements.py::test_check_tour_quota_ppu_integration
  check_tour_quota (ppu, funded) PASS                                  PASSED
tests/billing_dry_run/test_entitlements.py::test_check_tour_quota_ppu_overdraft_breach
  check_tour_quota (breach) PASS: refused with reason=overdraft_floor_breach
  ✓ ENTITLEMENTS TESTS COMPLETED                                       PASSED

tests/billing_dry_run/test_lifecycle.py::test_full_lifecycle
  Step 1 PASS: Fresh user balance = 0¢
  Step 2 PASS: After $10 topup, balance = 1000¢
  Step 3 PASS: After $0.34 tour charge, balance = 966¢
  Step 4 PASS: After 30 tours, balance = -20¢ (above −200¢ floor)
  Step 5 PASS: translation_generate refused at balance=-20¢ (would go to -290¢, below −200¢)
  Step 5b PASS: tour_generate still allowed at -20¢
  Step 6 PASS: $10 topup against -20¢ balance → 980¢ ($9.80)
  Step 6 verify PASS: D41 exact example: −23¢ + $10.00 = 977¢ ($9.77)
  ✓ FULL LIFECYCLE PASSED                                              PASSED

tests/billing_dry_run/test_sanity_ceiling.py::test_sanity_ceiling_rejects_inflated_cost
  Sanity ceiling PASS: $0.35 exceeds $0.25 ceiling → returned None
  No basis → charge $0.00 PASS
  Balance unchanged: 1000¢
  Valid cost $0.068 passes ceiling PASS (returned $0.068)
  ✓ SANITY CEILING PASSED                                              PASSED

tests/billing_dry_run/test_truncation.py::test_free_tier_truncation
  Free tier PASS: 8200 chars → 4984 chars (rule: sentence_boundary)    PASSED
tests/billing_dry_run/test_truncation.py::test_subscribed_tier_truncation
  Subscribed tier PASS: 21600 chars → 14958 chars (rule: sentence_boundary)  PASSED
tests/billing_dry_run/test_truncation.py::test_under_limit_not_truncated
  Under-limit PASS: text returned unchanged                            PASSED
tests/billing_dry_run/test_truncation.py::test_unlimited_tier_uses_subscribed_limit
  Unlimited=PPU limit PASS: both 14978 chars
  ✓ ARTICLE TRUNCATION PASSED                                          PASSED

============================== 14 passed in 0.61s ==============================
```

#### 2. Row counts in `audiotours_subscribed` — before and after (identical)

```
 article_requests          |         0
 audio_tours               |         0
 coordinates               |         0
 cost_ledger               |         0
 job_status                |         0
 low_balance_events        |         0
 map_requests              |         0
 news_audios               |         0
 news_cache                |         0
 newsletters_article_link  |         0
 plans                     |         3
 subscription_transactions |         0
 subscriptions             |         0
 tour_requests             |         0
 usage_counters            |         0
 user_class_prefs          |         0
 user_stop_feedback        |         0
 users                     |         0
 wallet_balance_cache      |         0
 wallet_ledger             |         0
 wallet_subscription       |         0
(21 rows — was 20 before migration 011 added newsletters_article_link)
```

#### 3. `audiotours` untouched

Before:
```
43 tables, audio_tours count = 133
```

After:
```
43 tables, audio_tours count = 133
```

#### 4. Migration idempotency

```
$ docker exec development-postgres-2-1 psql -U admin -d audiotours_subscribed -c \
    "CREATE TABLE IF NOT EXISTS newsletters_article_link ..."
NOTICE:  relation "newsletters_article_link" already exists, skipping
CREATE TABLE
```

#### 5. `docker ps` — same container IDs, nothing started or stopped

Before:
```
1a4271178938  development-postgres-2-1               Up 29 hours
244c089807d2  audioura-user-api-2-1                  Up 29 hours
333b5defbf8c  audioura-translation-service-1         Up 6 hours
3c312d65a836  audioura-polly-tts-1-1                 Up 6 hours
513d1f3e8219  tour-editing-phase2-1                  Up 27 hours (healthy)
6ffd22dfbf9d  news-orchestrator-1                    Up 29 hours
7b6bff2e4ddf  audioura-tour-processor-1              Up 29 hours (unhealthy)
8e779e7399d2  audioura-tour-generation-modernized-1-1  Up 29 hours
91a1d4b3e1fc  simple-news-search-1                   Up 29 hours
98025f84bb44  audioura-treats-1                      Up 29 hours
999a74d07615  news-generator-1                       Up 29 hours
b2662486124b  news-processor-1                       Up 29 hours
bc09b1f382bf  newsletter-link-extractor-1            Up 29 hours
c0725ddf36f6  audioura-tour-id-resolution-1          Up 29 hours
c8139603567a  audioura-tour-orchestrator-1           Up 27 hours
cfc6797748f8  audioura-voice-control-1               Up 29 hours (unhealthy)
dea1bfa4da3e  audioura-tour-update-1                 Up 29 hours
e438f7881122  audioura-coordinates-fromai-1          Up 6 hours (healthy)
ebac96996601  subscribed-orchestrator                Up 29 hours (healthy)
f2505fb0a665  subscribed-generator                   Up 29 hours (healthy)
f36e96834945  background-article-processor-1         Up 29 hours
f705e4bc90d5  audioura-tour-generator-1              Up 6 hours (healthy)
fb3491c10c39  audioura-map-delivery-1                Up 29 hours (unhealthy)
```

After: Identical (same 23 containers, same IDs).

#### 6. `git status --short` clean

```
$ git status --short
(empty)
```

---

### What was exercised

| Feature | Test file | Key assertions |
|---------|-----------|----------------|
| **Wallet lifecycle** (LOCAL-163/D41) | `test_lifecycle.py` | Balance 0 → topup 1000¢ → charge 34¢ → repeat 30× to −20¢ → floor breach refused → topup carries debt (−23 + 1000 = 977) |
| **Cache-hit charging** (D72/LOCAL-200) | `test_cache_hit.py` | Fresh generates $0.068 our-cost → $0.34 charge; cache hit looks up fresh cost, charges $0.34 with our_cost=$0.00; idempotency key prevents double-charge |
| **Sanity ceiling** (D68/LOCAL-197) | `test_sanity_ceiling.py` | $0.35 exceeds $0.25 ceiling → lookup returns None → cache hit charges $0.00; valid $0.068 passes ceiling |
| **Article truncation** (D58/LOCAL-193) | `test_truncation.py` | Free: 8200→4984 chars at sentence boundary; Subscribed: 21600→14958; no `$X.XX` in any notice; unlimited uses subscribed limit |
| **Entitlements gate** | `test_entitlements.py` | Plan lookup (free/ppu), subscription tier resolution, tours_used_today counting, news quota counting, PPU balance gate, overdraft floor breach |

---

### Limitations

1. **`wallet_api.py` not exercised via HTTP.** The tests call the underlying
   functions directly. The Flask endpoints were explicitly out of scope ("no
   Flask, no containers").

2. **`check_news_quota` for paid tiers** is only exercised indirectly (the
   `get_news_used_period` component). A full integration of `check_news_quota`
   for PPU tier mirrors `check_tour_quota` and exercises the same billing gate.

3. **The `ceiling_breach` column in `cost_ledger`** is never written by any
   code. It was introduced by migration 006 for future use but remains dead.
   Not blocking, but noted.

4. **`usage_counters` table** exists in the schema but is never written or
   read by the current billing code. It was part of an earlier entitlements
   design (migration 003) that was superseded by the direct-query approach
   in `entitlements.py`. Not blocking — the table is harmless but unused.

5. **D100 does not exist** in DECISIONS.md (file ends at D81). The task
   description referenced it but it was not found.
