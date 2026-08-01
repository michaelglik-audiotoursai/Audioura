# Subscribed — design of record

**Owner:** Michael. **Branch:** `subscribed` (off `storied`).
**Written:** 2026-07-31, from Michael's spec before a 3-day field trip.

This is the reference every LOCAL-6x task builds against. Where a task and
this document disagree, this document wins — unless Michael says otherwise.

---

## The model, in Michael's words

> Two subscription types:
> 1. Pay-Per-Use by incremented never returned back $10 USD credits refilled
>    when only $2.00 left. That includes no limit on anything including
>    future purchases of the tours. $2USD per month fee. Calculate all the
>    work we do and multiply it by 5 to get the money back from credits.
>    Includes both articles and tours.
> 2. Unlimited. $50USD per month. Includes all what is in Pay-Per-Use but
>    stops when we spent 0.5 of the $50 per month.
>
> In any case should show Wallet to users in settings.

This is **usage-metered billing**, not feature tiers. The existing `plans`
table models quota dimensions (`tours_per_day`, `tour_max_poi`, …) and is
the wrong shape for it. Do not force the new model into those columns; add
what is needed alongside and leave `free` working.

---

## Tiers

| | Pay-Per-Use | Unlimited |
|---|---|---|
| Base fee | $2.00 / month | $50.00 / month |
| Credits | $10.00 top-ups, non-refundable | n/a |
| Top-up trigger | balance < $2.00 → **reminder**, user confirms | n/a |
| Limits | none | service stops when **our cost** reaches $25.00 (0.5 × $50) in the month |
| Covers | tours **and** news articles | same |

Every number above is **configuration, not a constant**. Michael retunes
from the field. See "Configuration" below.

## Pricing rule

**User price = our true cost × 5.**

The multiplier is config. What "our true cost" means is the subtle part:

- **Cache hit costs ≈ $0.** Michael, 2026-07-31: *"it cost to us and to our
  clients nothing when/if they download a tour already pre-created or
  pre-translated."* A download of an existing tour or existing translation
  must meter at approximately zero — storage and bandwidth only, not the
  original generation cost. **Charging generation cost on a cache hit is
  the single worst bug this feature can have.**
- **Fresh generation** meters the real API spend. Measured: a 15-stop tour
  costs **$0.069**; the code ceiling in `cost_ceiling_monitor.py` is $0.15.
  At ×5 that is $0.35–$0.75 to the user.
- **Future higher-cost services** are coming and must not need a redesign:
  photo-of-a-POI → tour extension, and news article generation. Meter by
  *operation type* with per-type cost capture, never a hardcoded per-tour
  price.
- **Sharing a tour** with another user is expected to be free.

### Economic sanity, for context

At $0.069/tour, $10 of credit buys ~28 fresh tours. A user would need ~144
fresh tours/month before $50 Unlimited beats pay-per-use. That maths only
holds for *fresh* tours — with most consumption being cache hits and news,
Unlimited is insurance against the expensive tail. Do not "fix" the pricing;
just make sure cache hits meter at zero.

---

## Apple constraint — this is not negotiable

Credits are a **consumable** IAP. Apple requires explicit user
authentication for every consumable purchase. **There is no mechanism to
auto-charge when a balance drops.** RevenueCat does not change this; it is a
StoreKit rule.

Michael's ruling, 2026-07-31: *"then we should include reminder instead of
auto-charge."*

So: at balance < $2.00, send a reminder (push + in-app banner). The user
taps once and authenticates. Never imply a charge will happen by itself.

The $2/month and $50/month fees ARE auto-renewable subscriptions and renew
normally.

**Refunds:** Apple grants them directly on user request and we cannot block
it. Credits are non-refundable *on our side*, but the ledger must handle a
clawback — a negative adjustment against an already-spent balance. Michael:
*"No Problem. That only impacts how we calculate corporate revenue vs.
cashflow."* So: record it, never crash on it, allow the balance to go
negative rather than losing the record.

---

## Payment provider

