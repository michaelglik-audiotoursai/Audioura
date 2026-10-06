# Subscription levels — design of record (D613, 2026-10-06)

**Source:** Michael's spec, ClickUp [wdvrdayu5a](https://app.clickup.com/t/wdvrdayu5a).
**Supersedes:** the wallet / Pay-Per-Use / Unlimited model in `SUBSCRIBED_DESIGN.md` (2026-07-31).
Its tables (`wallet_*`, `cost_ledger`) stay in place, read-only, and nothing new writes to them.
**Purpose:** cap what free tour generation can cost us without destroying long-term value.
**Where it runs:** Subscribed only, on the local Mac Mini stack. It does not reach GCloud until
Michael says so.

## Cost reality the tiers are built on
- The expensive operation is a **fresh generation**: OpenAI, plus Gemini grounded search, plus
  TTS. That is about $1–2 for a 7-stop museum tour (LOCAL-594 measures it exactly).
- Close to free: listening, downloads, cache hits, reusing an existing translation, and edits
  that only re-voice text.

## Levels

| | L1 Install | L2 Free | L3 $10 pack | L4 $25 round | Tester |
|---|---|---|---|---|---|
| Acquired | auto on install | queue, or referral; auto on install if L2 seats < 50 AND the queue is empty | consumable IAP $10 | consumable IAP $25 | Michael's invitation |
| Listen, download, articles, reuse translations, edit existing (no new stops) | ✅ | ✅ | ✅ | ✅ | ✅ |
| New tours | ❌ | 1/day, 3/month, ≤5 stops, **by reference only** (no new grounding) | 5 fresh per pack, ≤10 stops | 25 ops (new + edit, any mix), ≤25 stops | 10/day, 50/month, ≤5 stops |
| Edits that add stops | ❌ | ❌ | 5 per pack, ≤10 new stops/edit | in the 25 ops, ≤10 new stops/edit | ≤5 new stops/edit |
| Sell tours | ❌ | ❌ | ❌ | ✅ (later; flag only) | ❌ |
| Referrals → an L2 seat | — | — | 3 lifetime | 5 / month | 3 |
| Cap | — | 100 concurrent seats | — | — | 50 tours/month |
| Inactivity | — | 7 idle days → L1, must re-queue | none | none | none |

Every number is a column in `plans` (changeable by SQL, no redeploy). The code holds no tier
constants.

## Billing (build exactly this)
- L3 and L4 are **consumables**. They are never auto-renewing subscriptions, and nothing is ever
  charged automatically.
- **Anniversary = most recent payment date + 1 calendar month, clamped to the month's last day**
  (Jan 31 → Feb 28/29; May 31 → Jun 30). Paying early resets it and replaces the allowance:
  unused units do not carry over. *LEAD decision; Michael may overturn.*
- At or after the anniversary, nothing changes server-side until the device next opens the app.
  Then the app asks: **renew** (buy again) or **drop to L1**.
- A 3-day warning is shown in the app before the anniversary.
- **No personal identity** is stored: only the anonymous `secret_id` / device. There are no
  refunds.
- Downgrade from L4 to L3 means lapsing to L1 and then buying L3.
- Purchases are verified **server-side** (Apple App Store Server API / Google Play Developer API)
  against the transaction id before an allowance is granted. The same transaction id can never
  grant twice.

## L2 seats and queue
- At most 100 concurrent L2 seats, counting referral seats.
- On install, the device is auto-granted L2 only if seats in use < 50 AND the queue is empty.
  Otherwise it starts at L1 and can join the FIFO queue.
- **Notification (LEAD decision, no email):** when a seat frees, the first device in the queue
  gets a **claim offer stored server-side**. The app shows it the next time it opens (and by push
  later, once push exists). The offer expires after 72 h and then passes to the next device.
- **Eviction:** after 7 days with no activity at all (any app open, listen, download or article),
  the device drops to L1 and the seat is freed. This runs as an hourly job and is idempotent.
- Referral grants (L3 3 lifetime, L4 5/month, Tester 3) count against the 100 cap and are refused
  when it is full.

## L2 "by reference"
An L2 tour may only **reuse researched stops** that already exist: the stop pool (LOCAL-590) and
existing tours of that venue, re-sequenced and re-narrated. It must issue **zero grounded Gemini
requests and zero SERP queries**. If there is no reusable material for the request, the listener
gets an actionable refusal ("this place hasn't been researched yet — upgrade or pick a nearby
tour"), never a fresh generation. A test must prove the grounding counter stays at 0.

## Migration of existing local users (LEAD decision)
- Michael's devices, all 2 current `unlimited` users and the 35 `ppu` test users → **tester**.
- The 35 `free` users → **L2**, grandfathered and counted in the cap. The 7-day eviction then
  applies normally.
- The old `plans` rows are kept, and nothing is deleted.

## Delivery (Kiro tasks)
| task | scope | base |
|---|---|---|
| LOCAL-595 | schema + levels in `plans`, per-device allowance state, enforcement in `entitlements.py` + orchestrator + editing, structured refusals, `/entitlements/me` API, user migration, purchase-grant endpoint with sandbox verification stub | subscribed |
| LOCAL-596 | L2 seats: auto-grant, FIFO queue, claim offers, 7-day eviction job, referral grants against the cap | after 595 |
| LOCAL-597 | L2 by-reference generation path, zero grounding | after 594 |
| LOCAL-598 | app: plan screen, consumable IAP (StoreKit 2 / Play Billing), renew/lapse prompt, 3-day warning, queue/claim UI | after 595 |
| Michael | create the two consumable products in App Store Connect / Play Console (outward-facing) | when 598 is ready |
