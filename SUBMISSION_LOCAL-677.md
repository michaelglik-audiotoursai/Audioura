# SUBMISSION — LOCAL-677: Curator paid tours

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-677-paid-tours` (from `subscribed` @ `cf002b5b`)
**Build:** 2.4.8+38 → **2.4.8+39**

## Why
Michael (2026-10-13): "I expect the mobile App now has Reviews, Curator's paid
tours abilities, and filters for such tours." Reviews/ratings shipped (2.4.8+38),
but **paid tours did not exist** — `map_delivery/app.py::_is_paid_select` read
`audio_tours.is_paid` only *if the column existed*, so every tour was free.

This ships the for-sale flag, the price tiers, the free Stop-1 preview, the Buy
flow (store stub until Apple/Google are live), the Free/Paid filter, and the
curator Price control + Sales count. Design of record: `CURATOR_MARKETPLACE.md`
(D624); tiers/preview/payout split are **config** using LEAD's D652 defaults
(Michael has not confirmed the numbers). **Payouts/Stripe are out of scope** (a
later task, D624 §4).

## What shipped

### 1. DB — additive, declared (`migration/sql/022_tour_price_tiers.sql`)
- `audio_tours.price_tier SMALLINT NULL` — 1..5 (a row in `price_tiers`), NULL =
  free. Every existing tour stays free.
- `audio_tours.is_paid BOOLEAN GENERATED ALWAYS AS (price_tier IS NOT NULL)
  STORED` — the database keeps the for-sale flag in lock-step with the tier; it
  can never drift and needs no trigger. `map_delivery` already reads this column.
- `tour_unlocks(user_id, tour_id, transaction_id, store, price_usd, created_at,
  UNIQUE(user_id, tour_id))` — one row per (buyer, tour). The UNIQUE makes a
  replayed purchase a no-op (idempotent unlock). `tour_id` is an ORIGINAL id, so
  **a translation shares its source's unlock**.
- `price_tiers` config table (tier, product_id, price_usd, label), seeded with
  the D652 defaults ($1.99/$2.99/$4.99/$7.99/$9.99 → `audioura.tour.tier1..5`).
  **Every number is a row** — Michael changes a price with one `UPDATE`, no
  redeploy. `price_tiers.py` is the DB-authoritative reader with a code fallback.

### 2. Curator price endpoint (`tour_pricing_service.py`, on the orchestrator)
- `POST /tour/<id>/price {user_id, tier}` — a **Curator** (a level with
  `plans.can_sell = TRUE`, data not a hard-coded level name) sets or clears
  (`tier: null`) the tier on **their own** tour. A non-curator → `403 not_curator`;
  a curator who does not own the tour → `403 not_owner`; a bad tier →
  `400 invalid_tier`. Ownership reuses `tour_reviews_service.resolve_tour_creator`,
  so pricing and reviews agree on who owns a tour. The tier is written on the
  ORIGINAL tour (a translation inherits it).
- Also `GET /tour/<id>/price`, `GET /tour/<id>/unlock-state?user_id=` (the
  preview/lock gate — Stop 1 free), `GET /tour/<id>/sales` (unlock count),
  `GET /price-tiers` (the config for the app's picker).

### 3. Server: unlock + preview + verified + Free/Paid filter
- **`map_delivery/app.py`** — `?price=free|paid` on `/tours-near` and
  `/search-tours`; every tour payload now carries `price_tier` + `price_label`
  ("$4.99"/"Free"). `is_paid` and `price_tier` **inherit from the source** for a
  translation (`COALESCE(orig.*, t.*)` over the existing self-join).
- **`user-tracking/entitlements_api.py`** — `/purchases/verify` recognises
  `audioura.tour.tierN` products and takes a tour path: verify (stub accepts any
  non-empty txn), record the purchase, and write `tour_unlocks` idempotently; a
  replayed transaction is `409` but still ensures the unlock. Requires `tour_id`.
  **A tour purchase does not change the buyer's level.** Until the Apple/Google
  products exist, `IAP_VERIFY_MODE=stub` on the local stack completes a fake
  purchase so the flow is testable end to end on Michael's phone.
- **`tour_reviews_service.compute_verified`** now reads `tour_unlocks` FIRST (the
  authoritative per-tour unlock) and short-circuits to verified — so after an
  unlock the buyer's ratings/reviews are **"Verified listener"** (LOCAL-672 read
  purchases; it now reads `tour_unlocks`). The historical product-string + level
  fallback remains for pre-677 purchases.

### 4. App — listener side
- **Price badge** ("$4.99"/"Free") next to the ★ rating in the tour dialog and
  in the list rows (`widgets/price_badge.dart`).
- **Free / Paid / Any** home filter beside the rating filter, remembered per
  device, passed to `/tours-near` as `?price=free|paid` (`screens/home_screen.dart`).
- **Preview lock + Buy**: a locked paid tour shows a "Stop 1 is a free preview —
  Buy for $X" banner over the player (`screens/tour_player_screen.dart`); the Buy
  / **TEST PURCHASE** sheet (`widgets/tour_buy_sheet.dart`) completes the purchase.
- **IAP** (`services/iap_service.dart`): tour-tier products
  `audioura.tour.tier1..5`; `buyTour(tier, tourId)` (real StoreKit, sends
  `tour_id` to `/purchases/verify`) and `testPurchaseTour(tier, tourId)` (LOCAL
  stub mode — a clearly-labelled "TEST PURCHASE" that posts `store='stub'`).
- `services/tour_pricing_service.dart` — the app client for the pricing/unlock
  endpoints.

### 5. App — curator side (`screens/my_tours_screen.dart`)
- A **Price** control in each own tour's ⋮ menu (tier picker + Free), shown only
  to a Curator, for a sellable (numeric, non-translation) tour. The server still
  enforces ownership; a `403` surfaces as a clear message.
- A **"Price: $X · Sales: N"** line per sellable tour (unlock count). No money
  totals (payouts are a later task).

## Files
- Server: `migration/sql/022_tour_price_tiers.sql`, `price_tiers.py` (new),
  `tour_pricing_service.py` (new), `tour_orchestrator_service.py` (register),
  `map_delivery/app.py`, `user-tracking/entitlements_api.py`,
  `tour_reviews_service.py`.
- App: `lib/services/iap_service.dart`, `lib/services/tour_pricing_service.dart`
  (new), `lib/widgets/price_badge.dart` (new), `lib/widgets/tour_buy_sheet.dart`
  (new), `lib/screens/home_screen.dart`, `lib/screens/tour_player_screen.dart`,
  `lib/screens/my_tours_screen.dart`, `pubspec.yaml` (build bump).
- Tests: `tests/test_local677_paid_tours.py` (new).

## Tests & verification
- **`tests/test_local677_paid_tours.py` — 13 tests, all pass.** Covers the
  curator-only price (non-curator/non-owner/invalid-tier refusals), translation
  inheritance (price AND unlock), the preview lock+unlock (Stop 1 free; a free
  tour is never locked), the stub purchase writing an unlock **idempotently**
  (replay → 409, one row, level unchanged), the Free/Paid filter end to end, and
  **verified-after-unlock**. All rows use `TEST-677-` ids, deleted only by exact
  id after a prefix check.
- **Regression:** LOCAL-670 + LOCAL-672 suites (41 tests) still green after the
  `compute_verified` and `map_delivery` changes.
- **`flutter analyze`** (whole app): 77 errors, **all pre-existing** (62
  `audio_handler.dart`, 10 `map_page.dart`, 3 `tour_service.dart`, 2
  `subscription_management_screen.dart`) — **zero** in any LOCAL-677 file.
- **`flutter build ios --no-codesign`** succeeded (`Runner.app`, 37.6 MB).

## Notes / constraints honoured
- Additive migration only (no DROP/DELETE; `is_paid` generated, `price_tier`
  nullable). Self-healing: `price_tiers.py` and the map-delivery/entitlements
  mirrors fall back to the D652 constants on a DB that predates migration 022.
- No paid API calls. No payouts/Stripe. No GCloud. Own containers only.
- Build bumped after 2.4.8+38 → 2.4.8+39.


---

# 677B — Bounce: the lock never engaged on the phone

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-677-paid-tours` (continued; rebased on `subscribed` @ `d0caeacb`)
**Build:** 2.4.8+39 → **2.4.8+40**

