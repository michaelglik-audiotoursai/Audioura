##### READY FOR REVIEW

# LOCAL-160: Wallet UX Findings — the screen shows "Free Plan / Upgrade" to a user holding $10

**Branch:** `kiro/local160-wallet-ux-findings`  
**Commit:** `61585fe`  
**Commits ahead of subscribed:** 1  

---

## Summary

Rendered the wallet screen in 6 distinct states against the live subscribed stack
(`http://192.168.0.136:5102`) using macOS desktop Flutter integration tests.
Two UX issues flagged; four states render correctly.

---

## Evidence — Verbatim Rendered Text Per State

### STATE 3: PPU, healthy balance ($10) — most common paying-user state

```
TEXT: "Available Balance"
TEXT: "$10.00"
TEXT: "This period: $0.00"
TEXT: "Pay-Per-Use"
TEXT: "Period: 8/3 – 9/2"
TEXT: "Change"
TEXT: "Top Up"
TEXT: "Transaction History"
TEXT: "Credit top-up: $10.00"
TEXT: "2m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```
✅ Correct. User sees balance, plan, and top-up option.

---

### STATE 4: PPU, low balance ($1.50, threshold $2.00)

```
TEXT: "Available Balance"
TEXT: "$1.50"
TEXT: "⚠️ Low balance — top up to continue generating"
TEXT: "This period: $8.50"
TEXT: "Pay-Per-Use"
TEXT: "Period: 8/3 – 9/2"
TEXT: "Change"
TEXT: "Top Up"
TEXT: "Transaction History"
TEXT: "Simulated tour charges (test drain)"
TEXT: "2m ago"
TEXT: "−$8.50"
TEXT: "Credit top-up: $10.00"
TEXT: "2m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```
✅ Low-balance banner appears. Threshold is $2.00 (env `CREDIT_LOW_BALANCE_USD`).

---

### STATE 1: Free tier, zero balance — default new signup

```
TEXT: "Free Plan"
TEXT: "Upgrade to generate unlimited tours and articles"
TEXT: "View Plans"
TEXT: "Free"
TEXT: "Period: 8/1 – 9/1"
TEXT: "Change"
TEXT: "Transaction History"
TEXT: "No transactions yet"
TEXT: "Wallet"
```
✅ Appropriate for a user with no credit on the free tier.

---

### STATE 2: Free tier, positive balance ($10) — ⚠️ FLAG

```
TEXT: "Free Plan"
TEXT: "Upgrade to generate unlimited tours and articles"
TEXT: "View Plans"
TEXT: "Free"
TEXT: "Period: 8/1 – 9/1"
TEXT: "Change"
TEXT: "Transaction History"
TEXT: "Credit top-up: $10.00"
TEXT: "2m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```

**API returned `balance_usd: 10.0` but the UI does not display it anywhere
in the main card.** The only hint of $10 is the `+$10.00` in transaction history.

⚠️ **FLAG: Balance the user holds is not shown.** `_buildFreeCard()` hardcodes
the "Free Plan / Upgrade" prompt regardless of `balanceUsd`. A user would
conclude "I'm on the free plan and haven't paid" even though they hold $10.

**Reachability:** `/wallet/<id>/topup` succeeds for free-tier users (confirmed
in test — status 200, balance becomes $10). This state is reachable.

---

### STATE 5: PPU, negative balance (-$0.50) — ⚠️ FLAG

```
TEXT: "Available Balance"
TEXT: "$-0.50"
TEXT: "⚠️ Low balance — top up to continue generating"
TEXT: "This period: $10.50"
TEXT: "Pay-Per-Use"
TEXT: "Period: 8/3 – 9/2"
TEXT: "Change"
TEXT: "Top Up"
TEXT: "Transaction History"
TEXT: "Overcharge (test negative)"
TEXT: "2m ago"
TEXT: "−$0.50"
TEXT: "Simulated full drain (test)"
TEXT: "2m ago"
TEXT: "−$10.00"
TEXT: "Credit top-up: $10.00"
TEXT: "2m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```

