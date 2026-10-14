# SUBMISSION — LOCAL-690: Communities, phase 1 (D657, D658 + addenda)

**Branch:** `LOCAL-690-communities` (from `subscribed` = `62f0220b`)
**Agent:** Mac Mini Kiro
**Scope:** Server (tables, endpoints, pass purchase via the existing stub/Apple-verify
path, expiry, codes, RSS parsing) + app (Generate split, community page, join flow,
Listen origin label, map badge). **Payouts are OUT of scope** (later task).

Base verified: `git merge-base --is-ancestor 62f0220b HEAD` exits 0.

---

## What was built

### Rulings → implementation (D657 / D658 + both addenda)

| Ruling | Where |
|---|---|
| A community has an owner, name, description, organiser (name/photo/bio/contact), rules/waiver, Free or paid, pass options, Listed or Private | `communities` table; `POST /communities`; `CreateCommunityScreen` |
| Waiver communities are always Private | DB `CHECK (NOT (has_waiver AND visibility='listed'))` + server forces `private` on create + `CommunityRules.forcedVisibility` in the app |
| Listed needs a location | DB `CHECK (visibility<>'listed' OR location set)` + create validates |
| Content = owner-HOSTED MP3s: a list of links OR one RSS feed; Audioura stores only metadata (title, order, URL); NO content check | `community_episodes` (metadata only); `POST /communities/<id>/episodes` (links); `POST /communities/<id>/import-feed` (RSS) via `communities_rss.py` |
| Joining: the invite/share code goes into the existing Home search box; member → the tour opens; non-member → "This tour belongs to \<Community\>. Join to listen" → community page | `home_screen` share-code dispatch falls through to `CommunitiesService.resolveByCode` → `CommunityPageScreen`; server `GET /communities/by-code/<code>` returns `join_message` |
| Passes are NON-RENEWING price-ladder products; one product per price serves every community; our server stores community + expiry; nothing renews; reminder 3 days before and at expiry | `community_pass_products` (price × length), `community_memberships.expires_at`; `/purchases/verify` → `verify_community_pass` (expiry = now + duration_days; buying again extends the one row); `POST /communities/reminders/run` |
| Downloaded community audio stays playable after expiry; expiry only blocks new codes/episodes (server-checked) | `GET /communities/<id>/episodes` returns 403 for an expired/non-member (new content blocked); the server never serves/deletes downloaded files. App documents the rule with `CommunityRules.downloadByDefault()` |
| Download community tours by default | `CommunityRules.downloadByDefault()` = true (player uses the existing download path) |
| Placement: no new tab — organisers create from the Generate tab ("Tour \| Community") with a ready invite message; joined tours appear in Listen with an origin label; ⋯ → Origin; About gets a Communities button | `tour_generator_screen` Tour\|Community `SegmentedButton`; `invite_message` on create; `my_communities_screen` origin label + ⋯ Origin; About "Communities" button |
| Listed communities with a location show on the Home map with a community badge | `GET /communities/map` (listed + located + not-disabled, `badge:community`); `home_screen._loadCommunityPins` renders a purple pin with a groups badge |
| Report button → owner; Audioura keeps a per-community off switch | `POST /communities/<id>/report` returns `owner_user_id`; `communities.disabled` |
| Free communities (book club) skip passes | `POST /communities/<id>/join` (free only; paid = 402) |

### Server files
- **`migration/sql/029_communities.sql`** — 6 tables, additive & idempotent. Seeds 20
  pass products (5 prices $3/$5/$10/$20/$50 × 4 lengths day/week/month/year;
  durations 1/7/30/365).
- **`user-tracking/communities_api.py`** — Flask blueprint `communities_bp` (registered
  in `user-tracking/app.py`). Endpoints: create, get, by-code, join, episodes (add &
  list), import-feed, report, map, mine, reminders/run. Pure helpers `compute_expiry`,
  `is_membership_active`, `is_community_pass_product`.