## The report (Michael's iPhone, app 2.4.8+39, 2026-10-13 18:46–18:50)
Tour `q9oSUebU` (server tour 557, `price_tier=3`, is_test) showed the right
dialog — ★ 7.5 · New, **$4.99**, v12 · updated Oct 11, Original: English — but
after **Download Tour** the player **played ALL 5 stops**: no free-preview
banner, no Buy, no TEST PURCHASE. The orchestrator logged **no
`GET /tour/557/unlock-state` at all**.

## Root cause (two bugs)
1. **The player never asked.** A downloaded tour was opened by its local path and
   its stored `tour_id` was the **editable** id (non-numeric). `tour_player_screen`
   did `if (int.tryParse(tourId) == null) return;` before asking, so
   `unlockState` was never called and fell back to "free".
2. **The lock was only a banner.** Even when a lock state was present, nothing
   stopped playback — the WebView auto-played every stop. So the lock could not
   engage regardless of (1).

## What shipped (steps map to the ticket)

1. **Carry the server id + price + unlock into the local record** (step 1).
   `NEW services/downloaded_tour_meta.dart` — `DownloadedTourMeta` (snapshot
   model) + `DownloadedTourStore` (read/merge/mark-unlocked on `saved_tours`).
   `home_screen._stampPaidSnapshot` stamps `server_tour_id` (the NUMERIC id the
   pricing endpoints key on), `price_tier`, `is_paid` (grandfather snapshot),
   `unlocked`, `price_label`, `original_language` at download. My Tours passes
   `serverTourId` + `originalLanguage` to the player; every other entry path
   (share code, voice next/prev) recovers them from the local record **by path**,
   so the player always resolves the id and asks `/tour/<id>/unlock-state`.

