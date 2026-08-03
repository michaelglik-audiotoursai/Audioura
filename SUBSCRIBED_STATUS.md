# Subscribed — Status Report for Michael

**Originally written:** 2026-08-01  
**Refreshed:** 2026-08-02 (LOCAL-122)  
**Purpose:** Single authoritative reference on Subscribed-tier billing, what
is proven, what is stubbed, and what needs Michael.

---

## ⚠️ Two-document decision

`RETURN_BRIEFING.md` (on `storied`) is the broader document — it covers tour
quality, infrastructure, swipe personalization, unwired features, Docker state,
and decisions. This document covers **Subscribed billing only** — the economic
system, the payment stack, the wallet, and what makes billing go live.

**Reasoning:** Folding this into `RETURN_BRIEFING.md` would bury billing
specifics (the exact cost table, the tier-switch matrix, the Apple setup
checklist) inside a 200-line general briefing. Michael needs both a high-level
"what happened" document (the briefing) and a deep-dive into "how does billing
work and what do I do to ship it" (this one). The briefing links here for
detail; this one does not repeat what the briefing covers.

If the two ever disagree, **this document governs on billing topics**; the
briefing governs on everything else.

---

## 1. What works today (branch: `subscribed`)

Each claim names its branch and evidence source.

### Cost metering

**Branch: `subscribed` (merged from `storied` via LOCAL-60)**

Every tour, translation, and news article records its real API cost to a
`cost_ledger` table.

```
tour_generate          $0.068 our cost  →  user $0.34   (×5 multiplier)
                       ~~$0.063~~ [CORRECTED: LOCAL-100 measured mean $0.0682 over 5 runs]
translation_generate   $0.532 our cost  →  user $2.66   (8× a tour's cost) [MEASURED: LOCAL-135, n=5]
news_generate          $0.006–$0.011 our cost
cache hits             $0.00 always
```

### Pricing engine

**Branch: `subscribed`**

Pure Decimal math, banker's rounding, no float drift. 10,000-charge drift
test: $0.00 cumulative error. Multiplier is runtime-configurable via
`PRICING_MULTIPLIER` env var.

### Wallet ledger

**Branch: `subscribed`**

Append-only, idempotent writes (duplicate key returns same row), integer-cents
storage. Balance derived from SUM; 1000-row rebuild test matches cache exactly.
Clawback drives balance negative without error.

### Entitlement gate

**Branch: `subscribed`**

Extends the existing `check_tour_quota()`. Free tier unchanged. PPU blocks at
zero balance with topup reminder. Unlimited blocks at $25 our-cost with a
switch-to-PPU offer. Errors fail closed (deny, never silently allow). 23 tests
passing.

### Wallet API

**Branch: `subscribed`**

GET /wallet, GET /transactions, GET /plans, POST /topup. Lives on the
orchestrator Blueprint. 53 contract tests passing. Idempotent top-up proven
(same receipt key credits once).

### Charging is wired

**Branch: `subscribed`**

A real HTTP tour-generation request through the orchestrator debits a real
wallet. Proven end-to-end: POST /generate-complete-tour → $0.028 our cost →
$0.14 charged → balance dropped from $5.00 to $4.86 → GET /wallet confirmed.
Cache hit: balance unchanged. Unlimited: `monthly_cost_spent_cents`
incremented by our cost, no wallet charge.

### Tier switching

**Branch: `subscribed`**

All six transitions work (free↔ppu↔unlimited). The critical loop closes:
unlimited hits cost-stop → remedy says "switch to PPU" → user switches → tops
up → generates successfully. 14 tests passing.

### RevenueCat provider

**Branch: `subscribed`**

Implements the full PaymentProvider interface (purchase, restore, renewal,
expiry, refund, billing-retry). Runs against real Postgres. Same 15-test
shared suite passes on both fake and real providers. Webhook idempotency via
event_id.

**`APPLE_SETUP.md` exists** (since LOCAL-93) with a step-by-step enrollment
guide for App Store Connect products, RevenueCat project setup, sandbox
testers, and the three env vars to flip.