**Apple IAP via RevenueCat** (Michael's choice).

Build behind a `PaymentProvider` interface with a working **fake** for now.
Michael has not created App Store Connect products and is away — any task
that blocks on real IAP credentials has failed. The fake must support:
purchase, restore, renewal, expiry, refund/clawback, and a low-balance
event, so every path is testable without Apple.

---

## Wallet

Michael: *"In any case should show Wallet to users in settings."*

Settings → Wallet shows: current balance, plan, this period's spend, a
transaction history (date, operation, our cost, charged amount), and a
top-up button. On Unlimited it shows the monthly cost-stop progress instead
of a balance.

The transaction list is the user-facing proof of the ×5 rule. It must be
legible to a non-technical person: "Tour: French Riviera biking — $0.35",
not a token count.

---

## Configuration (all runtime-tunable, no code change)

```
PRICING_MULTIPLIER          = 5.0
PPU_MONTHLY_FEE_USD         = 2.00
CREDIT_TOPUP_USD            = 10.00
CREDIT_LOW_BALANCE_USD      = 2.00      # reminder threshold
UNLIMITED_MONTHLY_FEE_USD   = 50.00
UNLIMITED_COST_STOP_FRACTION= 0.5       # stop at 0.5 x fee in OUR cost
CACHE_HIT_COST_USD          = 0.00
```

---

## Decisions — made by LEAD, recorded in `DECISIONS.md`

These were previously listed as open questions for Michael. Per his ruling
of 2026-07-31 they are decided; he overturns what he dislikes.

1. **$2/month fee on Unlimited?** No — $50 covers everything. (D2)
2. **Zero balance on Pay-Per-Use?** Hard stop plus a top-up reminder; no
   negative balance from normal use. A refund clawback may still go
   negative, and is recorded. (D3)
3. **Unlimited hits its cost stop?** Clear message naming what happened,
   plus an offer to switch to Pay-Per-Use for the rest of the month. Never
   fail silently. (D4)
4. **Does `free` survive?** Yes, unchanged. Every existing user is on it. (D5)
5. **Mobile versioning.** Build numbers are globally monotonic across all
   branches; next build is `2.3.0+20`. Today `storied` carries 2.2.0+**1**
   while `services-migration` carries 2.1.1+**9** — a higher version string
   with a lower build number, which app stores cannot order safely. (D1)
6. **Pricing calibration is blocked**, not by a question but by a bug: the
   corpus ImportError means measured cost excludes story mining
   (`search: 0.0`). Fix LOCAL-63, then re-measure before setting prices. (D7)

---

## Isolated Deployment — `docker-compose-subscribed.yml` (LOCAL-92)

### Why

The shared containers (`audioura-*`) run from `storied` and do not include
`wallet_api.py`. Any Subscribed task that needs `GET /wallet/...` must bring
up its own orchestrator built from the `subscribed` branch.

### What it does

`docker-compose-subscribed.yml` stands up:

| Service | Container Name | Host Port | Internal Port |
|---------|---------------|-----------|---------------|
| Orchestrator (with wallet_api) | `subscribed-orchestrator` | **5102** | 5002 |
| Tour Generator (with cache) | `subscribed-generator` | **5100** | 5000 |

Both join the existing `development_default` network and point at the
master's `postgres-2` container — no second database.

### Quick commands

```bash
# Bring up (from any worktree that has the file):
docker compose -f docker-compose-subscribed.yml up -d --build

# Run e2e tests against it:
ORCHESTRATOR_URL=http://localhost:5102 python3 tests/test_local82_subscribed_e2e.py

# Tear down (leaves nothing behind):
docker compose -f docker-compose-subscribed.yml down
```

### Constraints

- **Never collides** with the shared `audioura-*` containers (distinct names
  and ports).
- **Never modifies** `docker-compose-master.yml`.
- **Shares Postgres** — billing tables are real. Test users are created/cleaned
  per the helper in each test.
- OPENAI_API_KEY and SERP_API_KEY must be exported in the shell (or the
  generator won't generate new tours; cached lookups still work without them).
