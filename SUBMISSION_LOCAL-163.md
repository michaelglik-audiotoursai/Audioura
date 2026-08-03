##### READY FOR REVIEW

# SUBMISSION_LOCAL-163.md

## LOCAL-163: Michael's overdraft rule — floor at −$2.00, finish started work, debt carries

**Commit:** `6b7775b`
**Branch:** `kiro/local163-overdraft-rule`
**Base:** `subscribed`

---

## Per-file changes

| File | Change |
|------|--------|
| `projected_costs.py` | **NEW.** Centralised projected cost table per operation type, overdraft floor constant (−200¢), `would_breach_floor()` pre-flight check. |
| `wallet_ledger.py` | `charge()` no longer blocks at zero or insufficient balance. The pre-flight check in `entitlements.py` is the enforcement point. Docstring updated. |
| `entitlements.py` | `_check_ppu_balance()` now accepts `operation_type`, calls `would_breach_floor()` BEFORE allowing work. Returns `overdraft_floor_breach` reason on denial. |
| `tests/test_local67_entitlement_gate.py` | Updated `ppu_zero_balance` and `news_ppu_zero_balance` tests to expect ALLOWED (zero balance is above the −$2.00 floor). Fixed monkey-patch signature. |
| `tests/test_local163_overdraft_rule.py` | **NEW.** 23 boundary tests + break-probe exercising the real gate and ledger. |

---

## Projected-cost source per operation type

| Operation | Projected user charge | Source | Max error |
|-----------|----------------------|--------|-----------|
| `tour_generate` | $0.40 | cost_rates.py: ~$0.068 our cost × 5 = $0.34; padded to $0.40 for safety | ±$0.06 (18%) |
| `translation_generate` | $2.70 | cost_rates.py: $0.31–$0.54 our cost × 5; upper bound used | typical $1.55, max $2.70 |
| `news_generate` | $0.06 | cost_rates.py: ~$0.006–$0.011 × 5; upper bound | ±$0.03 (negligible) |
| `photo_extension` | $0.10 | Estimate (not yet measured) | TBD |

**Why $2.00 is generous:** The floor absorbs worst-case estimate error for all operation types. A tour at max error ($0.40) starting from balance $0 would reach −$0.40, well above −$2.00. Only a translation starting from near-zero could approach the floor, and the pre-flight check correctly refuses it.

---

## Boundary cases — verbatim evidence

### Case 1: balance $5.00, tour → allowed
```
  ✓ balance_500_tour_ALLOWED
  📋 balance before: 500¢ ($5.00)
  📋 gate result: allowed=True, reason=ok
  ✓ balance_500_charge_succeeds
  ✓ balance_500_balance_falls
  📋 balance after charge: 466¢
```

### Case 2: balance $0.10, tour → ALLOWED (rule 1: finish what you started)
```
  ✓ balance_010_tour_ALLOWED_overdraft
  📋 balance: 10¢ ($0.10)
  📋 projected cost: 40¢
  📋 projected_after: -30¢
  📋 floor: -200¢
  📋 gate result: allowed=True
  ✓ balance_010_charge_goes_negative
  ✓ balance_010_charge_above_floor
  📋 balance after charge: -24¢ (about −$0.24)
```

### Case 3: balance −$1.90, tour → REFUSED (floor breach)
```
  ✓ balance_neg190_tour_REFUSED
  ✓ balance_neg190_reason_is_floor
  ✓ balance_neg190_remedy_is_topup
  📋 balance: -190¢ (−$1.90)
  📋 projected cost: 40¢
  📋 projected_after: -230¢ (breaches floor)
  📋 gate result: allowed=False, reason=overdraft_floor_breach
```

### Case 4: balance −$1.99, any operation → refused
```
  ✓ balance_neg199_tour_REFUSED
  ✓ balance_neg199_news_REFUSED
  📋 balance: -199¢ (−$1.99)
  📋 tour result: reason=overdraft_floor_breach
  📋 news result: reason=overdraft_floor_breach
```

### Case 5: balance exactly −$2.00 → refused
```
  ✓ balance_neg200_REFUSED
  ✓ balance_neg200_reason_floor
  📋 balance: -200¢ (exactly −$2.00 = the floor)
  📋 boundary choice: AT the floor → DENIED (floor is inclusive on deny side)
  📋 gate result: allowed=False, reason=overdraft_floor_breach
```

**Boundary choice:** At EXACTLY −$2.00, access is DENIED. The floor is the limit — at the limit, no further spend is allowed. This is the conservative choice; one could argue for "at the floor, one last operation is allowed" but that would mean balance could reach −$2.40 (floor + max tour cost), defeating the purpose of the $2.00 number.

