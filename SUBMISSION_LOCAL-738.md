# SUBMISSION — LOCAL-738

**Community create form — one price per length, only store prices, real error
messages, release cadence, Generate → Create direct.**

Agent: Mac Mini Kiro · Branch: `LOCAL-738-community-create-form` · Base:
`subscribed` @ `98cc6dc6`

`git merge-base --is-ancestor 98cc6dc6 HEAD` → exit 0 (correct base).

---

## Why (Michael's review 2026-10-22: C-entry, C2, C2b, C2c, C2d, C4b)

Every "Create community" failed on Michael's iPhone: the app sent
`pass_products: [{usd10, year}, {usd15, year}]`; the server refuses any product
outside `APPLE_LIVE_PASS_PRODUCTS` ($1/5/10/20) with 400
`pass_product_not_available`, and the app showed a generic
"The name may be taken, or you may need a plan". The form also crossed ONE price
set with every ticked length ("$15/month AND $15/year"), and a typed Custom
price stuck in `_selectedDollars` so changing the chips didn't change what was
sent.

## What changed

### Server — `user-tracking/communities_api.py`
1. **`GET /communities/pass-prices`** — the allowed pass PRICES for a new
   community, in price order, built from the single `APPLE_LIVE_PASS_PRODUCTS`
   set crossed with the catalogue (price + label). One source of truth; the app
   has no second copy.
2. **`release_cadence`** — `create_community` accepts and validates it
   (day|week|month|year, default `week`, else 400 `bad_release_cadence`),
   stores it, and `_community_row` / `_community_page` return it.

### Migration — `migration/sql/048_community_release_cadence.sql`
Additive, idempotent: `ADD COLUMN IF NOT EXISTS communities.release_cadence
VARCHAR(10) NOT NULL DEFAULT 'week'` + a guarded CHECK on the four lengths. No
DROP, no DELETE, no retype. Applying twice is a no-op; every existing community
reads back `week`. **Next free number was 048.** **LEAD applies 048 to the live
subscribed DB.**

### App
- `communities_service.dart` — `CommunitiesService.createResult(body)` returns
  the server's real `error` + `message` on failure (a transport failure gets a
  short connection note); `create()` kept as a thin wrapper. New `passPrices()`
  fetch.
- `communities_models.dart` — new `PassPrice`, `CreateResult`, and the pure
  Flutter-free `CommunityPassForm` (one-price-per-length payload + validity, the
  off-list guard); `Community.releaseCadence`; `CommunityCopy.releaseCadenceLabel`.