⚠️ **FLAG: Negative balance rendered ambiguously.** `$-0.50` is not how
people read money (should be `-$0.50`). No messaging explains whether the
user owes this amount, whether generation is blocked, or what to do.

The Dart code: `'\$${wallet.balanceUsd.toStringAsFixed(2)}'` — the `$` prefix
is unconditionally prepended to the number, including its sign.

---

### STATE 6: Unlimited, cost-stop at 50% ($12.50 / $25.00)

```
TEXT: "Monthly Allowance"
TEXT: "$12.50 / $25.00"
TEXT: "50% used"
TEXT: "Unlimited"
TEXT: "Period: 8/3 – 9/2"
TEXT: "Change"
TEXT: "Transaction History"
TEXT: "No transactions yet"
TEXT: "Wallet"
```
✅ `cost_stop_progress` **is rendered** — progress bar and percentage both work.
The cost stop limit is $25 (50% of the $50 monthly fee, per `UNLIMITED_COST_STOP_FRACTION`).

---

## Flags Summary

| # | Category | Details |
|---|----------|---------|
| 1 | Balance held but not shown | Free-tier user with $10.00: screen shows "Free Plan / Upgrade", balance invisible except in transaction history. |
| 2 | Negative balance rendered ambiguously | PPU at -$0.50 renders as `$-0.50` — dollar sign before the minus. No explanation of consequences. |

**Not flagged (correct behavior):**
- All numbers render to exactly 2 decimal places.
- No state produces a spinner, error, or blank screen.
- Low-balance banner fires correctly at ≤$2.00.
- Cost-stop progress renders correctly for unlimited users.
- Transaction amounts match API values.

---

## Test Users Created

| Label | User ID | Ledger before | Ledger after |
|-------|---------|:---:|:---:|
| free_zero | `test_ux160_free_zero_7cb67df9` | 0 | 0 |
| free_positive | `test_ux160_free_pos_7cb67df9` | 0 | 1 |
| ppu_healthy | `test_ux160_ppu_healthy_7cb67df9` | 0 | 1 |
| ppu_low | `test_ux160_ppu_low_7cb67df9` | 0 | 2 |
| ppu_zero | `test_ux160_ppu_zero_7cb67df9` | 0 | 3 |
| unlimited_mid | `test_ux160_unlim_7cb67df9` | 0 | 0 |

`demo_michael_1785726297` **untouched**.

---

## Per-file Changes

| File | Change |
|------|--------|
| `WALLET_UX_FINDINGS.md` | **New:** Full findings document (deliverable) |
| `audio_tour_app/integration_test/wallet_ux_findings_test.dart` | **New:** Flutter integration test — renders wallet for 6 users |
| `tests/test_local160_wallet_ux_findings.py` | **New:** Python script — creates users, sets states, queries API |
| `tests/local160_findings.json` | **New:** Machine-readable findings for cross-referencing |

---

## Limitations

1. **macOS desktop, not phone** — exercises identical Dart code, WalletService, HTTP
   contract, and rendering logic. Does not test Android-specific font sizes or
   hardware interactions.

2. **No screenshot** — macOS integration tests dump the widget tree text, not pixels.
   The text output is the complete set of rendered `Text` widgets.

3. **Negative balance state is artificial** — the entitlement gate (`entitlements.py`)
   blocks generation when balance ≤ 0, so a negative balance likely requires a race
   condition (concurrent generation + charge). However, the API *does* return negative
   values and the Dart code *does* render them, so the formatting issue is real.

4. **"Free tier + positive balance" reachability** — confirmed the top-up endpoint
   accepts free-tier users. Whether this happens via the normal app flow (View Plans
   → top up before tier switch completes) or only via edge cases is a product question.

5. **No Dart code was modified** — this task reports only, per constraint.

---

## How to Reproduce

```bash
# Python: create users + query API
python3 tests/test_local160_wallet_ux_findings.py

# Flutter: render wallet screen for all 6 states
cd audio_tour_app
flutter test integration_test/wallet_ux_findings_test.dart \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
  --dart-define=UX160_RUN_ID=7cb67df9 \
  -d macos
```

---

## git status --short (final)

```
(empty — clean working tree)
```
