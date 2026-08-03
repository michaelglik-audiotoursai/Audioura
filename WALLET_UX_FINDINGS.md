# Wallet UX Findings — LOCAL-160

All states rendered against the **live subscribed stack** at `http://192.168.0.136:5102`
on 2026-08-03 via `flutter test -d macos` (same Dart code as the APK).

Run ID: `7cb67df9`

---

## State 3: PPU, healthy balance — *most common state for paying users*

**API response:**
```json
{"plan":"ppu","balance_usd":10.0,"period_spend_usd":0.0,"low_balance":false,
 "period_start":"2026-08-03T13:38:02","period_end":"2026-09-02T13:38:02","cost_stop_progress":null}
```

**Rendered text (verbatim):**
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

**User reading:** A user sees their balance prominently, knows they're on PPU, and sees the option to top up — straightforward and correct.

---

## State 4: PPU, low balance ($1.50, threshold is $2.00)

**API response:**
```json
{"plan":"ppu","balance_usd":1.5,"period_spend_usd":8.5,"low_balance":true,
 "period_start":"2026-08-03T13:38:02","period_end":"2026-09-02T13:38:02","cost_stop_progress":null}
```

**Rendered text (verbatim):**
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

**User reading:** Clear and actionable — balance shows in red, warning banner says to top up, Top Up button is right there. This state works well.

**Low-balance threshold:** The `low_balance` flag fires at `balance_cents <= 200` (i.e., ≤ $2.00). This is driven by `CREDIT_LOW_BALANCE_USD` in `wallet_ledger.py` (default `2.00`, env-overridable).

---

## State 1: Free tier, zero balance — *default state for new signups*

**API response:**
```json
{"plan":"free","balance_usd":0.0,"period_spend_usd":0.0,"low_balance":false,
 "period_start":"2026-08-01T00:00:00","period_end":"2026-09-01T00:00:00","cost_stop_progress":null}
```

**Rendered text (verbatim):**
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

**User reading:** User understands they're on free, sees a clear path to upgrade, and no confusing financial information is shown.

---

## State 2: Free tier, positive balance ($10.00) — ⚠️ FINDING

**API response:**
```json
{"plan":"free","balance_usd":10.0,"period_spend_usd":0.0,"low_balance":false,
 "period_start":"2026-08-01T00:00:00","period_end":"2026-09-01T00:00:00","cost_stop_progress":null}
```

**Rendered text (verbatim):**
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

**User reading:** The user holds $10.00 in credit but the main card says "Free Plan / Upgrade" — they would reasonably wonder: "did my payment fail?" or "where is my money?" The only signal that they have credit is the `+$10.00` in the transaction history, which is easy to miss.

**⚠️ FLAG: Balance the user holds is not shown.** The `_buildFreeCard()` method hardcodes the upgrade prompt regardless of `balanceUsd`. The API returns `balance_usd: 10.0` but the Dart code never displays it for `plan == 'free'`.

**Reachability:** This state is reachable — the `/wallet/<id>/topup` endpoint succeeds for free-tier users. In practice, this would happen if a user tops up via the App Store before their tier-change request completes, or if a tier downgrade preserves leftover credit.

---

## State 5: PPU, zero or negative balance — ⚠️ FINDING

### At $0.00:

**API response:**
```json
{"plan":"ppu","balance_usd":0.0,"period_spend_usd":10.0,"low_balance":true,
 "period_start":"2026-08-03T13:38:02","period_end":"2026-09-02T13:38:02","cost_stop_progress":null}
```

**Rendered:** `"$0.00"` with low-balance banner — acceptable.

### At -$0.50:

**API response:**
```json
{"plan":"ppu","balance_usd":-0.5,"period_spend_usd":10.5,"low_balance":true,
 "period_start":"2026-08-03T13:38:02","period_end":"2026-09-02T13:38:02","cost_stop_progress":null}
```

**Rendered text (verbatim):**
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

**User reading:** "My balance is… dollar minus fifty cents?" The string `$-0.50` is not how people read money. A user would be confused about whether they owe money, what happens next, and whether their account is in some error state.

**⚠️ FLAG: Negative balance rendered ambiguously.** The Dart code does `'\$${wallet.balanceUsd.toStringAsFixed(2)}'` which produces `$-0.50` instead of the conventional `-$0.50` or even better: "You owe $0.50". There is also no messaging explaining what happens with a negative balance (can the user still generate? will they be blocked?).

---

## State 6: Unlimited, partway through monthly cost-stop

**API response:**
```json
{"plan":"unlimited","balance_usd":0.0,"period_spend_usd":0.0,"low_balance":false,
 "period_start":"2026-08-03T13:38:02","period_end":"2026-09-02T13:38:02",
 "cost_stop_progress":{"used_usd":12.5,"limit_usd":25.0}}
```

**Rendered text (verbatim):**
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

**User reading:** The user sees their usage against the monthly allowance with a progress bar — clear that they're partway through, no dollar-balance confusion since unlimited users don't have a balance. This renders well.

**Note:** `cost_stop_progress` *is* rendered (contrary to the concern in the task brief). The Dart code handles it via `_buildCostStopCard`.

---

## Summary of Flags

| # | Category | State | Issue |
|---|----------|-------|-------|
| 1 | **Balance held but not shown** | Free tier + $10 credit | `_buildFreeCard()` shows "Free Plan / Upgrade" regardless of balance. The $10 is only visible in transaction history as "+$10.00". |
| 2 | **Negative balance rendered ambiguously** | PPU at -$0.50 | Renders as `$-0.50` instead of `-$0.50`. No explanation of consequences. |

**Things that work correctly:**
- PPU healthy: balance, period spend, and transactions all match API.
- PPU low: banner appears at the right threshold ($2.00), balance in red, clear CTA.
- PPU zero: shows `$0.00` with low-balance warning — acceptable.
- Unlimited cost-stop: progress bar and percentage both render correctly.
- All numbers use exactly 2 decimal places in the rendered output.
- No spinner, error, or blank state for any of the 6 states tested.

---

## Test Users Created

| Label | User ID | Plan | Balance | Ledger rows |
|-------|---------|------|---------|-------------|
| free_zero | `test_ux160_free_zero_7cb67df9` | free | $0.00 | 0 |
| free_positive | `test_ux160_free_pos_7cb67df9` | free | $10.00 | 1 |
| ppu_healthy | `test_ux160_ppu_healthy_7cb67df9` | ppu | $10.00 | 1 |
| ppu_low | `test_ux160_ppu_low_7cb67df9` | ppu | $1.50 | 2 |
| ppu_zero | `test_ux160_ppu_zero_7cb67df9` | ppu | -$0.50 | 3 |
| unlimited_mid | `test_ux160_unlim_7cb67df9` | unlimited | $0.00 | 0 |

`demo_michael_1785726297` **untouched**.

---

## How to Reproduce

```bash
# 1. Create test users (Python — exercises API + DB)
python3 tests/test_local160_wallet_ux_findings.py

# 2. Render wallet screen (Flutter — actual widget tree)
cd audio_tour_app
flutter test integration_test/wallet_ux_findings_test.dart \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136 \
  --dart-define=UX160_RUN_ID=7cb67df9 \
  -d macos
```
