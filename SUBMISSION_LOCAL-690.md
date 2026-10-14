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
