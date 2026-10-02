##### READY FOR REVIEW

# SUBMISSION_LOCAL-65 — Pricing Engine

**Branch:** `kiro/local65-pricing-engine`
**Commit:** `ad6e84c`
**Files changed:** `pricing.py` (new, 187 lines), `test_pricing.py` (new, 487 lines)

---

## What was built

`pricing.py` — a pure pricing function that turns a metered cost (from
`cost_meter.py` / `cost_ledger`) into a user-facing charge:

```
user_charge = our_cost_usd × PRICING_MULTIPLIER
```

No balance mutation, no wallet writes, no ledger changes. This module
computes and returns; LOCAL-66 owns persistence.

---

## Design decisions

### Rounding: Banker's (ROUND_HALF_EVEN)

**Why not half-up?** Half-up biases systematically upward. Over thousands
of transactions that bias accumulates into real money drift. Banker's
rounding (IEEE 754 default) rounds to the nearest even digit on exact
halves, statistically eliminating systematic bias.

**Round once, at the charge boundary.** Component costs flow as raw
Decimals; only the final `user_charge_usd` is quantized to $0.01.

### Money representation: `decimal.Decimal` — never `float`

`Decimal("0.0633") * Decimal("5.0") = Decimal("0.3165")` — exact.
`0.0633 * 5.0 = 0.31649999...` — float drift.

The output includes both:
- `user_charge_usd`: `Decimal` for computation
- `user_charge_cents`: `int` for storage (avoids all fractional issues)

### Cache hit = $0.00 always

Non-negotiable per Michael's ruling. Even if a caller erroneously passes a
non-zero cost with `cache_hit=True`, the charge is forced to zero.

### Per-operation-type pricing (not per-tour)

`photo_extension`, `news_generate`, and future types work without redesign.
The multiplier applies uniformly; different operations just have different
underlying costs.

### Configuration via environment (no code change)

```
PRICING_MULTIPLIER=5.0   # default, read every call
CACHE_HIT_COST_USD=0.00  # always zero
```

Set `PRICING_MULTIPLIER=3.0` in env → prices move immediately. Proven in tests.

---

## ⚠️ FLAG FOR MICHAEL — Translation pricing

At ×5, a fresh translation costs the user **$1.86** against **$0.32** for
the tour it translates — roughly **6× more expensive**.

This is mathematically correct: our translation cost is $0.372 (Google
Translate + TTS for the full text), which is ~6× our tour generation cost
($0.063). The ×5 multiplier amplifies proportionally.

Michael should confirm this is acceptable UX before launch. Options:
1. Accept (it reflects real cost proportions)
2. Cap translation charge (e.g. max 2× the tour charge)
3. Lower the multiplier for translations only (breaks the uniform-multiplier
   simplicity)

---

## Test evidence

### Test run (30/30 PASS)

```
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

============================== 30 passed in 0.10s ==============================
```

### Known real numbers (from task spec)

| Operation | Our cost | User charge | Matches spec? |
|-----------|----------|-------------|---------------|
| tour_generate | $0.0633 | $0.32 | ✓ |
| tour_generate | $0.0573 | $0.29 | ✓ |
| translation_generate | $0.3720 | $1.86 | ✓ |
| tour_cache_hit | $0.0000 | $0.00 | ✓ |
| translation_cache_hit | $0.0000 | $0.00 | ✓ |

### Float-drift test

10,000 charges of $0.0633 at ×5: total = $3,200.00 exactly (no drift).
10,000 mixed charges (5 op types): total = $4,940.00 exactly (no drift).
Cents integer always equals Decimal × 100 — verified across all test runs.

### Config override

```
PRICING_MULTIPLIER=3.0  → $0.0633 charges $0.19 (was $0.32)
PRICING_MULTIPLIER=10.0 → $0.0633 charges $0.63
PRICING_MULTIPLIER=1.0  → $0.3720 charges $0.37 (pass-through)
```

### Regression suite (prepush-baseline)

```
test_tier_computation.py  — PASSED
test_sq3_fixtures.py      — PASSED
test_f4_cache_roundtrip.py — PASSED (3 warnings, non-blocking)
test_w4_matcher.py        — PASSED
Total: 41 passed in worktree (30 new + 11 existing), 0 failed
```

Baseline directory `~/audioura-worktrees/prepush-baseline` runs the same
existing tests with identical results (11 passed). No regression.

---

## Commit verification

```
$ git rev-list --count storied..HEAD
1

$ git show --stat HEAD
commit ad6e84cbfc21ae640fcfe7c8a897821a990794a9
 pricing.py      | 187 ++++++++++++++++++
 test_pricing.py | 487 ++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 674 insertions(+)
```