### Cost ceiling

**Branch: `subscribed`**

Dual-threshold ($0.15 warn, $1.30 abort). Fails closed: if the ceiling check
itself errors, delivery is aborted. Proven with monkeypatched failures.

**Limitation (unchanged from D15):** the check runs *after* generation
completes, so it prevents *delivering* an over-budget tour but not the API
*spend*. At $0.068/tour, this is two orders of magnitude below $1.30.

### Flutter Wallet UI

**Branch: `subscribed`**

Settings → Wallet shows balance, transaction history, cost-stop progress
(unlimited), low-balance banner, paywall with three plans. Wired to live API
(not mock). 12 widget tests passing, `flutter analyze` zero errors on wallet
files.

**Cannot be verified on device from this Mac Mini.** Evidence: widget tests +
flutter analyze only. No APK build possible (Docker builder hung — see §4).

### Isolated deployment

**Branch: `subscribed`**

`docker-compose-subscribed.yml` stands up the billing stack on ports
5102/5100, shares Postgres, never collides with shared (storied) containers.

---

## 2. What is NOT proven

- **Real Apple IAP has never been called.** No App Store Connect products
  exist. No RevenueCat project exists. No sandbox tester has ever purchased
  anything. The RevenueCat provider runs against synthetic payloads only.

- **The Flutter app has not been built on a device from this Mac.** Cannot
  build APK (Docker builder hung). All mobile evidence is `flutter analyze` +
  widget tests. No screenshot from a real screen exists.

- **No real user has ever been charged.** The system runs against
  `FakePaymentProvider` by default. Flipping to real requires App Store
  credentials.

- **RevenueCat webhook format is assumed, not verified.** The real webhook
  payload structure may differ from the documented examples used in tests.

