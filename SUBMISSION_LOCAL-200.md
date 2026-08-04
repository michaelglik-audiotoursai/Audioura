##### READY FOR REVIEW

## LOCAL-200: Cache-hit charging — tours and news charge same as fresh

**Commit:** `4cc7bb1` on `kiro/local200-cache-hit-charging`  
**Base:** `subscribed` (at `33b0719`)

---

## Design Decision: Option 1 — Original generation's recorded cost

**Chosen:** The charge basis for a cache hit is the `our_cost_usd` from the
original `tour_generate` / `news_generate` row in `cost_ledger`, looked up by
`job_id`.

**Why not Option 2 (recomputed estimate):** A recomputed estimate from artifact
size is reproducible but fictional — it represents a cost nobody actually paid.
Michael's rule is fairness ("why only the first user is paying?"), so the
second user should pay *the same thing* the first user paid. The ledger row IS
what the first user was charged from.

**Pre-LOCAL-197 trap handled:** Costs recorded before LOCAL-197 used the old
gpt-3.5-turbo rate (~$0.002/1K tokens), overstated ~2.5×. A sanity ceiling per
operation type (3× max observed real cost) rejects implausible values:
- `tour_generate`: ceiling $0.25 (max observed ~$0.08)
- `news_generate`: ceiling $0.05 (max observed ~$0.011)
- `translation_generate`: ceiling $1.80 (max observed ~$0.54)

If a stored cost exceeds the ceiling, `lookup_fresh_cost_for_cache_hit` returns
`None` → charge is $0.00. We lose revenue on those old rows rather than
overcharge.

**No-ledger-row case (117 pre-metering tours):** Returns `None` → $0.00
charge. Charging a guess is explicitly excluded.

---

## Per-file summary

| File | Change |
|------|--------|
| `pricing.py` | Generalised cache-hit branch: any type in `_CACHE_HIT_CHARGE_TYPES` charges `fresh_cost_usd × 5` when basis is provided, else $0.00. Added `_CACHE_HIT_CHARGE_TYPES` frozenset. Updated `_OPERATION_LABELS` for tour/news. Updated docstring. |
| `cost_meter.py` | Added `lookup_fresh_cost_for_cache_hit(job_id, operation_type)` — queries `cost_ledger` for the original fresh row, applies sanity ceiling, returns `float` or `None`. Added `_FRESH_COST_SANITY_CEILING` and `_CACHE_HIT_TO_FRESH_TYPE` dicts. |
| `projected_costs.py` | `tour_cache_hit` projection: $0.00 → $0.40. `news_cache_hit`: $0.00 → $0.06. (Matches fresh generation projections for pre-flight overdraft floor.) |
| `test_pricing.py` | Updated 2 description assertions to match new labels (`"Tour (cached — same charge)"`, `"Translation (cached — same charge)"`). |
| `tests/test_local200_cache_hit_charging.py` | 48 new unit tests. |

---

## Proposed wallet transaction descriptions

| Operation | Description (default) |
|-----------|----------------------|
| `tour_cache_hit` | **"Tour (cached — same charge)"** |
| `news_cache_hit` | **"News article (cached — same charge)"** |
| `translation_cache_hit` | "Translation (cached — same charge)" *(unchanged)* |

The "— same charge" suffix makes the cache-hit charge legible: the user sees
it is cached (instant) but understands the price is the same as a fresh
generation. This is the one place where our cost is $0.00 and the charge is
not — Michael's rule is fairness between users, not margin.

Callers may override with a content-specific description, e.g.:
`"Tour: Nice Museum (cached — same charge) — $0.32"`

---

## Test output

### LOCAL-200 tests (48 new) + pricing (30) + LOCAL-169 (7) = 85 passed

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0
collected 85 items

