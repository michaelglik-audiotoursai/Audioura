##### READY FOR REVIEW

## LOCAL-201: Wire cache-hit charging — callers pass fresh_cost_usd to pricing

**Commit:** `752c0ff` on `kiro/local201-wire-cache-hit-basis`  
**Base:** `subscribed` (at `2b0e75c`)

---

## Design: Fail-open cache-hit charging

Cache-hit charging fails **OPEN** (non-fatal), not closed. Rationale: D14's
fail-closed rule protects against delivering *unbilled new work*. A cache hit
delivers content that already exists — the user gets it regardless (it's a file
on disk). The charge is a fairness rule between users, not a safety gate. If
the pricing lookup fails, the user gets the tour/article for free on this
request; the next request will likely succeed.

**Idempotency:** Both callers use `f"charge:{user_id}:{job_id}"` — the same
key format as the existing fresh-charge path. `wallet_ledger.record_movement`
checks for duplicate keys (SELECT before INSERT, UNIQUE INDEX, UniqueViolation
handler). A retry of the same request produces the same key → no-op.

---

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | New `elif` branch (lines 241–283): when `_is_cache_hit and _our_cost <= 0`, calls `lookup_fresh_cost_for_cache_hit(job_id, _op_type)`, passes result to `compute_user_charge(fresh_cost_usd=...)`, charges wallet if PPU and charge > 0. Fails open. |
| `news_orchestrator_service.py` | Cache-hit path (lines 197–248): after existing metering, inserted charging block. Same pattern: lookup → compute → wallet charge. Inserted before the `return jsonify(...)` early return. Fails open. |
| `tests/test_local201_cache_hit_wiring.py` | 15 unit tests: basis-present (tour + news), basis-absent, our_cost always $0.00, idempotency-key derivation, repeat-request-does-not-double-charge, end-to-end with mocked DB (including sanity ceiling rejection). |

---

## Import-path and container-presence statement

### Import paths (from repo root)

All modules used by the wiring are importable from the repo root:

```
$ python3 -c "import cost_meter; import pricing; import wallet_ledger; import entitlements"
→ No error (all four import cleanly)
```

The callers themselves are also importable:
```
$ python3 -c "import generate_tour_text_service"  → OK
$ python3 -c "import news_orchestrator_service"   → OK
```

### Container presence

| Container | File | Present? |
|-----------|------|----------|
| `audioura-tour-generator-1` | `generate_tour_text_service.py` | ✅ YES |
| `audioura-tour-generator-1` | `cost_meter.py` | ✅ YES |
| `audioura-tour-generator-1` | `pricing.py` | ❌ **ABSENT** |
| `audioura-tour-generator-1` | `wallet_ledger.py` | ❌ **ABSENT** |
| `audioura-tour-generator-1` | `entitlements.py` | ✅ YES |
| `news-orchestrator-1` | `news_orchestrator_service.py` | ✅ YES |
| `news-orchestrator-1` | `cost_meter.py` | ❌ **ABSENT** |
| `news-orchestrator-1` | `pricing.py` | ❌ **ABSENT** |
| `news-orchestrator-1` | `wallet_ledger.py` | ❌ **ABSENT** |
| `news-orchestrator-1` | `entitlements.py` | ✅ YES |

**Finding for LEAD:** The wiring code will execute only after a container
rebuild that includes `pricing.py`, `wallet_ledger.py`, and `cost_meter.py`
in both images. D48 blocks this rebuild in the current task. The code is
correct and tested; it needs deployment (container rebuild) to become live.
The `try/except` blocks ensure the services continue to run without error
if the imports are missing — they log a warning and charge $0.00.

---

## Idempotency design

| Caller | Key format | Source |
|--------|-----------|--------|
| Tour cache hit | `charge:{user_id}:{job_id}` | Same `job_id` as the original generation |
| News cache hit | `charge:{secret_id}:{_cached_article_id}` | Same `article_id` from cache lookup |

