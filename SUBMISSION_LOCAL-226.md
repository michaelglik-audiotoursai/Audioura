##### READY FOR REVIEW

## LOCAL-226: Service-layer dry run — tightened per LEAD bounce

**Branch:** `kiro/local226-subscribed-service-dry-run`
**Commit:** `4a68896`
**Base:** `subscribed`

---

### Summary

Tightened the 27-test service-layer dry run suite per LEAD's falsification
finding: all tests passed with `newsletters_article_link` missing because
they asserted verdicts (`allowed=False`) without asserting the values that
distinguish "healthy quota exhausted" from "database broken, fail-closed."

After tightening: 34 tests, and removing the critical table causes **3
immediate failures** with diagnostic messages naming the exact problem.

---

### The falsification proof

Before (bounced):
```
$ ALTER TABLE newsletters_article_link RENAME TO _tmp
$ python3 -m pytest tests/service_layer_dry_run/ -q
27 passed          ← BROKEN DB undetected
```

After (this submission):
```
$ ALTER TABLE newsletters_article_link RENAME TO _tmp_broken_226
$ python3 -m pytest tests/service_layer_dry_run/ -q
3 failed, 30 passed, 1 warning
  test_news_quota_exceeded_free: Expected used==10, got 9999
  test_news_quota_refusal_via_http: Expected used==10 in HTTP response, got 9999
  test_news_quota_healthy_returns_exact_count: Expected used==3, got 9999
```

The falsification test (`test_falsification.py`) proves this in-suite: it
renames the table, asserts 9999, and restores.

---

### What was tightened (per test)

| Test | Before | After |
|------|--------|-------|
| `test_news_quota_exceeded_free` | `allowed is False` | `used == 10` (exact seeded count) |
| `test_news_quota_refusal_via_http` | `status == 429` | `data["used"] == 10` |
| `test_tour_quota_exceeded_free` | `allowed is False` | `used == 1` (exact seeded count) |
| `test_tour_quota_refusal_via_http` | `status == 429` | `data["used"] == 1` |
| `test_subscribed_tier_truncation` | `len ≤ 15000` | `len > 5000` (proves tier resolved, not free fallback) |
| `test_subscribed_tier_between_limits` | `was_truncated is False` | assert failure msg names tier fallback |
| `test_subscribed_tier_resolution_from_db` | (new) | `_get_subscription_tier == 'ppu'` |
| `test_cache_hit_charge_via_library` | `charge > 0` | `charge == 6` (exact cents) |
| `test_cache_hit_ledger_row_marked` | (new) | DB row has `cache_hit=True, our_cost=0.00` |

---

### Real service-layer finding

**Tour orchestrator reads `user_id` from JSON; news orchestrator reads `secret_id`.**

The test was sending `secret_id` to `/generate-complete-tour` and getting 401
("A valid user id is required") — the field is simply named differently:
- `tour_orchestrator_service.py` line 1416: `user_id = data.get('user_id')`
- `news_orchestrator_service.py` line ~103: `secret_id = data.get('secret_id', 'anonymous')`

Not a schema mismatch but a real API inconsistency that the test client exposed.
(The Flutter app presumably sends both, or routes them differently.)

---

### Container module audit (by inspection, no containers started/stopped)

| Container | Needs | Has | Missing |
|-----------|-------|-----|---------|
| `news-orchestrator-1` | entitlements, pricing, wallet_ledger, cost_meter, cost_rates, news_cache_layer1 | entitlements | **pricing, wallet_ledger, cost_meter, cost_rates, news_cache_layer1** |
| `audioura-tour-orchestrator-1` | entitlements, cost_meter, cost_rates, pricing, wallet_ledger, wallet_api, tier_change, fake_payment_provider | entitlements, cost_meter, cost_rates | **pricing, wallet_ledger, wallet_api, tier_change, fake_payment_provider** |
| `news-processor-1` | article_truncation, entitlements | (none) | **article_truncation, entitlements** |
| `audioura-tour-generator-1` | entitlements, cost_meter, cost_rates | entitlements, cost_meter, cost_rates | (complete for its import set) |

This confirms D76: five subscribed features are built and merged but not deployed.
A deploy must carry these modules to their respective images.

---

### Files Changed

| File | Purpose |
|------|---------|
| `tests/service_layer_dry_run/conftest.py` | Cleanup fix (remove newsletters_article_link reference) |
| `tests/service_layer_dry_run/test_entitlements_gate.py` | Tight value assertions: used==N, not just allowed==False |
| `tests/service_layer_dry_run/test_cache_hit_charge.py` | Exact cents, DB row verification |
| `tests/service_layer_dry_run/test_truncation_e2e.py` | Tier resolution proof, >5000 char assertion |
| `tests/service_layer_dry_run/test_wallet_routes.py` | Tighter structure assertions, limit param test |
| `tests/service_layer_dry_run/test_falsification.py` | NEW — proves suite detects schema break |
| `SUBMISSION_LOCAL-226.md` | This file |

---

### Evidence

#### Test output (34 tests, all passing)

```
$ python3 -m pytest tests/service_layer_dry_run/ -v --tb=short
34 passed, 1 warning in 0.51s
```

#### Falsification proof (with table missing: 3 fail)

```
$ ALTER TABLE newsletters_article_link RENAME TO _tmp_broken_226
$ python3 -m pytest tests/service_layer_dry_run/test_entitlements_gate.py -v --tb=line
FAILED test_news_quota_exceeded_free - AssertionError: Expected used==10, got used==9999
FAILED test_news_quota_refusal_via_http - AssertionError: Expected used==10 in HTTP response, got 9999
FAILED test_news_quota_healthy_returns_exact_count - AssertionError: Expected used==3, got 9999
3 failed, 3 passed
$ ALTER TABLE _tmp_broken_226 RENAME TO newsletters_article_link
```

#### audiotours untouched

```
audiotours.audio_tours count: 133
audiotours tables: 43
```

#### docker ps (23 containers, same IDs before and after)

```
$ docker ps --format '{{.ID}}' | wc -l
23
```

---

### Schema mismatches found via this task

**None new.** LOCAL-225 found and fixed the only mismatch (newsletters_article_link).
The tightened tests confirm the fix is in place and would detect its recurrence.

---

### Limitations

1. **Cache-hit charge path tested via library only, not HTTP.** The news
   orchestrator's cache-hit block imports `cost_meter`, `pricing`, and
   `wallet_ledger` at runtime — which are absent from the live container.
   The test exercises the same code path through the library, but the HTTP
   path through the running container would ImportError. This is a known
   deployment gap (D76), not a schema gap.

2. **Tour orchestrator's change-tier endpoint** depends on `tier_change.py`
   and `fake_payment_provider.py` which are absent from the live container.
   The test passes against the local test client (modules on disk) but would
   fail in the deployed container.

3. **The falsification test mutates and restores schema** in a finally block.
   If the Python process is killed mid-test (SIGKILL, not SIGTERM), the table
   could remain renamed. The test uses CREATE TABLE IF NOT EXISTS as a
   fallback recovery path.
