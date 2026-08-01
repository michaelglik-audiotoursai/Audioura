# Subscribed — Status Report for Michael

**Written:** 2026-08-01, covering work from 2026-07-31 through 2026-08-01.
**Context:** You left for a field test and asked for Subscribed to be built.
Fifteen tasks landed. Here is where things stand.

---

## 1. What works today

Each claim names its evidence.

**Cost metering** — every tour, translation, and news article records its
real API cost to a `cost_ledger` table. Proven by live generation and DB
query.

```
tour_generate          $0.0633 our cost  →  user $0.32   (×5 multiplier)
translation_generate   $0.3720 our cost  →  user $1.86   (6× a tour's cost)
news_generate          $0.0063–$0.0114 our cost
cache hits             $0.00 always (forced at metering layer)
```

**Pricing engine** — pure Decimal math, banker's rounding, no float drift.
10,000-charge drift test: $0.00 cumulative error. Multiplier is runtime-
configurable via `PRICING_MULTIPLIER` env var.

**Wallet ledger** — append-only, idempotent writes (duplicate key returns
same row), integer-cents storage. Balance derived from SUM; 1000-row rebuild
test matches cache exactly. Clawback drives balance negative without error.

**Entitlement gate** — extends the existing `check_tour_quota()`. Free tier
unchanged. PPU blocks at zero balance with topup reminder. Unlimited blocks
at $25 our-cost with a switch-to-PPU offer. Errors fail closed (deny, never
silently allow). 23 tests passing.

**Wallet API** — GET /wallet, GET /transactions, GET /plans, POST /topup.
Lives on the orchestrator Blueprint. 53 contract tests passing. Idempotent
top-up proven (same receipt key credits once).

**Charging is wired** — a real HTTP tour-generation request through the
orchestrator debits a real wallet. Proven end-to-end: POST /generate-
complete-tour → $0.028 our cost → $0.14 charged → balance dropped from $5.00
to $4.86 → GET /wallet confirmed. Cache hit: balance unchanged to the cent.
Unlimited: `monthly_cost_spent_cents` incremented by our cost, no wallet
charge.

**Tier switching** — all six transitions work (free↔ppu↔unlimited). The
critical loop closes: unlimited hits cost-stop → remedy says "switch to
PPU" → user switches → tops up → generates successfully. 14 tests passing.

**Cost ceiling** — dual-threshold ($0.15 warn, $1.30 abort). Fails closed:
if the ceiling check itself errors, delivery is aborted. Separate try/except
from metering. Proven with monkeypatched failures.

**News cache** — content-hash deduplication with 24h TTL. Second request for
same article: Polly TTS call count 236 → 236 (zero additional calls), cost
metered at $0.00, audio byte-identical (MD5 match).

**RevenueCat provider** — implements the full PaymentProvider interface
(purchase, restore, renewal, expiry, refund, billing-retry). Runs against
real Postgres. Same 15-test shared suite passes on both fake and real
providers. Webhook idempotency via event_id.

**Flutter Wallet UI** — Settings → Wallet shows balance, transaction
history, cost-stop progress (unlimited), low-balance banner, paywall with
three plans. Wired to live API (not mock). D16 vocabulary reconciled
(`ppu` everywhere). D20 monthly-fee renders as informational, not a charge.
12 widget tests passing, `flutter analyze` zero errors on wallet files.

**Isolated deployment** — `docker-compose-subscribed.yml` stands up the
billing stack on ports 5102/5100, shares Postgres, never collides with your
running containers. E2E passes 10/10 against it.

**Stale-image detection** — `check_image_freshness.py` now correctly
reports FRESH for all 15 healthy services (was falsely reporting STALE on
12 of them). Three-state: FRESH / STALE / UNKNOWN.

**Test tour pollution fixed** — `is_test` filter in `map_delivery/app.py`
(the live file, not the dead root-level one). Your Nice list returns exactly
[1, 12, 14, 17, 21, 24, 27, 28, 29].

---

## 2. What is NOT proven

Be blunt:

