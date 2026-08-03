##### READY FOR REVIEW

## LOCAL-172: Tour Reuse Charges, Not Refunds (D47)

**Commit:** `dfa4643`
**Branch:** `kiro/local172-tour-reuse-charges`
**Base:** `subscribed`

---

### Per-File Changes

| File | Change |
|------|--------|
| `tour_orchestrator_service.py` | Removed ~40-line `service_credit:reuse` refund block on the `already_exists` path. Replaced with a comment and log line explaining D47 charge-retention. The `store_failed` path (genuine DB error) still issues `service_credit` per D14. |
| `tests/test_local156_charge_without_catalogue.py` | Updated to assert charge is RETAINED on reuse (was: assert `service_credit` refund issued). Step 5 renamed. Wallet row count expectation changed from 3 (topup+charge+credit) to 2 (topup+charge). Added D47 history comment in module docstring. |
| `tests/test_local172_tour_reuse_charges.py` | **NEW.** 18 assertions: fresh/reuse charge equivalence, cost_ledger divergence, free-tier immunity, overdraft floor enforcement, overdraft projection verification, break-probe. |

---

### Verbatim Test Evidence

#### Exit codes — before and after

The "before" state is `subscribed` (where LOCAL-156 asserts the refund). The
LOCAL-156 test was deliberately updated with the reason in the test (as
LOCAL-163 did for D41).

| Test file | Before (subscribed) | After (this branch) |
|-----------|--------------------|--------------------|
| `test_local156_charge_without_catalogue.py` | exit 0 (16/16 — asserted refund) | exit 0 (17/17 — asserts charge retained) |
| `test_local163_overdraft_rule.py` | exit 0 (23/23 passed) | exit 0 (23/23 passed) |
| `test_local169_ceiling_and_retranslation.py` | exit 0 (21/21 passed) | exit 0 (21/21 passed) |
| `test_local172_tour_reuse_charges.py` | N/A (new) | exit 0 (18/18 passed) |

#### Behavioural Evidence (from test_local172)

**PPU user, fresh tour → charged:**
```
fresh_tour_our_cost: $0.016824
fresh_user_charge: $0.08 (8¢)
balance_before_fresh: 1000¢
balance_after_fresh: 992¢
```

**PPU user, reused tour → charged SAME (D47):**
```
reuse_user_charge: $0.08 (8¢)
balance_before_reuse: 992¢
balance_after_reuse: 984¢

wallet_ledger charge rows (PPU user):
  key=charge:...:reuse_job, amount=-8¢, desc=Tour: Nice Museum (reused) — $0.08
  key=charge:...:fresh_job, amount=-8¢, desc=Tour: Nice Museum (fresh) — $0.08
```

**cost_ledger divergence (intended):**
```
cost_ledger_fresh_our_cost:  $0.016824  (cache_hit=False)
cost_ledger_reuse_our_cost:  $0.000000  (cache_hit=True)
```

**Free-tier user, reused tour → NO charge:**
```
free_user_subscription_tier: None
free_user_wallet_rows: 0 → 0 (unchanged)
```

**Overdraft floor — reuse refused when near −$2.00:**
```
floor_user_balance: -170¢ ($-1.70)
projected_tour_cost: 40¢
floor: -200¢ ($-2.00)
balance_minus_projected: -210¢
would_breach_floor: True
check_tour_quota result: overdraft_floor_breach
```

**Break-probe (D36):**
```
break_probe_replacement_count: 2
old_refund_code_present: False
new_d47_logic_present: True
```

---

### Findings

1. **No overdraft hole exists for tour reuse.** Unlike translation (where
   LOCAL-169 found `translation_cache_hit` projected $0.00 after it began
   charging), the tour reuse path never passes `tour_cache_hit` to
   `would_breach_floor`. The pre-flight check always uses `tour_generate`
   (projected $0.40). The `tour_cache_hit` operation type refers to a
   text-generation cache (OpenAI), not DB-level tour existence. When the
   text-gen cache hits, `our_cost = 0` and the charge block is skipped
   entirely — so $0.00 projection is correct for that case.

2. **Free-tier users are immune by design.** Two gates prevent charging:
   (a) `_get_subscription_tier(user_id)` returns `None` for free users,
   causing both the PPU and Unlimited branches in `generate_tour_text_service.py`
   to be skipped; (b) the `if user_id and _our_cost > 0:` condition would
   also skip if somehow reached. Verified in test 4.

3. **The store_failed path is unchanged.** When `store_audio_tour` returns
   `success=False` (genuine DB error), the orchestrator still issues a
   `service_credit` and sets job status to `"error"`. This is D14: no charge
   without delivery. Only the `already_exists` refund is removed.

---

### Limitations

1. **The generation still runs before reuse is detected.** The tour name
   collision is only discovered at storage time (step 5 of the orchestrator
   pipeline). Text generation + TTS still execute and cost us money. A future
   optimization could check for name collisions at the start. This is a
   cost-to-us issue (we spend ~$0.017), not a user-facing issue (user is
   correctly charged regardless).

2. **No real tour was generated.** The charge path is exercised end-to-end
   through `pricing.compute_user_charge` → `wallet_ledger.charge` with real
   DB writes, without calling the generation service or spending API credits.

3. **The cost_ledger $0.00 entry for reuse is recorded by the test, not by
   the production orchestrator.** In production, the text gen records the
   real generation cost. If the orchestrator should also record a separate
   "reuse event" cost_ledger entry at $0.00, that would require an
   additional code change. The current behaviour is: one cost_ledger row
   per generation (real cost), one wallet_ledger row per charge (kept).

4. **The ×5 multiplier and prices were not touched.**