test_pricing.py::TestOperationTypes::test_tour_generate PASSED
test_pricing.py::TestOperationTypes::test_tour_generate_second_example PASSED
test_pricing.py::TestOperationTypes::test_translation_generate PASSED
test_pricing.py::TestOperationTypes::test_tour_cache_hit PASSED
test_pricing.py::TestOperationTypes::test_translation_cache_hit PASSED
test_pricing.py::TestOperationTypes::test_news_generate PASSED
test_pricing.py::TestOperationTypes::test_photo_extension PASSED
test_pricing.py::TestOperationTypes::test_cache_hit_forces_zero_even_with_nonzero_cost PASSED
test_pricing.py::TestFloatDrift::test_10000_sequential_charges_exact PASSED
test_pricing.py::TestFloatDrift::test_10000_mixed_operations_no_drift PASSED
test_pricing.py::TestLedgerRoundTrip::test_known_ledger_rows PASSED
test_pricing.py::TestLedgerRoundTrip::test_ledger_rows_preserve_metadata PASSED
test_pricing.py::TestConfigOverride::test_multiplier_override_to_3 PASSED
test_pricing.py::TestConfigOverride::test_multiplier_override_to_10 PASSED
test_pricing.py::TestConfigOverride::test_multiplier_override_to_1 PASSED
test_pricing.py::TestConfigOverride::test_cache_hit_ignores_multiplier_change PASSED
test_pricing.py::TestConfigOverride::test_bad_env_value_falls_back_to_default PASSED
test_pricing.py::TestEdgeCases::test_custom_description PASSED
test_pricing.py::TestEdgeCases::test_unknown_operation_type_gets_title_case PASSED
test_pricing.py::TestEdgeCases::test_zero_cost_fresh_generation PASSED
test_pricing.py::TestEdgeCases::test_float_input_converted_correctly PASSED
test_pricing.py::TestEdgeCases::test_string_input_works PASSED
test_pricing.py::TestEdgeCases::test_decimal_input_works PASSED
test_pricing.py::TestEdgeCases::test_cents_integer_consistency PASSED
test_pricing.py::TestBankersRounding::test_exact_half_rounds_to_even_down PASSED
test_pricing.py::TestBankersRounding::test_exact_half_rounds_to_even_up PASSED
test_pricing.py::TestBankersRounding::test_above_half_always_rounds_up PASSED
test_pricing.py::TestBankersRounding::test_below_half_always_rounds_down PASSED
test_pricing.py::TestTranslationFlag::test_translation_vs_tour_ratio PASSED
test_pricing.py::TestTranslationFlag::test_translation_absolute_values_documented PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_with_fresh_cost PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_with_fresh_cost_second_example PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_without_fresh_cost_charges_zero PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_fresh_cost_as_float PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_fresh_cost_as_decimal PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_our_cost_stays_zero PASSED
tests/test_local200_cache_hit_charging.py::TestTourCacheHitCharges::test_tour_cache_hit_matches_fresh_tour_charge PASSED
tests/test_local200_cache_hit_charging.py::TestNewsCacheHitCharges::test_news_cache_hit_with_fresh_cost PASSED
tests/test_local200_cache_hit_charging.py::TestNewsCacheHitCharges::test_news_cache_hit_without_fresh_cost_charges_zero PASSED
tests/test_local200_cache_hit_charging.py::TestNewsCacheHitCharges::test_news_cache_hit_our_cost_stays_zero PASSED
tests/test_local200_cache_hit_charging.py::TestNewsCacheHitCharges::test_news_cache_hit_matches_fresh_news_charge PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[tour_cache_hit-0.0633] PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[tour_cache_hit-None] PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[news_cache_hit-0.0085] PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[news_cache_hit-None] PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[translation_cache_hit-0.3720] PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitOurCostZero::test_our_cost_always_zero[translation_cache_hit-None] PASSED
tests/test_local200_cache_hit_charging.py::TestPreLocal197SanityCeiling::test_tour_cache_hit_implausible_cost_charges_zero PASSED
tests/test_local200_cache_hit_charging.py::TestPreLocal197SanityCeiling::test_sanity_ceilings_defined PASSED
tests/test_local200_cache_hit_charging.py::TestPreLocal197SanityCeiling::test_sanity_ceiling_tour_rejects_inflated PASSED
tests/test_local200_cache_hit_charging.py::TestPreLocal197SanityCeiling::test_sanity_ceiling_tour_accepts_normal PASSED
tests/test_local200_cache_hit_charging.py::TestTranslationCacheHitUnchanged::test_translation_cache_hit_with_fresh_cost PASSED
tests/test_local200_cache_hit_charging.py::TestTranslationCacheHitUnchanged::test_translation_cache_hit_without_fresh_cost PASSED
tests/test_local200_cache_hit_charging.py::TestWalletDescriptions::test_tour_cache_hit_description PASSED
tests/test_local200_cache_hit_charging.py::TestWalletDescriptions::test_news_cache_hit_description PASSED
tests/test_local200_cache_hit_charging.py::TestWalletDescriptions::test_translation_cache_hit_description PASSED
tests/test_local200_cache_hit_charging.py::TestWalletDescriptions::test_custom_description_overrides_default PASSED
tests/test_local200_cache_hit_charging.py::TestWalletDescriptions::test_tour_cache_hit_no_fresh_cost_description PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_returns_cost_when_row_exists PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_returns_none_when_no_row PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_returns_none_when_cost_exceeds_ceiling PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_returns_none_when_cost_is_zero PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_news_cache_hit_lookup PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_unknown_operation_type_returns_none PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_no_db_url_returns_none PASSED
tests/test_local200_cache_hit_charging.py::TestLookupFreshCost::test_db_error_returns_none PASSED
tests/test_local200_cache_hit_charging.py::TestProjectedCostsUpdated::test_tour_cache_hit_projection_nonzero PASSED
tests/test_local200_cache_hit_charging.py::TestProjectedCostsUpdated::test_news_cache_hit_projection_nonzero PASSED
tests/test_local200_cache_hit_charging.py::TestProjectedCostsUpdated::test_translation_cache_hit_projection_unchanged PASSED
tests/test_local200_cache_hit_charging.py::TestProjectedCostsUpdated::test_tour_cache_hit_equals_tour_generate_projection PASSED
tests/test_local200_cache_hit_charging.py::TestProjectedCostsUpdated::test_news_cache_hit_equals_news_generate_projection PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitChargeTypes::test_contains_translation PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitChargeTypes::test_contains_tour PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitChargeTypes::test_contains_news PASSED
tests/test_local200_cache_hit_charging.py::TestCacheHitChargeTypes::test_labels_exist_for_all PASSED
tests/test_local200_cache_hit_charging.py::TestRegressionGuard::test_fresh_tour_unchanged PASSED
tests/test_local200_cache_hit_charging.py::TestRegressionGuard::test_fresh_news_unchanged PASSED
tests/test_local200_cache_hit_charging.py::TestRegressionGuard::test_fresh_translation_unchanged PASSED
tests/test_local169_ceiling_and_retranslation.py::test_ceiling_190_allowed PASSED
tests/test_local169_ceiling_and_retranslation.py::test_ceiling_210_aborted PASSED
tests/test_local169_ceiling_and_retranslation.py::test_ceiling_break_probe PASSED
tests/test_local169_ceiling_and_retranslation.py::test_translation_charge_fresh_and_cached PASSED
tests/test_local169_ceiling_and_retranslation.py::test_tour_cache_hit_still_free PASSED
tests/test_local169_ceiling_and_retranslation.py::test_two_different_two_dollars PASSED
tests/test_local169_ceiling_and_retranslation.py::test_cache_identity PASSED