- **Real Apple IAP has never been called.** No App Store Connect products
  exist. No RevenueCat project exists. No sandbox tester has ever purchased
  anything. The RevenueCat provider runs against synthetic payloads only.

- **The Flutter app has not been built on a device.** Cannot build APK on
  the Mac Mini. All mobile evidence is `flutter analyze` + widget tests.
  No screenshot from a real screen exists.

- **No real user has ever been charged.** The system runs against
  `FakePaymentProvider` by default. Flipping to real requires your App
  Store credentials.

- **RevenueCat webhook format is assumed, not verified.** The real webhook
  payload structure may differ from the documented examples used in tests.

- **The charging wire was proven on a privately-rebuilt container**, not on
  the shared deployment. The shared containers still run `storied` code
  (by design — your phone uses them).

- **Translation cost is estimated, not measured.** The translation service
  returns `cache_hit` but not actual character counts. The $0.372 figure
  is calculated from typical tour length, not from real API response data.

- **TTS cost in tour breakdown is $0.00.** TTS happens at the tour-processor
  level; the cost metered at the generator level captures only the LLM spend
  ($0.063). Full end-to-end tour cost including audio synthesis is higher
  but not yet captured in a single ledger row.

- **Apple grace period not modelled.** The fake provider does immediate
  cutoff on cancellation. Real Apple subscriptions retain access until
  period_end.

- **Tier-change via HTTP will 500.** `tier_change.py` is not COPY'd into the
  orchestrator Dockerfile yet. Tests exercise it via direct Python imports.

- **Cloud Run deployment untested.** Everything runs on local Docker. The
  cloud gateway integration (`_get_auth_headers`) has not been exercised.

---

## 3. What only Michael can do

See `APPLE_SETUP.md` for the full checklist. The short version:

1. **Create three products in App Store Connect** — `com.audioura.ppu_monthly`
   ($2/month), `com.audioura.unlimited_monthly` ($50/month),
   `com.audioura.credit_topup_10` ($9.99 consumable). Apple reviews IAPs;
   expect 24–48h.

2. **Set up a RevenueCat project** — add the iOS app, create the `premium`
   entitlement, configure the webhook URL and secret.

3. **Create a sandbox tester** — throwaway Apple ID for testing without real
   money. Sandbox subscriptions renew every 5 minutes.

4. **Set three env vars and rebuild** — `PAYMENT_PROVIDER=revenuecat`,
   `REVENUECAT_API_KEY`, `REVENUECAT_WEBHOOK_SECRET`.

**Subscribed cannot ship until those products exist.** The code is ready
and waiting. Estimated time: ~1 hour of your hands plus Apple's review
queue.

---

## 4. Decisions taken in your absence

You said to make our own judgement on reversible decisions. All of these are
one-line or one-config reversals.

| Decision | What | Why | To reverse |
|----------|------|-----|------------|
| D2 | No $2 fee on top of Unlimited ($50 covers all) | "$52 billed to a customer told $50" generates refund requests | Add $2 to Unlimited billing logic |
| D3 | Hard stop at zero balance (no debt from normal use) | Letting users run up uncollectible debt through Apple | Change `charge()` to allow negative |
| D4 | Cost-stop offers switch to PPU | Silent failure at $50/month feels broken | Remove the switch offer, show message only |
| D5 | `free` tier survives unchanged | Every existing user is on it; changing silently alters behaviour | Remove the free tier handling |
| D20 | Monthly fee NOT deducted from credits | Apple already collects the fee via subscription; deducting from credits is double-billing | Change `monthly_fee()` amount_cents from 0 to -200 |
| LOCAL-90 | No proration credit on Unlimited→PPU switch | User already consumed up to $25 of our cost; crediting unused days rewards gaming | Add prorated credit calculation to `_sync_db_state_switch` |
| LOCAL-93 | $9.99 charged for $10.00 credit (Apple rounds) | Apple pricing tiers round $10 to $9.99; we credit the full $10 internally | Change credit amount to $9.99 |
| D1 | Mobile build numbers globally monotonic (next is 2.3.0+20) | Two branches had colliding build numbers; stores order by build number | Pick a different versioning scheme |

