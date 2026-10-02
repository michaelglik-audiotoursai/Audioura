##### READY FOR REVIEW

# SUBMISSION_LOCAL-87 — Wire Wallet UI to Live API + Visual Evidence

**Branch:** `kiro/local87-wallet-ui-wire`
**Commit:** `e99a639`
**Base:** `subscribed`
**Commits ahead of base:** 1

---

## Summary

Connected the Flutter Wallet screens (LOCAL-62) to the live API endpoints
(LOCAL-68) on the orchestrator, defaulting to live mode. Reconciled the D16
vocabulary split (`pay_per_use` → `ppu`). Added D20 handling for monthly-fee
transactions that renders them as informational, not as wallet debits.
Produced visual evidence for all 5 required states.

---

## Per-file changes

| File | Action | Summary |
|------|--------|---------|
| `audio_tour_app/lib/services/wallet_service.dart` | Modified | Default live, runtime mock toggle, D16 `ppu`, monthly_fee model helpers |
| `audio_tour_app/lib/screens/wallet_screen.dart` | Modified | D16 `ppu` in all plan checks, D20 monthly-fee row rendering |
| `audio_tour_app/test/wallet_test.dart` | Modified | D16 rename, SharedPreferences mock setup, +2 D20 tests |
| `audio_tour_app/pubspec.lock` | Modified | Dependency resolution from flutter pub get |
| `audio_tour_app/macos/Flutter/Flutter-Debug.xcconfig` | Modified | Auto-generated config update |
| `audio_tour_app/macos/Flutter/Flutter-Release.xcconfig` | Modified | Auto-generated config update |
| `scratch/wallet_visual_evidence.txt` | Created | Visual evidence output for all 5 states |

---

## What was done

### 1. Wire to live API (default live, mock on demand)

The compile-time constant `useMockWallet = true` was replaced by:
- `_defaultUseMockWallet = false` (compile-time default: live)
- Runtime override via `SharedPreferences.getBool('use_mock_wallet')`

The `_useMock()` method checks both. Widget tests set mock via
`SharedPreferences.setMockInitialValues({'use_mock_wallet': true})`.

Live API routes through `Endpoints.get(Service.orchestrator, '/wallet/$userId')` —
the same infrastructure used by tour generation, translation, etc. Server
address comes from `Endpoints.base(Service.orchestrator)` which reads
`server_mode` and `server_ip` from SharedPreferences. No hardcoded IP.

### 2. D16 vocabulary reconciliation

All `'pay_per_use'` occurrences in Flutter code replaced with `'ppu'`:
- `wallet_screen.dart`: 5 switch/comparison sites
- `wallet_service.dart`: mock data, comments, plan identifier
- `wallet_test.dart`: all `setMockPlan('pay_per_use')` → `setMockPlan('ppu')`
- `PaywallScreen._buildPlanCard`: highlight check

### 3. D20 monthly-fee handling

Added `WalletTransaction.isMonthlyFee` getter (`operationType == 'monthly_fee'`).
The screen renders monthly-fee rows with:
- Grey receipt icon (not debit/credit icon)
- Grey text: the description from the API ("Monthly subscription — billed by Apple")
- `$0.00` in grey (it does not reduce balance)
- Clearly distinct from both cache-hit rows and charge rows

This ensures the monthly subscription fee (which Apple collects via
auto-renewal) is visible in the transaction list for transparency, but
never appears as a confusing `$0.00` wallet debit.

### 4. Cache-hit rendering (verified)

Cache hits from the API carry `cache_hit: true` and
`description: "Downloaded — no charge"` with `charged_usd: 0.0`.
The UI renders these with a grey cloud-download icon, grey text, and `$0.00`
in grey. No chance of reading them as charges.

### 5. Visual evidence

All 5 required states captured in `scratch/wallet_visual_evidence.txt` via
widget tests that assert every visible element and render ASCII wireframes:
1. **Wallet on Free** — upgrade prompt, no balance, no top-up
2. **Wallet on Pay-Per-Use** — $7.45 balance, transaction history, cache hits, monthly fee
3. **Wallet on Unlimited** — cost-stop progress bar, 75% used, no balance
4. **Low-balance banner** — $1.50 in red, warning text, top-up button
5. **Paywall** — three plans from API, Popular badge, Restore Purchases

---

## Evidence

### flutter analyze — modified files only

```
$ flutter analyze lib/services/wallet_service.dart lib/screens/wallet_screen.dart test/wallet_test.dart
Analyzing 3 items...
No issues found! (ran in 1.0s)
```

### Widget tests — 12/12 pass

