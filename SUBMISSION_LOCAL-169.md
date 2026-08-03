##### READY FOR REVIEW

## LOCAL-169: Ceiling $2.00 and Re-Translation Charge (D45)

**Commit:** `b52323c`
**Branch:** `kiro/local169-ceiling-2usd-and-retranslation-charge`
**Base:** `subscribed`

---

### Per-File Changes

| File | Change |
|------|--------|
| `cost_ceiling_monitor.py` | Default `COST_HARD_LIMIT_USD` changed from `"1.30"` to `"2.00"`. Abort message updated to reference D45 and use the variable value instead of hardcoded "$1.30". Docstring updated. |
| `pricing.py` | `compute_user_charge()` gains optional `fresh_cost_usd` parameter. When `operation_type == "translation_cache_hit"` and `fresh_cost_usd` is provided, user charge = fresh_cost × multiplier (not $0.00). All other cache hits remain $0.00. Docstring updated to remove "cache hits always $0" blanket statement. |
| `projected_costs.py` | `translation_cache_hit` projected cost changed from `Decimal("0.00")` to `Decimal("2.70")` (same as `translation_generate`). The pre-flight overdraft check now correctly accounts for the user-facing charge of a re-translation. |
| `tour_orchestrator_service.py` | Translation block (lines ~1096–1155) restructured: (1) cost_ledger recording unchanged (fresh → real cost, cache hit → $0.00); (2) NEW wallet charging block added for PPU and Unlimited users — both fresh and cached translations charge the wallet identically using `pricing.compute_user_charge` with `fresh_cost_usd`. |
| `tests/test_local64_cost_ceiling.py` | Boundary tests updated: `test_over_hard_limit` uses $2.50, `test_ceiling_stats_increment` uses $2.50 to trigger abort, `test_exact_boundary_values` tests $2.00 at boundary. Comments updated. |
| `tests/test_local169_ceiling_and_retranslation.py` | **NEW.** 21 assertions: ceiling $1.90 allowed / $2.10 aborted, break-probe, fresh+cached charge equivalence, cost_ledger divergence, tour/news cache hits still free, two-$2.00 separation, cache key identity. |

---

### Verbatim Test Evidence

#### Before (on `subscribed`)

```
test_local64_cost_ceiling.py:      Results: 31 passed, 0 failed   (exit 0)
test_local60_cost_metering.py:     ALL TESTS PASSED                (exit 0)
test_local143_cost_model_matches:  Results: 20 passed, 1 failed   (exit 1) [pre-existing]
test_local163_overdraft_rule.py:   RESULTS: 23/23 passed, 0 failed (exit 0)
```

#### After (on `kiro/local169-ceiling-2usd-and-retranslation-charge`)

```
test_local64_cost_ceiling.py:      Results: 31 passed, 0 failed   (exit 0)
test_local60_cost_metering.py:     ALL TESTS PASSED                (exit 0)
test_local143_cost_model_matches:  Results: 20 passed, 1 failed   (exit 1) [pre-existing]
test_local163_overdraft_rule.py:   RESULTS: 23/23 passed, 0 failed (exit 0)
test_local169_ceiling_and_retranslation.py: RESULTS: 21/21 passed, 0 failed (exit 0)
```

The LOCAL-143 failure is pre-existing: `DEPLOYED_TRANSLATION_PASSES=1` in code vs container reporting 2-pass. Unrelated to this task.

#### Behavioural Evidence (from test_local169)

**Ceiling exercised (not asserted from constant — D35):**
```
$1.90 → abort=False, warn=True, hard_limit=2.0
$2.10 → abort=True, breach=hard_limit_exceeded
```

**Break-probe (D36):**
```
break_probe_replacement_count: 1
```

**Translation charge — fresh vs cached:**
```
fresh_translation_cost_usd: $0.304448
fresh_user_charge:  $1.52 (152¢)
cached_user_charge: $1.52 (152¢)  ← SAME

wallet_ledger_fresh:  type=charge, amount=-152¢, desc=Translation to fr — $1.52
wallet_ledger_cached: type=charge, amount=-152¢, desc=Translation to fr (cached) — $1.52
```

**cost_ledger divergence (intended):**
```
cost_ledger_fresh_our_cost:  $0.304448  (cache_hit=False)
cost_ledger_cached_our_cost: $0.000000  (cache_hit=True)
```

---

### Findings

1. **Cache key is correct.** The translation cache key is `original_tour_id + content_language` (in `translation_service.py`: `SELECT id FROM audio_tours WHERE original_tour_id = %s AND content_language = %s`). Each tour variant has a unique ID, so two variants of the same venue produce separate cache entries. This matches Michael's requirement ("people can modify tours and have multiple tour options and we should keep them all with their individual translations").

2. **Two $2.00 values are separate named constants.**
   - Ceiling: `cost_ceiling_monitor.COST_HARD_LIMIT` — the most a single operation may cost before abort.
   - Floor: `projected_costs.OVERDRAFT_FLOOR_CENTS = -200` — how far a balance may go negative.
   - They live in different modules, have different semantics, and must not be unified.

3. **Translation was previously metered but never wallet-charged.** The orchestrator recorded to `cost_ledger` (LOCAL-60) but never called `wallet_ledger.charge()` for translations. This task adds the wallet charge path for both fresh and cached.

---

### Limitations / Noted Inconsistencies

1. **Tour generation reuse (LOCAL-156) still refunds.** When a requested tour already exists, LOCAL-156 issues a `service_credit` refund. The same "charge regardless of cache" argument that D45 applies to translations could apply to tours — but Michael specified translations only. Left alone per instructions.

2. **Downloads remain free.** Downloading an already-created tour is not a billable event.

3. **No real translation was generated.** The charge path is exercised end-to-end through `pricing.compute_user_charge` → `wallet_ledger.charge` with real DB writes, without calling the translation service or spending API credits.

4. **LOCAL-143 pre-existing failure.** The running container reports 2-pass translation while `DEPLOYED_TRANSLATION_PASSES=1`. This predates LOCAL-169 and affects cost accuracy (understating), not correctness of the charge logic.

5. **The ×5 multiplier and user-facing price were not touched.** At single-pass with 16K chars: our cost ≈ $0.30, user charge ≈ $1.52. This is within the new $2.00 ceiling.