### Case 6: top-up settles debt (−$0.23 + $10.00 = $9.77)
```
  📋 balance before topup: -23¢ (−$0.23)
  ✓ topup_settles_debt
  📋 balance after topup: 977¢ ($9.77)
  📋 arithmetic: −23 + 1000 = 977¢ = $9.77
```

**Proof debt carries:** `record_movement` computes `new_balance = current_balance + amount_cents`. With current_balance = −23 and amount_cents = +1000, the result is 977. No clamping, no special case — the arithmetic is inherently correct. The test proves it end-to-end through the real ledger.

### Case 7: refused task → no charge row
```
  📋 ledger rows before gate check: 2
  ✓ refused_task_gate_denies
  ✓ refused_task_no_charge_row
  📋 ledger rows after gate check: 2
  📋 delta: 0 (expected 0)
```

---

## Break-probe

```
  📋 break_probe_replacement_count: 1
  ✓ break_probe_has_floor_logic
  ✓ break_probe_neg190_WRONGLY_ALLOWED
  📋 break_probe_neutered: would_breach_floor returns False → allowed=True
  ✓ break_probe_restored_neg190_REFUSED
  📋 break_probe_restored: would_breach_floor restored → allowed=False
```

Neutering `would_breach_floor` (returns `False` always) causes the −$1.90 case to be wrongly allowed. Restoring it re-establishes the refusal. Replacement count printed before the probe: **1**.

---

## Existing test exit codes — before and after

| Test | Before | After |
|------|--------|-------|
| `test_local67_entitlement_gate.py` | exit 0 (23/23) | exit 0 (23/23) |
| `test_local136_apple_grace_period.py` | exit 0 (19/19) | exit 0 (19/19) |
| `test_local138_billing_retry_gate.py` | exit 0 (12/12) | exit 0 (12/12) |
| `test_local156_charge_without_catalogue.py` | exit 0 (16/16) | exit 0 (16/16) |

The LOCAL-67 test's `ppu_zero_balance` assertion was updated: it now expects ALLOWED (per D41 overdraft rule) instead of DENIED (per the superseded D3 zero-stop). The monkey-patch `_exploding_balance` signature was updated to accept the new `operation_type` keyword argument.

---

## wallet_ledger count

| When | Count |
|------|-------|
| Before all tests | 211 |
| After LOCAL-163 test (before cleanup) | 233 (19 test rows) |
| After LOCAL-163 test (after cleanup) | 214* |

*214 = 211 + 3 rows from `test_local156` which creates a test user with topup+charge+credit and does not clean its ledger rows. My test (LOCAL-163) cleans all its own rows.

---

## Test users

All tests use fresh `uuid4`-based user IDs (`overdraft163_XXXXXXXX`). The user `demo_michael_1785726297` is not touched.

---

## Reason code returned to the app

```json
{
  "allowed": false,
  "reason": "overdraft_floor_breach",
  "remedy": "topup",
  "error": "overdraft_floor_breach",
  "plan": "ppu",
  "balance_usd": "-1.90",
  "balance_cents": -190,
  "projected_cost_cents": 40,
  "projected_balance_after_cents": -230,
  "floor_cents": -200,
  "message": "Your balance is $-1.90. This operation would take it to approximately $-2.30, which is below the $-2.00 limit. Top up $10.00 to continue."
}
```

The app receives a machine-readable `reason` code and a human-readable `message`. What the app **shows** the user (blocked UI, grayed button, dialog) is Michael's call and has not been decided.

---

## Limitations

1. **Translation can breach the floor from positive balance.** At the upper bound ($2.70 projected), a user with balance $0.69 would be refused even though balance is positive. This is conservative — the alternative is allowing work that could reach −$2.01. The $2.70 projection is the max; typical translations cost ~$1.55.

2. **Projected costs are estimates.** If actual costs exceed projections, a charge could in theory push balance below −$2.00 (since `charge()` no longer blocks). The projections use conservative upper bounds to make this unlikely. The floor provides a $2.00 buffer.

3. **No per-operation type routing in `check_news_quota` / `check_tour_quota` beyond tour vs news.** Translation operations would need their own entry point to use the `translation_generate` projected cost. Currently translations are charged but not gated through `check_tour_quota` — they would need separate integration.

4. **D41 does not exist in `DECISIONS.md`** (latest is D31). The directive is stated verbatim in the task description and attributed to Michael. It should be recorded as a formal decision.