- **`user-tracking/communities_rss.py`** — RSS/Atom parser, **metadata only** (title,
  order, URL). `parse_feed` is pure; `fetch_and_parse` takes an injectable `http_get` so
  tests mock HTTP (no real request). No content check.
- **`user-tracking/entitlements_api.py`** — `/purchases/verify` now routes
  `audioura.pass.*` products to `communities_api.verify_community_pass` (same stub/Apple
  path as tour unlocks; idempotent on `purchases.transaction_id`).

### App files (Flutter)
- **`lib/services/communities_models.dart`** — dependency-free models + `CommunityRules`
  pure helpers (unit-testable).
- **`lib/services/communities_service.dart`** — networked client over `Service.userDb`.
- **`lib/screens/community_page_screen.dart`** — organiser, description, rules + waiver
  (accept gate), passes (buy), episodes (active members), my status, report.
- **`lib/screens/communities_about_screen.dart`** — About Communities + create form →
  ready invite dialog.
- **`lib/screens/my_communities_screen.dart`** — Listen "My communities" list, origin
  label, ⋯ → Origin.
- Edits: `iap_service.dart` (community-pass buy + test purchase, `community_id` in the
  verify body), `about_screen.dart`, `tour_generator_screen.dart`, `home_screen.dart`,
  `my_tours_screen.dart`.

---

## Tests — every rule covered

### Server — `tests/test_local690_communities.py` (24 tests, all pass)
```
IAP_VERIFY_MODE=stub ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true \
  python3 -m pytest tests/test_local690_communities.py -q
# 24 passed
```
Covers: RSS parse (metadata only, order, URL; mock-HTTP injected getter; bad body raises);
create rules (owner/name required, waiver→Private, Listed→location, paid→passes, unique
8-char code with a digit); invite-code resolve + join framing + disabled → 404; free join
vs paid refuses free join; pass purchase grants expiry = now + duration; idempotent;
buying again extends the single membership row; pass-not-offered refused; expiry blocks new
episode listing (owner & active member can, expired & non-member 403); feed import +
re-import upsert on guid (no duplicates); owner-only feed import; reminders (3-days-before
and at-expiry, each once); map lists only Listed+located+not-disabled; report → owner;
mine lists origin; pure `compute_expiry`/`is_membership_active`/`is_community_pass_product`.

### App — `audio_tour_app/test/communities_service_test.dart` (11 tests, all pass)
```
cd audio_tour_app && flutter test test/communities_service_test.dart --no-pub
# All tests passed!
```
Covers: origin label (Audioura / name / name — organiser), join framing wording, forced
visibility (waiver → private), download-by-default, defensive JSON parsing of the page /
map pin / joined community (missing fields never throw).

`flutter analyze` on all new files: **No issues**. 0 errors across all changed files
(448 pre-existing lints live in the large existing screens, unrelated to this change).
Existing `search_dispatch` + `share_code` tests still pass (43).

---

## Live test — own container, isolated DB (never the shared `audiotours`)

Live DB `audiotours_local690` was created on my own `development-postgres-2-1` container
(alias `postgres-2`, host port 5433) — the shared `audiotours` tables were never touched,
and no `-p audioura` / `audioura-*` container was used or renamed. The RSS feed was a
local fixture served through the injectable HTTP getter (no external network).

`run_local690_live.py` exercised the full flow: create a paid Listed community with passes
+ a feed → create a free community → import the feed (2 episodes) → owner adds a link (3rd
episode) → a member buys a $5/month pass (stub) → the member lists episodes (3, active) →
free join → report → map list → reminders tick. All steps returned 200/201.

### Row counts (per table written)
| table | rows |
|---|---|
| communities | 2 |
| community_pass_products | 20 |
| community_passes | 2 |
| community_memberships | 2 |
| community_episodes | 3 |
| community_reports | 1 |
| purchases | 1 |

Migration idempotency verified: re-applying `029_communities.sql` produced no errors and
`community_pass_products` stayed at 20 rows.