- `communities_about_screen.dart` — the create form rewritten:
  - **One price per length** (C2/C2d): tick a length, pick ONE price for it;
    exactly one `{product_id, length}` per ticked length; at least one on.
  - **Only store prices** (C2b): price chips come from the server; **Custom
    price removed**; what is shown selected is exactly what is sent (stale-
    selection bug gone). Falls back to $1/5/10/20 only if the call fails.
  - **Real errors** (C2): the form shows `result.message` (e.g. "That community
    name is taken.") — never the old generic guess.
  - **Release cadence** (C2c): required single-select, default `week`.
  - **Location without typing** (C4b): "Use my location" (device GPS via
    `geolocator`) fills the coordinates; manual entry stays as a fallback.
- `tour_generator_screen.dart` — Generate → **Community opens
  `CreateCommunityScreen` directly** (C-entry), not the About page.
- `community_page_screen.dart` — shows **"New tours: weekly"** from
  `release_cadence`.

---

## code_sha

The create commit on `LOCAL-738-community-create-form` (recorded in the PR /
branch head). Base: `98cc6dc6`.

## Migration

`migration/sql/048_community_release_cadence.sql` — additive, idempotent.
Applied to `audiotours_test` (pytest) and to the throwaway `local738` DB for the
live test. **LEAD applies it to the live subscribed DB.**

---

## Tests

### Dart unit — `test/communities_create_form_local738_test.dart` (13 tests, all pass)
- month@$5 + year@$20 → exactly `[{usd5,month},{usd20,year}]` (no cross-product).
- a ticked length with no price is skipped; no length on → empty payload.
- **changing a chip changes the payload** (stale-selection bug).
- **RED TEST**: an off-list `$15` price is dropped from the payload AND cannot
  make the form valid — this test FAILS if an off-list price slips through.
- `releaseCadenceLabel` ("New tours: weekly" …); `PassPrice` /
  `Community.release_cadence` parsing (defaults to `week`); `CreateResult`.

### Dart widget — `test/communities_create_form_widget_local738_test.dart` (2 tests, all pass)
Drives the REAL `CreateCommunityScreen` with a `MockClient` (plan l2, server
pass prices, name free, failing create):
- the form renders on a plan with the server price chips ($5/$20) + the default
  "Weekly" cadence chip, and NO "Custom price" field.
- **a failing create shows the server's exact message** ("That community name is
  taken.") and never "may need a plan".

### pytest (audiotours_test) — `tests/test_local738_create_form.py` (7 tests, all pass)
- `/communities/pass-prices` set == `APPLE_LIVE_PASS_PRODUCTS`, ascending order,
  excludes off-list ($15).
- create defaults `release_cadence` to `week`; stores a chosen cadence (returned
  on the page); rejects a bad cadence (400); refuses an off-list $15 price (400
  `pass_product_not_available`).

### No regression
- `test_local700_communities_ux.py` — 14 pass.
- `flutter analyze` on the touched files: **no new issues**. The only reported
  items are 2 pre-existing `Radio` deprecations in
  `community_page_screen.dart:1185-1186` (the report-reason radios, not my code).
- Baseline Flutter failures unchanged: `storied_compat_screens_404` "Your plan"
  still fails pre-existing (`plan_screen.dart` untouched).

---

## Live test (own container, spare ports, simulator-grade API drive)

Stack `docker-compose.local738.yml` — project `local738`, spare ports
(`54803` user-api, `54832` postgres), a **throwaway** `postgres-738` (tmpfs),
build context this worktree. **Never** `-p audioura` / the shared `postgres-2` /
Michael's phone. Budget: **$0** (no generation, no AI).

Full schema loaded into the throwaway DB (schema_dump + migrations 001–048,
50/52 applied; the 2 non-applied are idempotent re-asserts and one psql-meta
file not needed for the community path). Shared `audioura` stack (14 containers)
left untouched; `down -v` removed the throwaway DB.

Drove the exact payload the rewritten form sends:

| Step | Result |
|---|---|
| `GET /communities/pass-prices` | `[$1, $5, $10, $20]` only, in order (catalogue has 35 rows incl. $15 — filtered out) |
| `POST /communities` (month@$5, year@$20, cadence=week) | **201**; passes `$5 / month`, `$20 / year`; `release_cadence: week`; join_code issued |
| `GET /communities/<id>` | **200**; `release_cadence: week`; both passes present |
| RED: off-list `$15` | **400** `pass_product_not_available` — "…Choose $1, $5, $10 or $20." |
| bad cadence `fortnight` | **400** `bad_release_cadence` |

### Row counts (throwaway `postgres-738`)
| table | before | after |
|---|---|---|
| communities | 0 | 1 |
| community_passes | 0 | **2** (one per ticked length — no cross-product) |
| community_memberships | 0 | 0 |

No deletes; no purchase-bearing rows touched (D690); no `DELETE FROM
audio_tours`.

### Simulator screenshots
Not captured: this agent runs headless and cannot drive the iOS simulator UI /
capture a Flutter app screenshot. The create-form UI is covered instead by the
widget tests above (real `CreateCommunityScreen`, server price chips, cadence
chip, no Custom price, the real-error SnackBar), and the server behaviour by the
live API drive against an own container. The GPS "Use my location" button uses
the existing `geolocator` permission/`getCurrentPosition` pattern from
`navigation_service.dart` and can only be exercised on a device/simulator.

---

## Cost

≈ **$0.00** — no generation, no AI, no store calls (stub IAP). Well under the
$0.10 budget.
