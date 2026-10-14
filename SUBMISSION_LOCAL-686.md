# SUBMISSION — LOCAL-686: Tour price ladder $2–$200 (5 quick picks + Custom snap-to-nearest)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-686-price-ladder` (from `subscribed` = 1512dddc)
**Status:** Proven on the dev DB (migration applied + idempotent, stub purchase of `audioura.tour.usd35` unlocks a tour, legacy tier still 402s). All automated tests green.

---

## Why
Michael (2026-10-14): guides pick their own price. Apple/Google sell only pre-created products at fixed prices, so Audioura ships a **fine ladder of consumable products** and the guide's typed price **snaps to the nearest step** — "Typing $37 gives 'Your price: $35'". Before this, there were 7 fixed `.99` tiers; now there is a 34-step round-dollar ladder plus 5 quick picks and a Free option.

## The ladder — 34 round-dollar steps, tiers 8..41
| Range | Step | Count | Tiers |
|-------|------|-------|-------|
| $2 – $20 | $1 | 19 | 8–26 |
| $25 – $50 | $5 | 6 | 27–32 |
| $60 – $100 | $10 | 5 | 33–37 |
| $125 – $200 | $25 | 4 | 38–41 |

Product ids `audioura.tour.usd<N>` (consumable, e.g. `audioura.tour.usd35` = $35 = tier 29). Labels are the integer dollar amount (`"$35"`).

The seven legacy `.99` tiers (1–7, migrations 022/024) stay **ACTIVE** so tours already priced with them keep their price (e.g. a tier-3 tour still shows `$4.99` and still gates). A new column **`price_tiers.in_picker BOOLEAN DEFAULT TRUE`** marks what the guide's picker offers: `TRUE` for the 34 ladder tiers, `FALSE` for the 7 legacy tiers.

## Snapping rule (verified identically in Python and Dart)
Nearest ladder step; **ties round DOWN**; below $2 → $2; above $200 → $200.
`37→35, 1→2, 2.4→2, 2.5→2, 22→20, 23→25, 199→200, 250→200, 112.5→100, 113→125` — all pass.

---

## What changed (commit per step)

| Step | File(s) | Change |
|------|---------|--------|
| 1 | `migration/sql/026_price_ladder.sql` | 34 ladder rows (tiers 8..41); widen both tier CHECKs 1..7 → 1..41; add `price_tiers.in_picker` (FALSE for 1–7, TRUE for ladder). Additive + idempotent (`ADD COLUMN IF NOT EXISTS`, `ON CONFLICT DO UPDATE`). |
| 2–3 | `price_tiers.py`, `tests/test_local686_price_ladder.py` | `DEFAULT_PRICE_TIERS` now 1..41 each with `in_picker`; `load_price_tiers` reads `in_picker` (self-healing fallback for a DB that predates the column); new `picker_tiers()`, `ladder_prices()`, `snap_to_ladder()`, `snap_label()`, `LADDER_MIN/MAX_USD`. 7 unit tests. |
| 4 | `map_delivery/app.py`, `user-tracking/entitlements_api.py` | `_DEFAULT_TIER_LABELS` and `TOUR_TIER_PRODUCTS` mirrors extended to all 41 tiers (7 legacy + 34 ladder). |
| 5 | `tour_pricing_service.py`, `.../services/tour_pricing_service.dart` | `/price-tiers` now returns `in_picker` per row; Dart `PriceTier.inPicker`, `pickerLadder()` (ladder-only), `snapToLadder()` client helper. |
| 6 | `.../screens/my_tours_screen.dart`, `.../test/price_ladder_snap_test.dart` | Rebuilt the guide's price control: **Free + quick-pick chips ($3/$5/$10/$20/$50)** and a **Custom field "Your price ($2–$200)"** that shows **"Your price: $X"** = nearest ladder step on every keystroke. Save stores that step's tier. 13 Dart tests. |
| 7 | `.../services/iap_service.dart`, `.../ios/Audioura.storekit` | `kTierProductIds` map (single Dart source of truth), `kTourStoreIds` derived from it, `tourProductForTier` tier-mapped (legacy `tier<N>`, ladder `usd<N>`); StoreKit config gains the 34 ladder consumables (43 products total). |
| 8 | `tests/test_local677_paid_tours.py` | Tier-range assertions updated to 1..41 (tiers 1–7 still valid; 8 and 41 valid, 42 invalid; `usd35`=tier 29). |
| 9 | `audio_tour_app/pubspec.yaml` | Build bump `2.4.14+47` → `2.4.14+48`. |