---

## Commits (per step)
- `613aa974` — migration 029 (tables + 20 pass products).
- `46c3cb43` — server (blueprint, RSS parser, pass dispatch) + 24 tests + live driver.
- `d809aa20` — app (client, screens, Generate split, join flow, map badge, origin, IAP).

## Honest status
- **Proven:** 24 server tests + 11 Dart tests pass; full live flow with real row counts on
  an isolated DB; migration idempotent; analyze clean on new files.
- **Not exercised live:** the real Apple/Google StoreKit pass products do not exist yet, so
  the pass purchase was proven through the `stub` path (the same stub that LOCAL-677 tour
  purchases use); the `apple` JWS branch reuses the existing verified verifier. The Flutter
  UI was verified by `flutter analyze` + unit tests, not by an on-device run.
- **Out of scope (by ticket):** owner payouts, tax forms, statements.


---

# 690C — pass catalogue = ONE product per PRICE (bounce of LOCAL-690)

LEAD review of LOCAL-690 (2026-10-14): the one deviation from D658 was that migration 029 built
the pass catalogue per **price × length** (20 products, 5 prices). D658 says Apple's non-renewing
product carries no length, so **one product per PRICE serves every community and every length** —
the LENGTH belongs to the community's pass option. Price × length would be 4× the App Store products
for Michael to create (136 for the full ladder). And prices must come from the full ladder (LOCAL-686).
690C rewrites 029 in place and threads the length through the stack.

## What changed (690B → 690C)