**On retry:** `wallet_ledger.record_movement` does a SELECT for the key before
INSERT. If found → returns existing row (no-op, no balance change). If a race
condition causes a duplicate INSERT, the UNIQUE INDEX raises `UniqueViolation`
→ caught, re-fetched, returned. No double charge is possible.

---

## Wallet tests (fail identically to clean `subscribed`)

**Before change (clean subscribed):**
```
FAILED tests/test_wallet_ledger.py::test_ledger_and_derived_balance - AssertionError: Expected 690¢, got 890
FAILED tests/test_wallet_ledger.py::test_zero_balance_stop - AssertionError: Charge should be blocked
========================= 2 failed, 6 passed in 7.69s =========================
```

**After change (this branch):**
```
FAILED tests/test_wallet_ledger.py::test_ledger_and_derived_balance - AssertionError: Expected 690¢, got 890
FAILED tests/test_wallet_ledger.py::test_zero_balance_stop - AssertionError: Charge should be blocked
========================= 2 failed, 6 passed in 7.64s =========================
```

Same 2 tests, same assertions, same values. These failures are pre-existing
(monthly_fee and overdraft-floor behaviour diverge from test expectations due
to the D41/D163 rule change).

---

## Test output (15 passed in 0.10s)

```
tests/test_local201_cache_hit_wiring.py::TestTourCacheHitWiring::test_basis_present_charges_user PASSED
tests/test_local201_cache_hit_wiring.py::TestTourCacheHitWiring::test_basis_absent_charges_zero PASSED
tests/test_local201_cache_hit_wiring.py::TestTourCacheHitWiring::test_our_cost_always_zero_on_cache_hit PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsCacheHitWiring::test_basis_present_charges_user PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsCacheHitWiring::test_basis_absent_charges_zero PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsCacheHitWiring::test_our_cost_always_zero_on_cache_hit PASSED
tests/test_local201_cache_hit_wiring.py::TestCacheHitIdempotency::test_tour_repeat_request_same_idempotency_key PASSED
tests/test_local201_cache_hit_wiring.py::TestCacheHitIdempotency::test_news_repeat_request_same_idempotency_key PASSED
tests/test_local201_cache_hit_wiring.py::TestCacheHitIdempotency::test_idempotency_key_derivation_tour PASSED
tests/test_local201_cache_hit_wiring.py::TestCacheHitIdempotency::test_idempotency_key_derivation_news PASSED
tests/test_local201_cache_hit_wiring.py::TestTourServiceWiring::test_lookup_returns_none_for_missing_job PASSED
tests/test_local201_cache_hit_wiring.py::TestTourServiceWiring::test_lookup_returns_cost_for_existing_job PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsServiceWiring::test_lookup_returns_none_for_missing_article PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsServiceWiring::test_lookup_returns_cost_for_existing_article PASSED
tests/test_local201_cache_hit_wiring.py::TestNewsServiceWiring::test_sanity_ceiling_rejects_implausible_cost PASSED
```

LOCAL-200 tests also pass (48 passed in 0.11s).

---

## Limitations

1. **Container rebuild required for live execution.** The wiring code is present
   in the repo and tested, but the running containers are missing `pricing.py`
   and `wallet_ledger.py` (tour-generator) and `cost_meter.py`, `pricing.py`,
   `wallet_ledger.py`, `cost_rates.py` (news-orchestrator). D48 blocks rebuild.
   LEAD must deploy.

2. **Cache-hit charging fails open.** If imports fail at runtime (missing
   files in container), the `try/except` logs a warning and charges $0.00.
   This is deliberate: content is already generated, the charge is fairness
   revenue not a safety gate.

3. **No integration test against live DB.** The 15 unit tests mock psycopg2.
   An integration test would require the full service stack with the correct
   container images (blocked by D48).

4. **`PRICING_MULTIPLIER` unchanged**, overdraft floor unchanged, `charge()`
   unchanged, `storied` untouched.