**Single source of truth:** the three product-id mirrors (Dart `kTierProductIds`, Python `TOUR_TIER_PRODUCTS`, `Audioura.storekit`) were cross-checked programmatically — **all three carry the identical 41 ids**.

---

## Verification evidence

**Python unit tests** — `tests/test_local686_price_ladder.py`: 7 passed. Snapping and config asserted against the exact ticket cases.

**Dart tests** — `test/price_ladder_snap_test.dart`: 13 passed (ladder shape + all 10 snap cases + edge cases).

**`flutter analyze`** on changed files: `iap_service.dart`, `tour_pricing_service.dart`, `price_ladder_snap_test.dart` → **No issues found.** `my_tours_screen.dart` → **0 errors** (82 pre-existing `info`/`warning` lints, unchanged baseline, none in the edited region).

**Live DB test (dev DB `audiotours` on `development-postgres-2-1`, host port 5433 — NOT an `audioura-*` container; no container restarted/renamed):**

Migration 026 applied **twice** (idempotency), counts reported before/after:

| | price_tiers | audio_tours | in_picker TRUE / FALSE |
|--|--|--|--|
| before | 7 | 475 | (column absent) |
| after run 1 | 41 | 475 | 34 / 7 |
| after run 2 | 41 | 475 | 34 / 7 |

`audio_tours` unchanged (475, purely additive). CHECKs confirmed widened to `1..41` on both `price_tiers` and `audio_tours`. Legacy tier 3 preserved (`$4.99`, `in_picker=FALSE`); `usd35`=tier 29 (`$35`, `in_picker=TRUE`).

**End-to-end on the test DB (`audiotours_test`, migrations 024+026 applied):**
- Full `test_local677_paid_tours.py` + `test_local686_price_ladder.py` → **31 passed**.
- A `TEST-686-` `is_test` tour priced `usd35` (tier 29): price label `$35`, product `audioura.tour.usd35`; **locked before** → stub `/purchases/verify` of `audioura.tour.usd35` returns `verified+unlocked`, `amount=35.0` → **not locked after**.
- A `TEST-686-` tour priced tier 3: still `$4.99`, still `is_paid`, still **locked (402)** for a stranger.
- All `TEST-686-` rows cleaned up afterward (0 leftovers in both DBs); only `is_test` tours were created, never a real tour, no `DELETE` from real `audio_tours` rows.

---

## Safety notes
- Branch created from `subscribed` HEAD (1512dddc); `git merge-base --is-ancestor 1512dddc HEAD` exits 0.
- No `audioura-*` container was started, stopped, or renamed; no `docker compose -p audioura …`. The migration was applied to the dev DB directly over psycopg2 (additive, idempotent) — the running services self-heal to the same schema.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or `.continuous_dev/STATUS.md`.

## Open / handing-to-LEAD
- Quick-pick set ($3/$5/$10/$20/$50) is LEAD's recommendation, marked **D-pending** in the ticket — wired as specified; trivially changeable (a `const quickPickUsd` list in `my_tours_screen.dart`).
- The 34 Apple/Google store products (`audioura.tour.usd<N>`) must be created in App Store Connect / Play Console before a real (non-stub) purchase can complete; the StoreKit config file is updated for Sandbox/local testing today.