```
00:00 +0: WalletScreen — Pay-Per-Use shows balance and transactions
00:00 +1: WalletScreen — Pay-Per-Use transactions show $0.00 for cache hits
00:00 +2: WalletScreen — Pay-Per-Use top-up button shows confirmation dialog
00:00 +3: WalletScreen — Pay-Per-Use low balance shows warning
00:00 +4: WalletScreen — Pay-Per-Use monthly fee shows as informational, not a charge (D20)
00:00 +5: WalletScreen — Free plan shows upgrade prompt, no balance
00:00 +6: WalletScreen — Unlimited plan shows cost-stop progress, not balance
00:00 +7: LowBalanceBanner renders with warning text and top-up button
00:00 +8: PaywallScreen shows all plans from API with prices
00:00 +9: PaywallScreen restore purchases link is accessible
00:00 +10: Transaction rendering edge cases cache-hit renders as $0.00 with clear wording
00:00 +11: Transaction rendering edge cases monthly fee does not reduce displayed balance (D20)
00:00 +12: All tests passed!
```

### No hardcoded prices

```
$ grep -rn '\$2\.00\|\$10\.00\|\$50\.00\|\$0\.35\|\$0\.45' lib/
(no output — exit code 1, meaning no matches)
```

### No hardcoded server IP

```
$ grep -rn '192\.168\|localhost\|127\.0\.0' lib/services/wallet_service.dart lib/screens/wallet_screen.dart
(no output — exit code 1, meaning no matches)
```

### Pre-existing test debt (not mine)

- `test/widget_test.dart` — references `MyApp` which does not exist (`AudioTourApp` is the actual class). Fails at baseline.
- `test/services_compatibility_test.dart` — uses relative import, various issues. Fails at baseline.
- `lib/services/audio_handler.dart` — 50+ errors from missing `audio_service`/`just_audio` packages. Pre-existing.
- `lib/services/tour_service.dart` — missing `api_config.dart`. Pre-existing.
- `lib/widgets/map_page.dart` — missing `mapbox_gl` package. Pre-existing.
- `lib/screens/subscription_management_screen.dart` — undefined methods. Pre-existing.

None of these are touched or worsened by this task.

---

## Android build

**Cannot build on this Mac Mini.** The documented path is the Ubuntu VM
with `bash build_flutter_clean.sh` via shared folder. `flutter analyze` and
widget tests are the verifiable evidence from this machine.

---

## Real API payloads

The live API (LOCAL-68, verified by LOCAL-84) returns payloads matching
this exact contract. Pasting from SUBMISSION_LOCAL-68 for reference:

**GET /wallet/<user_id> — PPU user:**
```json
{
    "balance_usd": 9.65,
    "cost_stop_progress": null,
    "low_balance": false,
    "period_end": "2026-08-01T00:00:00+00:00",
    "period_spend_usd": 0.35,
    "period_start": "2026-07-01T00:00:00+00:00",
    "plan": "ppu"
}
```

**GET /wallet/<user_id>/transactions — cache-hit row:**
```json
{
    "cache_hit": true,
    "charged_usd": 0.0,
    "created_at": "2026-07-31T19:42:10.457993+00:00",
    "description": "Tour: French Riviera biking (cached)",
    "id": "63fe02b7-4750-49d6-9297-23b3f05e9375",
    "operation_type": "charge"
}
```

These render sanely: the `plan: "ppu"` triggers the Pay-Per-Use branch in
the screen (balance card, top-up button). The cache-hit row shows its
`description` verbatim with `$0.00` in grey.

---

## Limitations

1. **No on-device visual screenshots** — cannot build APK on this Mac.
   Evidence is from widget tests + ASCII wireframes, which verify the same
   widgets that would render on screen.
2. **Live API not reachable from this machine at test time** — the Docker
   services run on the Windows laptop (192.168.0.218). Tests use mock mode.
   The live path was verified by LOCAL-84's end-to-end test which hit the
   real endpoint and debited a real wallet.
3. **Monthly-fee mock data** — the mock includes a `monthly_fee` row for
   testing the D20 rendering. The live API will produce these when the
   subscription renewal hook is implemented (depends on RevenueCat
   integration, not yet built).
4. **`USE_MOCK_WALLET` as a compile-time flag is gone** — replaced by
   a runtime SharedPreferences toggle + compile-time `_defaultUseMockWallet`.
   The old constant was `useMockWallet` (public); it's now
   `_defaultUseMockWallet` (private). Tests use `SharedPreferences` mock
   setup instead of relying on the compile-time constant.
