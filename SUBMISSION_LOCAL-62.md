##### READY FOR REVIEW

## LOCAL-62 — Wallet in Settings + Paywall (Flutter)

**Commit:** `84f9bad`  
**Branch:** `kiro/local62-wallet-ui`  
**Base:** `storied`  
**Commit count from storied:** 1  

---

## Per-file changes

| File | Action | Lines |
|------|--------|-------|
| `audio_tour_app/lib/services/wallet_service.dart` | Created | 309 |
| `audio_tour_app/lib/screens/wallet_screen.dart` | Created | 481 |
| `audio_tour_app/lib/screens/about_screen.dart` | Modified | +37 (Wallet section added) |
| `audio_tour_app/test/wallet_test.dart` | Created | 170 |

---

## Evidence

### flutter analyze — new/modified files (zero errors)

```
Analyzing 4 items...

warning • The value of the field '_currentServerIp' isn't used • lib/screens/about_screen.dart:34:10 • unused_field
warning • The value of the field '_usePathPrefixes' isn't used • lib/screens/about_screen.dart:36:8 • unused_field
[... remaining are all pre-existing warnings/infos in about_screen.dart ...]

20 issues found. (ran in 1.1s)
```

**All 20 issues are pre-existing in about_screen.dart** (unused fields, deprecated Radio API, BuildContext async gaps). Zero errors. Zero issues in `wallet_service.dart`, `wallet_screen.dart`, or `wallet_test.dart`.

### Widget tests — 9/9 pass

```
00:00 +0: WalletScreen — Pay-Per-Use shows balance and transactions
00:00 +1: WalletScreen — Pay-Per-Use transactions show $0.00 for cache hits
00:00 +2: WalletScreen — Pay-Per-Use top-up button shows confirmation dialog
00:00 +3: WalletScreen — Pay-Per-Use low balance shows warning
00:00 +4: WalletScreen — Free plan shows upgrade prompt, no balance
00:00 +5: WalletScreen — Unlimited plan shows cost-stop progress, not balance
00:00 +6: LowBalanceBanner renders with warning text and top-up button
00:00 +7: PaywallScreen shows all plans from API with prices
00:00 +8: PaywallScreen restore purchases link is accessible
00:00 +9: All tests passed!
```

### No hardcoded prices

```
$ grep -rn '\$2\|\$10\|\$50' lib/
(no output — exit code 1, meaning no matches)
```

### Pre-existing test debt

`test/widget_test.dart` references `MyApp` which does not exist in `main.dart` (the app class is `AudioTourApp`). This test has been failing at baseline since before this branch. Not fixed — noted only.

---

## What was built

### 1. Settings → Wallet (WalletScreen)

- **Pay-Per-Use:** Large balance display ($7.45), "This period" spend chip, top-up button, full transaction history
- **Free:** Icon + "Upgrade to generate unlimited tours" prompt with "View Plans" button
- **Unlimited:** Monthly allowance progress bar ($18.75 / $25.00, 75% used), no fake balance, no top-up

### 2. Transaction history

Each row is plain-language per spec:
- `Tour: French Riviera biking — $0.35`
- `Downloaded — no charge` (cache hit, shows $0.00)
- `Translation: Uffizi Gallery → French — $0.25`
- `Credit top-up — +$10.00`

### 3. Paywall / upgrade (PaywallScreen)

- Three plan cards with features, prices from API (not hardcoded)
- Subscribe buttons for paid plans (placeholder flow — requires App Store configuration)
- "Restore Purchases" link (scrollable)
- "Popular" badge on Pay-Per-Use

### 4. Low-balance banner (LowBalanceBanner)

- Reusable widget: orange bar with warning icon + "Top Up" button
- Rendered when `low_balance: true` from API (balance < $2.00 threshold)
- Copy is explicit: "Top up to keep generating" — no auto-charge language

### 5. Mock API (USE_MOCK_WALLET flag)

`useMockWallet = true` in `wallet_service.dart`. The mock implements all 4 API endpoints:
- `GET /wallet/<user_id>` → plan, balance, spend, cost_stop, low_balance
- `GET /wallet/<user_id>/transactions?limit=50` → transaction list
- `GET /plans/available` → plan features and prices
- `POST /wallet/<user_id>/topup` → adds credits

`WalletTestHelper` allows switching mock scenarios in tests.

---

## Findings for LEAD

### 1. Version discrepancy

`remind_mobile_ai.md` says **v2.1.1+9** on `services-migration` (head `f72ee23`).  
`audio_tour_app/pubspec.yaml` on `storied` (this worktree's base) says **2.2.0+1**.  
These are different lineages. Not reconciled per instructions.

### 2. Existing entitlement gate in cloud path

`remind_mobile_ai.md:40` records that cloud tour generation already sends `user_id` because *"Gateway requires it for quota/entitlements check"*. The `Endpoints.apiHeaders()` already attaches `X-API-Key` and `X-App-Attestation` headers for protected services (orchestrator, translation) in cloud mode.

**This means an entitlements check already exists at the gateway level.** The Subscribed wallet/billing system should extend this existing gate — the gateway already knows the user_id and can enforce quota. Adding a separate client-side entitlement check would duplicate it. The wallet mock is built against the assumption that the backend `/wallet` endpoints sit behind the same gateway.

### 3. Server address

The app uses `Endpoints.base(Service.orchestrator)` which resolves to `https://api.audioura.com` in cloud mode (baked in via `_defaultCloudBaseUrl`). No hardcoded IPs in wallet code. The wallet service routes through the same `Endpoints.get/post` helpers.

### 4. Android build

Cannot build APK on this Mac Mini. The documented path is Ubuntu VM with `bash build_flutter_clean.sh`. Widget tests + flutter analyze are the verifiable evidence from this machine.

### 5. SUBSCRIBED_DESIGN.md location

File exists at `/Users/micha/Audioura/SUBSCRIBED_DESIGN.md`, not in the worktree. Read it as instructed. The implementation follows it.