---

## 5. The economics question

A translation costs us $0.372 — roughly **6× the tour it translates**
($0.063). At the ×5 multiplier that becomes $1.86 to the user versus $0.32
for the tour.

A user who generates a tour and then translates it into 5 languages pays:
$0.32 + (5 × $1.86) = **$9.62** — nearly the entire $10 top-up gone on one
tour in six languages.

Nobody has decided whether this is right. Options:

1. **Accept it** — it reflects real cost proportions (Google Translate +
   full TTS resynthesis is genuinely expensive).
2. **Cap translation charge** — e.g., max 2× the tour charge ($0.64 instead
   of $1.86).
3. **Lower the multiplier for translations only** — breaks the uniform-×5
   simplicity.

The measured translation cost ($0.372) is an estimate, not an exact figure.
The translation service does not report actual character counts, so there is
some uncertainty. But the 6:1 ratio is real.

---

## 6. Open risks

**Tour 29 deletion incident (D23).** During autonomous operation, tour 29
(your French Riviera Biking Tour, the one on your phone) and its
translations 34/35 were deleted from `audio_tours`. Detected by luck;
restored from the ZIP on disk. Row count is back to 60.

**Cause: never identified.** No task worktree contains `DELETE FROM
audio_tours`. Leading hypothesis is test cleanup reaching real rows. Guards
now in place: 5-minute row-count snapshot, alert on falling count,
`CLAUDE.md` now forbids any task from deleting from `audio_tours`.

**Michael's app path currently works** — tour 29 downloads at 7,408,370
bytes. But whatever caused the deletion was never found, only mitigated.

**Other risks:**

- The charging wire was proven on a privately-rebuilt container that is not
  the one your phone talks to. Merging `subscribed` into `storied` and
  rebuilding is what makes billing live — and that is your call.

- Three containers are genuinely STALE (running LOCAL-86 private images).
  A full rebuild from compose would fix them but was avoided while you were
  field-testing.

- The venue-coherence gate (LOCAL-85) was rewritten because it blocked
  delivery of correct Matisse tours. The new logic is less aggressive —
  it catches genuine drift but may miss edge cases where stops reference
  venues with non-standard French naming patterns.

---

## Reference table

| Feature / Component | Task(s) |
|---|---|
| Cost metering (per-operation ledger) | LOCAL-60 |
| Payment provider interface + fake | LOCAL-61 |
| Wallet UI (Flutter) | LOCAL-62, LOCAL-87 |
| Stale-image detection | LOCAL-63, LOCAL-89 |
| Cost ceiling enforcement (fail-closed) | LOCAL-64 |
| Pricing engine (×5, Decimal, bankers) | LOCAL-65 |
| Wallet ledger (append-only, idempotent) | LOCAL-66 |
| Entitlement gate (tier dispatch) | LOCAL-67 |
| Wallet API endpoints | LOCAL-68 |
| News cost metering | LOCAL-69 |
| Corpus verification (post-rebuild) | LOCAL-71 |
| Thin-corpus rule A/B test | LOCAL-72 |
| News cache (content-hash dedup) | LOCAL-73 |
| Visitor facts rebase | LOCAL-74, LOCAL-91 |
| Palais Lascaris fact density | LOCAL-75 |
| Test DB port fix (5432→5433) | LOCAL-77 |
| Dispatcher base-branch fix | LOCAL-80 |
| Subscribed test port fix | LOCAL-81 |
| End-to-end integration test | LOCAL-82 |
| Charging wire (billing actually works) | LOCAL-83 |
| HTTP charging proof (real request debits wallet) | LOCAL-84 |
| Venue-coherence gate fix | LOCAL-85 |
| Flask send_file compatibility | LOCAL-86 |
| Test tour pollution prevention | LOCAL-88 |
| Tier switching (all 6 transitions) | LOCAL-90 |
| Isolated deployment (docker-compose-subscribed.yml) | LOCAL-92 |
| RevenueCat provider + APPLE_SETUP.md | LOCAL-93 |