- **The charging wire was proven on a privately-rebuilt container**, not on the
  shared deployment. The shared containers still run `storied` code (by design
  — Michael's phone uses them, per D24).

- ~~**Tier-change via HTTP will 500.** `tier_change.py` is not COPY'd into the orchestrator Dockerfile yet.~~
  **CORRECTED (LOCAL-90):** Tier switching works over HTTP. All six transitions
  tested against the subscribed stack. The `Dockerfile.orchestrator` now
  includes the tier-change module.

- ~~**Translation cost is estimated, not measured.** The translation service
  returns `cache_hit` but not actual character counts. The $0.372 figure is
  calculated from typical tour length, not from real API response data.~~
  **CORRECTED (LOCAL-135):** Translation cost measured at **$0.532** mean over
  5 tours (n=5, stdev $0.050, range $0.475–$0.591). The old $0.372 estimate
  was wrong for two reasons: (1) used Google Translate rate ($20/1M) but the
  service uses AWS Translate ($15/1M); (2) did not account for the service
  translating each stop twice (full text + TTS-stripped text). The double
  translation dominates — lower per-char rate × 2 passes = higher total.

- **TTS cost in tour breakdown is $0.00.** TTS happens at the tour-processor
  level; the cost metered at the generator level captures only the LLM spend.
  Full end-to-end tour cost including audio synthesis is higher but not yet
  captured in a single ledger row.

- **Apple grace period not modelled.** The fake provider does immediate cutoff
  on cancellation. Real Apple subscriptions retain access until period_end.

- **Cloud Run deployment untested.** Everything runs on local Docker.

---

## 3. What only Michael can do

See `APPLE_SETUP.md` for the full checklist. The short version:

1. **Create three products in App Store Connect** —
   `com.audioura.ppu_monthly` ($2/month),
   `com.audioura.unlimited_monthly` ($50/month),
   `com.audioura.credit_topup_10` ($9.99 consumable).

2. **Set up a RevenueCat project** — add the iOS app, create the `premium`
   entitlement, configure the webhook URL and secret.

3. **Create a sandbox tester** — throwaway Apple ID for testing without real
   money.

4. **Set three env vars and rebuild** — `PAYMENT_PROVIDER=revenuecat`,
   `REVENUECAT_API_KEY`, `REVENUECAT_WEBHOOK_SECRET`.

**Subscribed cannot ship until those products exist.** Estimated time: ~1 hour
of your hands plus Apple's review queue.

---

## 4. Current blockers

### Docker builder hung

A three-line Alpine image times out at 180 seconds. Running containers stay
healthy; the problem is exclusively in the builder. Any task requiring a
container rebuild is blocked. The subscribed-orchestrator and
tourquality-* stacks were already built before the hang began and still run.

**Impact on Subscribed:** No new container image can be built. If a code fix
touches server Python and needs deployment, it cannot be deployed until the
builder is fixed or the machine is cleaned.

### Port map mismatch (app → server) — TESTED (LOCAL-152)

**Branch: `subscribed` (Dart code)**

The app's `Endpoints._localPorts[Service.orchestrator]` hardcodes **5002**
(the shared/storied orchestrator). The subscribed-orchestrator with wallet +
preference routes lives on **5102**. On Michael's phone talking to the Mac Mini
(192.168.0.218:5002), preferences and wallet 404 because that orchestrator does
not have the subscribed code.

**Tested 2026-08-02 (LOCAL-152).** Previously inferred; now verified by HTTP.

#### Subscribed stack (port 5102): NOT RUNNING

The `subscribed-orchestrator` and `subscribed-generator` containers are not up.
`curl http://localhost:5102/health` → connection refused. The subscribed stack
has no running containers.

#### Shared stack (port 5002): wallet routes NOT registered

| Route | Method | HTTP code | Body type | Verdict |
|---|---|---|---|---|
| `/wallet/<id>` | GET | 404 | Generic Flask HTML | **NOT REGISTERED** — route absent from image |
| `/wallet/<id>/transactions` | GET | 404 | Generic Flask HTML | **NOT REGISTERED** |
| `/plans/available` | GET | 404 | Generic Flask HTML | **NOT REGISTERED** |
| `/wallet/<id>/topup` | POST | 404 | Generic Flask HTML | **NOT REGISTERED** |
| `/user/<id>/stop-feedback` | POST | 404 | Generic Flask HTML | **NOT REGISTERED** |

**Distinction applied (LOCAL-150 method):** All five return `<!DOCTYPE HTML
...><title>404 Not Found</title>` — the Flask default for an unregistered URL.
This is NOT a structured JSON 404 (which would mean the route exists but the
resource is absent). These routes genuinely do not exist in the running image.

**Root cause confirmed:** `wallet_api.py`, `wallet_ledger.py`, `pricing.py`,
`swipe_preference_service.py`, and `tier_change.py` are absent from the
container filesystem (`find /app -name "*.py"` shows only 5 files:
`cost_ceiling_monitor.py`, `cost_meter.py`, `cost_rates.py`,
`entitlements.py`, `tour_orchestrator_service.py`).

**Flask url_map confirms** only 7 routes are registered on 5002:
`DELETE /delete-account/<secret_id>`, `GET /download/<job_id>`,
`POST /generate-complete-tour`, `GET /health`, `GET /jobs`,
`GET /serve/<job_id>`, `GET /status/<job_id>`, `POST /tour-status`.

#### The real finding

**The app cannot reach the wallet at all today.** The subscribed stack is not
running (connection refused on 5102), the shared stack doesn't have the code
(generic 404 on 5002), and the app hardcodes port 5002. No code path exists
that would allow the wallet screen to load data from a real backend today.

The original note ("will 404") was correct — but understated the situation:
it's not "would 404 if built from stale code" but rather "does 404 right now
and has no fallback." The inference was right; the mechanism (image predates
wallet code entirely, not stale image with wrong code) was slightly wrong.

**`POST /topup` — UNVERIFIED for functional exercise.** Could not be safely
tested because: (1) the route doesn't exist on either stack, so there is
nothing to call; (2) even if it existed, any body with a valid `product_id`
would credit a wallet (the endpoint is designed to succeed idempotently on
any new product_id). The route's absence from `url_map` is definitive proof
it is not registered — no HTTP exercise was possible or needed.