| Area | Before (690/690B) | After (690C) |
|------|-------------------|--------------|
| `community_pass_products` | 20 rows, `(product_id, length, duration_days, price_usd, label)`; ids `audioura.pass.usd5.month` | **34 rows** = the LOCAL-686 ladder prices, `(product_id, price_usd, label)`; ids `audioura.pass.usd<N>`; **no length column** |
| `community_passes` (owner's options) | `(community, product)`, unique `(community, product)` | adds **`length` + `duration_days`**, unique **`(community, product, length)`** |
| `/purchases/verify` (pass) | body `{community_id}`; expiry from the product's duration | body `{community_id, length}`; server checks `(community, product, length)` is offered, expiry = now + the **option's** `duration_days` |
| App pass product ids | 20 `audioura.pass.usdN.length` | the **34** `audioura.pass.usd<N>` (`kPassStoreIds`); `buy/testPurchaseCommunityPass(..., length)` |
| `Audioura.storekit` | `nonRenewingSubscriptions: []` | **34** non-renewing subscription products `audioura.pass.usd<N>` |
| Create form | 5 hard-coded `price.length` checkboxes | price **quick-picks ($2/$3/$5/$10/$20/$50) + Custom (snaps to the nearest ladder dollar) + four length checkboxes**; `pass_products` body is `[{product_id, length}]` |

The page still shows **"$5 / month"**: the catalogue label is the price only (`$5`), and the server
composes `price_label / length` from the option (`pass_label_for`). Durations are the same
calendar-free arithmetic (day=1, week=7, month=30, year=365).

## Rulings → where they live (690C delta)
- *One product per PRICE, length per community* → migration 029 §2 (34 price-only products) + §3
  (`community_passes.length/duration_days`, unique `(community, product, length)`);
  `communities_api._offered_option()` and `verify_community_pass(..., length)`.
- *Prices come from the full ladder (LOCAL-686)* → the 34 `audioura.pass.usd<N>` match
  `price_tiers` tiers 8..41; the create form snaps a custom price with `snapDollarsToLadder`
  (mirrors `TourPricingService.snapToLadder` / `price_tiers.snap_to_ladder`).
- *Request carries community_id + length; buying again extends* → `/purchases/verify` passes
  `length` through; `_upsert_membership` is one row per `(user, community)` with a fresh expiry.

## Reminders — the daily tick for LEAD (unchanged endpoint)
`POST /communities/reminders/run` still runs the 3-days-before + at-expiry buckets (idempotent per
period). To fire it once a day, add a tick that calls it — e.g. a cron/launchd entry hitting the
user-api, or a one-liner on the host:

```
# once a day (example: 09:00). Point at the user-api base URL + API key in prod.
0 9 * * *  curl -fsS -X POST "$USER_API_BASE/communities/reminders/run" -H "X-API-Key: $GATEWAY_API_KEY"
```

(Not wired into `.continuous_dev/*` — that is LEAD's call, per the ticket.) The app shows due
reminders from `/communities/mine` as the in-app "expires in N days — Renew" banner.

## Tests (690C)
- **Server: 27 pass** (was 24) on `audiotours_test`. New/updated:
  - `test_one_price_product_two_communities_two_lengths` — the SAME `audioura.pass.usd5` buys a
    **1-day** pass in community A and a **1-month** pass in community B: two memberships, expiries
    ≈ now+1d and now+30d.
  - `test_catalogue_has_34_price_products_no_length` — catalogue is the 34 ladder prices with
    **no** `length`/`duration_days` column; those live on `community_passes`.
  - `test_pass_not_offered_refused` — a different product **and** the right product with a length
    the community did not offer both → 400 `pass_not_offered`.
  - `test_duration_days_for_length_and_label`, updated `test_is_community_pass_product`
    (`audioura.pass.usd5` is a pass), and every pass purchase now carries `length`.
- **Dart: 14 pass** (was 11). New `community pass product ids` group: `kPassStoreIds`/`kPassLadderDollars`
  are 34 ids with no length suffix; `passProductForDollars(5) == 'audioura.pass.usd5'`; four lengths.
  `Community.fromJson` pass payload updated to the new product shape.

## Live row counts — isolated DB `audiotours_local690` (own container `development-postgres-2-1`, host 5433)
`run_local690_live.py` (updated to the new shape) ran the full flow. The $5 product bought a
**month** in the paid community and a **day** in a second community (one product, two lengths):

| table | rows |
|-------|------|
| communities | 3 |
| community_pass_products | **34** |
| community_passes | 3 |
| community_memberships | 3 |
| community_episodes | 3 |
| community_reports | 1 |
| purchases | 2 |

Live output confirmed `passes offered: [('audioura.pass.usd5','day','$5 / day'),
('audioura.pass.usd5','month','$5 / month')]`, `buy pass ($5/month) duration_days 30`, and
`buy pass ($5/day, 2nd community, SAME product) duration_days 1`.

Migration 029 was dropped+re-applied on both `audiotours_test` and `audiotours_local690` (isolated
DBs I own); `INSERT 0 34` on apply; the shared `audiotours` DB was never touched; no `-p audioura`,
no `audioura-*` container renamed.

## Commits (690C, per step)
- `b3fa2ed0` — migration 029 rewritten + server (one product per price; length on the option;
  `verify_community_pass(..., length)`; `_offered_option`; create attaches `{product_id, length}`).
- `5a9efa38` — app (34 `audioura.pass.usd<N>` ids; buy/testPurchase take length; 34 storekit
  non-renewing subscriptions; create form price-ladder + length picker; build 49→50).
- `73c1161e` — tests (server to new shape + 3 new 690C tests = 27 pass; Dart pass payload + iap
  pass-id group = 14 pass).

## Honest status (690C)
- **Proven:** 27 server tests + 14 Dart tests pass; the full live flow on the isolated DB with the
  34-price catalogue and the one-product-two-lengths-two-communities case; migration applies with
  `INSERT 0 34`; `flutter analyze` clean on the changed files.
- **Not exercised live:** the real Apple/Google pass products still do not exist, so the pass
  purchase was proven through the `stub` path; the `apple` JWS branch reuses the existing verifier
  (now also sending `length`). The storekit entries and the create-form UI were verified by analyze
  + unit tests, not an on-device run.
- **Out of scope (by ticket):** owner payouts, tax forms, statements.