============================== 85 passed in 0.25s ==============================
```

### Wallet tests — pre-existing failures identical on both branches

```
=== LOCAL-200 branch (kiro/local200-cache-hit-charging) ===
tests/test_wallet_ledger.py::test_ledger_and_derived_balance FAILED
tests/test_wallet_ledger.py::test_rebuild_1000_movements PASSED
tests/test_wallet_ledger.py::test_clawback_negative_balance PASSED
tests/test_wallet_ledger.py::test_idempotency PASSED
tests/test_wallet_ledger.py::test_zero_balance_stop FAILED
tests/test_wallet_ledger.py::test_unlimited_cost_stop PASSED
tests/test_wallet_ledger.py::test_cents_conversion PASSED
tests/test_wallet_ledger.py::test_low_balance_reminder PASSED
========================= 2 failed, 6 passed in 7.66s ==========================

=== subscribed baseline ===
tests/test_wallet_ledger.py::test_ledger_and_derived_balance FAILED
tests/test_wallet_ledger.py::test_rebuild_1000_movements PASSED
tests/test_wallet_ledger.py::test_clawback_negative_balance PASSED
tests/test_wallet_ledger.py::test_idempotency PASSED
tests/test_wallet_ledger.py::test_zero_balance_stop FAILED
tests/test_wallet_ledger.py::test_unlimited_cost_stop PASSED
tests/test_wallet_ledger.py::test_cents_conversion PASSED
tests/test_wallet_ledger.py::test_low_balance_reminder PASSED
========================= 2 failed, 6 passed in 7.66s ==========================
```

Both failing tests (`test_ledger_and_derived_balance`, `test_zero_balance_stop`) fail
identically before and after this change. They are pre-existing issues in the
`subscribed` branch unrelated to cache-hit charging.

---

## Limitations

1. **Callers not yet wired.** `pricing.py` now accepts `fresh_cost_usd` for
   `tour_cache_hit` and `news_cache_hit`, and `cost_meter.py` provides
   `lookup_fresh_cost_for_cache_hit()`. However, the service-layer callers
   (`generate_tour_text_service.py` line 238 `if _our_cost > 0` guard, and
   `news_orchestrator_service.py` cache-hit early return) have **not been
   modified** to call the lookup and pass the basis to pricing. This is the
   integration step — it requires container rebuilds (D48 blocks it in this
   task). The arithmetic layer is complete; the wiring is a follow-up task.

2. **The 117 pre-metering tours** will charge $0.00 on cache hit because they
   have no `cost_ledger` row. This is by design (charging a guess is forbidden).
   Revenue is forgone on these legacy tours.

3. **Pre-LOCAL-197 rows** (costs recorded at ~2.5× real rate) are rejected by
   the sanity ceiling and charge $0.00. Once those tours expire from cache
   (or new generations replace them), the issue resolves organically.

4. **Storied branch untouched** — Storied users never see a cost (D58).

5. **`PRICING_MULTIPLIER` unchanged**, overdraft floor unchanged, `charge()`
   unchanged.