#### Evidence: wallet_ledger unchanged

Row count before: **163**. Row count after: **163**. No rows created or modified.

**Fix options (unchanged):**
1. Merge `subscribed` into `storied` and rebuild the shared stack (Michael's
   call — this is "go live")
2. Change the port map in the Dart client to 5102 (breaks storied-only usage)
3. Deploy `subscribed` code to the 5002 container (violates D24 while Michael
   is away)

Reported in SUBMISSION_LOCAL-109.

---

## 5. The economics question (updated LOCAL-135)

A translation costs us **$0.532** — roughly **8× the tour it translates**
($0.068). At the ×5 multiplier that becomes **$2.66** to the user versus $0.34
for the tour.

A user who generates a tour and then translates it into 5 languages pays:
$0.34 + (5 × $2.66) = **$13.64** — exceeding the entire $10 top-up on one
tour in six languages.

**Not decided.** Options:
1. Accept it (reflects real cost)
2. Cap translation charge (e.g., max 2× the tour charge)
3. Lower the multiplier for translations only

The measured translation cost ($0.532, n=5, stdev $0.050) is **higher** than
the previous $0.372 estimate. The 8:1 ratio is measured, not estimated.

**Root cause of the higher cost:** the translation service translates each
stop twice per language (once for the text file, once nav-stripped for Polly
TTS input). The old estimate assumed a single translation pass.

---

## 6. Tour quality gate — cleared

**Branch: `storied` (tour generation code lives here)**

Five independent runs on the isolated verification stack:

| Metric | Value |
|--------|-------|
| Mean score | 98.8 |
| Worst run | 87.8 |
| Gate threshold | 75 |
| Spread | 20.6 |
| Mean cost/tour | $0.0682 |

The base score alone (81.25–87.50) clears the gate in every run without needing
callbacks. Evidence: SUBMISSION_LOCAL-100.

**Michael's field test is the next step.** That is his call.

---

## 7. Swipe personalization loop — closed end to end

**Branch: `subscribed` (schema, service, wiring, Dart UI)**

The full loop:
1. User swipes like/dislike during playback → offline queue → POST /user/<id>/stop-feedback → 200
2. Server updates user_class_prefs (Beta-count model)
3. Next generation reads prefs → `bias_stop_ordering()` → different stop order
4. Cold start = today's behavior exactly (quality-only)

**Proven over HTTP** (SUBMISSION_LOCAL-107, LOCAL-109). Route registered on
subscribed-orchestrator (port 5102).

**Known gap — CONFIRMED (LOCAL-152):** The shared orchestrator (port 5002,
`storied` branch) does NOT have the preference route. Tested 2026-08-02:
`POST /user/test-user-999/stop-feedback` → generic Flask HTML 404. The Dart
app targets 5002. Swipes from a real device **do** silently fail against the
shared stack. This is not an inference — it is measured.

---

## 8. Decisions with billing consequences

Full list in `DECISIONS.md`. Billing-relevant subset:

| # | Decision | Consequence |
|---|----------|-------------|
| D2 | $50 Unlimited has no $2 fee on top | Total is $50, not $52 |
| D3 | Hard stop at zero balance | No negative from normal use; clawback can go negative |
| D4 | Unlimited cost-stop → offer PPU switch | Not silent; shows message |
| D5 | Free plan survives unchanged | No migration needed |
| D16 | `ppu` is canonical tier ID | DB primary key |
| D20 | Monthly fee NOT deducted from credits | $10 topup = $10.00 usable balance |
| LOCAL-90 | No proration credit on Unlimited→PPU | Prevents gaming |
| LOCAL-93 | $9.99 Apple price → $10.00 credit internally | Apple rounding absorbed |

---

## 9. Corrections from the original document

These claims appeared in the 2026-08-01 version and are now known to be
inaccurate or incomplete:

| Original claim | Correction | Source |
|----------------|------------|--------|
| "tour_generate $0.0633 our cost" | Mean measured at $0.0682 over 5 runs | LOCAL-100 |
| "Tier-change via HTTP will 500" | All six transitions work over HTTP after LOCAL-90 merged the module into the Dockerfile | SUBMISSION_LOCAL-90, D24 |
| "Stale-image detection — correctly reports FRESH for all 15 healthy services" | Three containers are genuinely STALE (running LOCAL-86 private images). Detection works; the images it finds stale *are* stale. | Original §6 already noted this; phrasing corrected. |
| Row count stated as 60 | Row count is now **88** (grew through test generations, all marked `is_test=true`) | SUBMISSION_LOCAL-103, LOCAL-104 |
| "translation_generate $0.372 our cost" | Measured at **$0.532** mean (n=5, stdev $0.050). Old estimate used wrong API (Google $20/1M vs actual AWS $15/1M) and missed double-translation per stop. | LOCAL-135 |

---

## 10. What is proven, what is stubbed, what needs Michael

### PROVEN (exercised with real data on real Postgres)

- Cost metering (per-operation, per-job)
- Wallet ledger (append-only, idempotent, SUM-derived balance)
- Entitlement gate (all three tiers dispatch correctly)
- Pricing engine (×5, Decimal, drift-free)
- Tier switching (all 6 transitions)
- Wallet API (4 endpoints, 53 contract tests)
- Charging wire (HTTP request → wallet debit → balance change)
- Cost ceiling (fail-closed, dual-threshold)
- News cache (content-hash dedup, $0.00 on cache hit)
- Swipe loop (gesture → preference → reordered tour, over HTTP)
- Sharing (POST /tour/share → 200, round trip confirmed, free)
- Tour quality gate (mean 98.8, worst 87.8, gate ≥75)

### STUBBED (code exists, exercised against synthetic data only)

- RevenueCat provider (synthetic webhook payloads, not real Apple receipts)
- Wallet UI (widget tests only, no device build, no screenshot)
- Apple grace period (immediate cutoff in fake provider)
- ~~Translation cost ($0.372 estimated, not measured from real API response)~~
  **PROVEN (LOCAL-135):** measured $0.532 mean (n=5, stdev $0.050) from real
  tour content in the database. Includes TTS.
- TTS cost (not captured in cost_ledger; happens downstream)

### NEEDS MICHAEL

- App Store Connect products (3 IAPs) — see `APPLE_SETUP.md`
- RevenueCat project setup
- Sandbox tester creation
- Decision: merge `subscribed` into `storied` (makes billing live)
- Decision: translation pricing (accept 6:1 ratio or cap it)
- Decision: fix Docker builder (cleanup images/swap) or work around it
- Field test of tour quality on his own terms

---

## Reference table

| Feature / Component | Task(s) | Branch |
|---|---|---|
| Cost metering | LOCAL-60 | storied + subscribed |
| Payment provider interface + fake | LOCAL-61 | subscribed |
| Wallet UI (Flutter) | LOCAL-62, LOCAL-87 | subscribed |
| Stale-image detection | LOCAL-63, LOCAL-89 | storied |
| Cost ceiling | LOCAL-64 | subscribed |
| Pricing engine | LOCAL-65 | subscribed |
| Wallet ledger | LOCAL-66 | subscribed |
| Entitlement gate | LOCAL-67 | subscribed |
| Wallet API | LOCAL-68 | subscribed |
| News cost metering + cache | LOCAL-69, LOCAL-73 | storied |
| Tier switching | LOCAL-90 | subscribed |
| Isolated deployment | LOCAL-92 | subscribed |
| RevenueCat provider + APPLE_SETUP | LOCAL-93 | subscribed |
| Tour quality gate clearance | LOCAL-97, LOCAL-98, LOCAL-100 | storied |
| Swipe preferences (backend) | LOCAL-101, LOCAL-104 | subscribed |
| Swipe UI (Flutter) | LOCAL-105 | subscribed |
| Swipe loop closed | LOCAL-106, LOCAL-107, LOCAL-109 | subscribed |
| Sharing wired | LOCAL-110 | storied |
| Spine quality gate | LOCAL-111 | storied |