2. **Offline-correct lock** (step 2, D647 add. 2). `_loadUnlockState` asks the
   server when a numeric id resolves; offline / no answer it gates from the local
   snapshot (`_offlineState`): a tour stored **paid & not-unlocked** stays
   preview-only; a tour stored **free** stays free. **Fail closed only for a tour
   stored paid.** A confirmed purchase writes `unlocked:true` to the local record
   at once (`markUnlockedForPath`) so the lock lifts offline, and syncs as today.
   **Also fixed bug 2:** `_applyLockToWebView` injects a JS guard that
   pauses+rewinds any stop `>= free_preview_stops` while locked (installed on the
   real audio elements in `onLoadStop`, re-applied after a purchase).

3. **Grandfathering** (step 3). `is_paid` is a snapshot **at download time**, so a
   tour downloaded while free stays playable after the curator later prices it; a
   **re-download** after pricing stamps it paid and then locks (Michael's test).

4. **Listen/player header** (step 4). `_buildOriginalHeader` shows
   "Original: &lt;Language&gt; · vN" above the player, like the dialog.

5. **Hide "Distance: null km"** (step 5). `utils/tour_display.shouldShowDistance`
   — the found-tour dialog renders the Distance line only when `distance_km` is
   non-null (share-code and search entries carry none).

7. **Download only the selected languages** (D653). If English is deselected the
   phone does **not** pull the English tour (`TourTranslationHelper
   .shouldDownloadEnglish`); the server may still use English as an internal
   template, the listener just does not receive it. The "English will be generated
   as template" note and the `showEnglishNote` flag were removed from the shared
   `LanguageSelector` (all call sites updated).

8. **Every language copy carries the price, unlocks separately** (D653). Reverses
   LOCAL-677's "translation inherits unlock". A translation still **inherits** its
   source's **price** (`get_price` resolves to original), but `tour_unlocks` is now
   keyed on the **language row's own `tour_id`**: buying Russian unlocks Russian
   only; English needs its own purchase (2 × $4.99 = $9.98). `record_unlock` /
   `is_unlocked` / `preview_state` key on the own id; `_verify_tour_purchase`
   writes the unlock on the purchased language's own id; `sales_count` **pools**
   across the family for the curator's view; `compute_verified` pools across the
   family so the **Verified-listener** mark comes from an unlock of **any** language
   (reviews/ratings pool, D647). Each saved translation record carries the inherited
   price snapshot keyed by its own server id, `unlocked:false` for a paid copy.

## Verification
- **Flutter tests (new, 22, all green):**
  `test/downloaded_tour_meta_test.dart` — server-id resolution incl. **per entry
  path** (listen list / share code / voice nav all resolve the id so unlock-state
  is requested); offline lock (fail-closed-for-paid, free-stays-free);
  grandfathering (free stays free, re-download paid locks, pre-677B record free);
  store read/merge/mark-unlocked lifts the lock at once; per-language price
  snapshot. `test/paid_tour_download_test.dart` — null-distance hidden;
  selected-languages-only (English deselected is not pulled).
- **Server tests:** `tests/test_local677_paid_tours.py` — **16 passed** (was 13):
  translation inherits price **but unlocks separately**; each language unlocks
  independently + sales pool; verified pools across languages; `/purchases/verify`
  of a translation unlocks only that language. Regression:
  `test_local672_verified_reviews.py` (26) still green → **42 passed**.
- **`flutter analyze`** (whole app): **77 errors, all pre-existing**, **zero** in
  any file 677B touched (unchanged from 677).
- **`flutter build ios --no-codesign`** succeeded (`Runner.app`, 37.6 MB).
- No paid API calls. No install (LEAD does). Build bumped 2.4.8+39 → **2.4.8+40**.
