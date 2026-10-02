##### READY FOR REVIEW

# LOCAL-161: Show users the money they hold, and format a negative balance correctly

**Branch:** `kiro/local161-wallet-balance-visibility`  
**Commit:** `b8fdcfc`  
**Commits ahead of subscribed:** 1  

---

## Summary

Two narrow fixes to `wallet_screen.dart`:

1. **Free-tier balance now visible** when non-zero. A user who holds $10 on the free plan now sees "Available Balance / $10.00" below the upgrade prompt. Zero-balance free users still see only "Free Plan / Upgrade" (no distracting "$0.00").

2. **Negative balance formatted correctly.** Introduced a `formatUsd()` helper that produces `-$0.50` instead of `$-0.50`. Applied to the single `toStringAsFixed(2)` site that can go negative.

---

## Rendered Before/After

### State 1: Free tier + $10 balance

**BEFORE** (from `WALLET_UX_FINDINGS.md` State 2):
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

**AFTER** (rendered 2026-08-03, user `test_161_free_pos_efa21ef2`):
```
TEXT: "Free Plan"
TEXT: "Upgrade to generate unlimited tours and articles"
TEXT: "Available Balance"
TEXT: "$10.00"
TEXT: "View Plans"
TEXT: "Free"
TEXT: "Period: 8/1 – 9/1"
TEXT: "Change"
TEXT: "Transaction History"
TEXT: "Credit top-up: $10.00"
TEXT: "0m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```

**Balance now visible.** Upgrade prompt preserved. Card layout unchanged.

---

### State 2: Free tier + $0 balance

**AFTER** (rendered, user `test_161_free_zero_efa21ef2`):
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

**No "$0.00" displayed.** Identical to the pre-fix behavior. The condition `wallet.balanceUsd != 0.0` suppresses the balance section.

---

### State 3: PPU negative balance (-$0.50)

**BEFORE** (from `WALLET_UX_FINDINGS.md` State 5):
```
TEXT: "Available Balance"
TEXT: "$-0.50"
```

**AFTER** (rendered, user `test_161_ppu_neg_efa21ef2`):
```
TEXT: "Available Balance"
TEXT: "-$0.50"
TEXT: "⚠️ Low balance — top up to continue generating"
TEXT: "This period: $10.50"
TEXT: "Pay-Per-Use"
TEXT: "Period: 8/3 – 9/2"
TEXT: "Change"
TEXT: "Top Up"
TEXT: "Transaction History"
TEXT: "Overcharge (test negative)"
TEXT: "0m ago"
TEXT: "−$10.50"
TEXT: "Credit top-up: $10.00"
TEXT: "0m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```

**`-$0.50`** — minus before dollar sign, conventional formatting.

---

### Regression: PPU healthy ($10) — UNCHANGED

**AFTER** (rendered, user `test_161_ppu_healthy_efa21ef2`):
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
TEXT: "0m ago"
TEXT: "+$10.00"
TEXT: "Wallet"
```

Matches LOCAL-160 State 3 exactly.

---

### Regression: Unlimited cost-stop (50%) — UNCHANGED

**AFTER** (rendered, user `test_161_unlim_efa21ef2`):
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

Matches LOCAL-160 State 6 exactly.

---

## Signed-money sites — audit

Six `toStringAsFixed(2)` sites exist in `wallet_screen.dart`:

| # | Expression | Can go negative? | Changed? | Reason |
|---|-----------|-----------------|----------|--------|
| 1 | `wallet.balanceUsd` (PPU balance card) | **YES** | ✅ Uses `formatUsd()` | This is the bug. Negative balances are reachable via overcharges. |
| 2 | `wallet.periodSpendUsd` ("This period: $X.XX") | No | ❌ Left as-is | Accumulates from zero upward — sum of charges, always ≥ 0. |
| 3 | `progress.usedUsd` (cost-stop used) | No | ❌ Left as-is | Absolute usage amount for unlimited tier — always ≥ 0. |
| 4 | `progress.limitUsd` (cost-stop limit) | No | ❌ Left as-is | Config value ($25) — always positive. |
| 5 | `txn.chargedUsd.abs()` (credit transaction) | No | ❌ Left as-is | Already uses `.abs()` and prefixes with `+$`. |
| 6 | `txn.chargedUsd` (debit transaction) | No | ❌ Left as-is | Only reached for debits (positive amounts), prefixed with `−$`. |

**The `formatUsd` helper is also used in the new free-card balance display** (site 1 equivalent, also can be negative if a free user somehow overdrafts — defensive).

---

## Test users created

| Label | User ID | Plan | Balance | Ledger rows |
|-------|---------|------|---------|-------------|
| free_positive | `test_161_free_pos_efa21ef2` | free | $10.00 | 1 |
| free_zero | `test_161_free_zero_efa21ef2` | free | $0.00 | 0 |
| ppu_negative | `test_161_ppu_neg_efa21ef2` | ppu | -$0.50 | 2 |
| ppu_healthy | `test_161_ppu_healthy_efa21ef2` | ppu | $10.00 | 1 |
| unlimited_mid | `test_161_unlim_efa21ef2` | unlimited | $0.00 | 0 |

`demo_michael_1785726297` **untouched** (ledger count = 3, confirmed).

---

## flutter analyze (verbatim)

```
Analyzing wallet_screen.dart...                                 
No issues found! (ran in 0.7s)
```

---

## Existing mock widget tests

```
00:00 +12: All tests passed!
```

All 12 pre-existing wallet widget tests pass unmodified.

---

## Per-file changes

| File | Change |
|------|--------|
| `audio_tour_app/lib/screens/wallet_screen.dart` | +`formatUsd()` helper (8 lines at top). `_buildFreeCard()` → `_buildFreeCard(WalletData wallet)` with conditional balance section. PPU balance uses `formatUsd()` instead of raw string interpolation. |
| `audio_tour_app/integration_test/wallet_balance_visibility_test.dart` | **New:** Integration test (5 states, rendered against live stack) |
| `tests/test_local161_wallet_balance_visibility.py` | **New:** Python script to create test users with correct state |

---

## How to reproduce

```bash
# 1. Create test users
python3 tests/test_local161_wallet_balance_visibility.py

# 2. Run integration test (uses run_id from step 1)
cd audio_tour_app
flutter test integration_test/wallet_balance_visibility_test.dart \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
  --dart-define=LOCAL161_RUN_ID=efa21ef2 \
  -d macos

# 3. Mock widget tests (no network needed)
flutter test test/wallet_test.dart
```

---

## Limitations

1. **No messaging about what a negative balance means** — whether the user is blocked or merely owes is a product decision Michael has not made. The UI shows the number; it does not explain consequences.

2. **A larger redesign might be better.** The free-tier card now shows the balance in a smaller font (24px vs PPU's 42px) below the upgrade text. A more cohesive approach would unify both cards into one layout with a conditional upgrade banner. However, the task asked for minimal change, so I kept the existing card structure and added only the balance section. If Michael wants a redesign, it should be a separate ticket.

3. **macOS desktop, not phone** — renders identical Dart code, HTTP contract, and widget tree as the Android APK. Does not test Android-specific rendering (fonts, hardware buttons).

---

## git status --short (final)

```
(empty — clean working tree)
```
