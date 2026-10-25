# SUBMISSION — LOCAL-762

**Listen ⋮ menu: owner-only Price/Re-score, a role line, price at creation, and
the Share spinner that never closed.**

- **Branch:** `LOCAL-762-listen-menu-roles`
- **Base:** `subscribed` @ `bc5577d7` (verified `git merge-base --is-ancestor bc5577d7 HEAD` → exit 0)
- **code_sha:** `e3acea7f3d91b1b7ccaf43d16add285ed9f67cfb`
- **Ruling:** D711 (§1 menu, §2 role line, §3 members-only pricing, §4 price at creation)
- **Agent:** Mac Mini Kiro
- **Budget:** $0.00 (no OpenAI / no AI calls anywhere in build or live test)

> Note on D711: the ruling is referenced by the task but is not yet present in
> `DECISIONS.md` (that file currently ends at D611). I implemented strictly to
> the inline §1–§4 specification in the task. I did not edit `DECISIONS.md`.

---

## Why (Michael's retest, 2026-10-25)

- A member (Pixel-4, not an organiser) could reach **Set Price**; the organiser
  (iPhone) got *"you can only set a price for the tours you created"* **on his
  own tour** — confusing. Root cause: the organiser-audio publish never stored
  `creator_user_id`, so the server could not resolve him as the creator, and the
  app showed Price/Re-score to everyone regardless of ownership.
- **Request re-score** was offered to users who could never use it.
- **Share** returned a code but *"Creating share code"* spun forever — a
  LOCAL-761 regression (tab Navigators).
- Michael asked for a **line defining what the tour is** ("Owner's tour",
  "Community tour", "you are the organiser").

---

## 1. The Share spinner (LOCAL-761 regression) — fixed + whole-app audit

`showDialog`/`showModalBottomSheet` default to `useRootNavigator: true`, so the
progress dialog is pushed on the **root** navigator. After LOCAL-761 put each
bottom-nav tab inside its **own** nested `Navigator`, dismissing with a plain
`Navigator.of(context).pop()` / `Navigator.pop(context)` from a screen now
*inside a tab* popped the **tab's** navigator instead — the dialog stayed up
forever and a tab route was popped out from under the user. Fix:
`Navigator.of(context, rootNavigator: true).pop()`.

### Dialog-pop sites changed (whole-app audit)

| File | Sites |
|---|---|
| `widgets/share_tour_sheet.dart` | the `shareTour` "Creating share code…" progress dialog (1) |
| `screens/home_screen.dart` | bulk-download progress; single-download success + catch; `membership_required` dismiss; 4 translation-block dismisses; "Getting encryption key…"; newsletter-URL success + catch; "Loading newsletter articles…" success + catch; "Downloading N articles…" success + catch; buy-then-download dialog (11) |
| `screens/my_tours_screen.dart` | translation progress; 2× speech "Listening…" `onResult` dismiss (3) |
| `screens/subscription_management_screen.dart` | cleanup success + catch; clear-all-data success + catch (4) |
| `screens/edit_stop_screen.dart` | "Processing audio file…" success + catch (2) |

**Total: 21 sites across 5 files.**

**Audited and left unchanged (verified SAFE)** — these pop from inside the
dialog/sheet's **own builder callback** (the context is a descendant of the
dialog route, so it already targets the root navigator): the share result sheet;
`home_screen._buildDownloadActions` (a `StatefulBuilder` context); and every
`onPressed: () => Navigator.of(ctx).pop()` / `actions:` OK/Cancel button across
`rate_tour_dialog.dart`, `subscription_credential_dialog.dart`,
`tour_buy_sheet.dart`, `reviews_section.dart`, `renewal_sheet.dart`,
`why_this_score_sheet.dart`, `map_page.dart`, and the generator/community/news
screens.

**Red test:** `test/share_spinner_nested_navigator_local762_test.dart` — inside a
nested tab `Navigator`, the root-pushed progress dialog **closes** and the tab
route underneath is **not** popped; the buggy nested-navigator pop is reproduced
(dialog stays up); and the real `shareTour` dismisses its own "Creating share
code…" dialog (3 tests, all green).

---

## 2. Ownership is known per tour

- **`user-tracking/communities_api.py`** — the organiser-audio NEW publish INSERT
  now stamps `creator_user_id = user_id` (the organiser). Without it,
  `audio_tours.creator_user_id` stayed NULL and ownership could never be
  resolved for an organiser-audio tour (there is no `tour_requests` row to fall
  back on), which is exactly why the organiser was refused on his own tour and
  the LEAD had to backfill tour 750 by hand.
- **New endpoint:** `GET /tour/<id>/role?user_id=` (added in
  `tour_pricing_service.register_pricing_routes`, auto-mounted on the
  orchestrator). Returns `is_owner`, `is_curator`, `source_kind`, `is_broadcast`
  (`source_kind == 'organiser_audio'`), `community_id`, `community_name`,
  `community_visibility`, `is_community`, `is_organiser`. Fails closed to the
  least-privileged reading. Chosen over extending `/tour-info` so the role lives
  next to the pricing logic that already resolves creator + curator.
- The app caches these on the Listen record (`TourRole.toRecordJson`) and
  **refreshes them on ⋮-menu open** (`PopupMenuButton.onOpened`).

**Other NULL-creator INSERT paths found:** `tour_orchestrator_service.py`
(generated) and `tour_editing_phase2.py` (custom edit) already set it.
`tour_worker_service.py:210` does **not** — reported here; it is a separate
service (worker-based generation) and was left unchanged.

---

## 3. The ⋮ menu shows only what applies (D711 §1)

In `screens/my_tours_screen.dart`:

- **Price** — shown only when `_canSell && role.isOwner` (and a sellable numeric
  id). A **members-only** community tour shows Price **disabled with an ⓘ**
  ("Members-only tours are covered by the membership dues…"); a **public**
  community tour / a plain owned tour keeps the live Price.
- **Request re-score** — shown only when `role.isOwner` **and not** a broadcast
  tour.
- Every **Price dialog** states *"People who already downloaded this tour keep
  it; the price applies to new downloads."* and, for a public community tour,
  *"Members get it included; non-members pay this price."*
- A member's `setPrice` refusal and the server's `members_only_no_price` are
  mapped to clear messages.

---

## 4. Role line (D711 §2)

`lib/utils/tour_role_label.dart` — one **pure** function
`tourRoleLabel(record, userId) → TourRoleLine{text, icon}`, rendered as the
**first, non-tappable** entry of the ⋮ menu (small grey text + icon). Cases:

- `Your tour`
- `Your community tour — you are the organiser`
- `Community tour · <name>`
- `Broadcast tour · <name>` (+ ` — you are the organiser`)
- `Audioura tour`

**Unit tests for every case:** `test/tour_role_label_local762_test.dart`
(10 tests, all green), including inference from `source_kind` alone and
defensive handling of odd types.

---

## 5. Price at creation (D711 §4)

- **Builder** (`organiser_audio_tour_screen.dart`) — an optional **"Price for
  non-members"** (Free + the round-dollar ladder), shown and enabled **only when
  visibility is Public**; sent with the publish (`price_tier`), which the server
  applies. Red test: `test/organiser_builder_price_local762_test.dart` (hidden
  for Members, shown for Public — 2 tests, green).
- **Generate** (`tour_generator_screen.dart`) — for a curator (`_canSell`), an
  optional price picker in the options (hidden for a members-only community
  target); a paid tier requires **Guide Terms** acceptance (LOCAL-691); applied
  via `TourPricingService.setPrice` once the tour has a numeric id.
- **Server** (`tour_pricing_service.set_price` + `communities_api`) — pricing a
  members-only tour is refused `members_only_no_price` (400); clearing
  (`tier=null`) is still allowed; a public community tour may be priced; members
  get the tour "Included with membership" (existing `/tours-near` / download
  entitlement path, unchanged).

---

## Tests

**Red-first, then green.**

### Flutter — full suite baseline
`flutter test` → **1104 passed, 7 failed**. The **7 failures are the known
network/e2e baseline** (`local109_swipe_e2e_test.dart` +
`storied_compat_screens_404_test.dart`, both require a live local server →
`SocketException: Connection refused`). **No new failures.** All **15 new
LOCAL-762 tests** pass in-suite:

- `share_spinner_nested_navigator_local762_test.dart` (3)
- `tour_role_label_local762_test.dart` (10)
- `organiser_builder_price_local762_test.dart` (2)

### Python — touched suites green
`tests/test_local762_tour_role_and_pricing.py` (11): Part A hermetic (the
organiser-audio INSERT stamps `creator_user_id`; a public publish stores
`price_tier`; a members-only publish with a price → 400); Part B DB-backed
against `audiotours_test` (every `tour_role` case; members-only `set_price`
refused; public priced; the `/role` endpoint; the 400 route mapping).
Touched suites `677 / 718 / 754b / 701 / 755` + `762` → **77 passed**, no
regressions.

> `audiotours_test` was missing migration 041 (`creator_user_id`); applied the
> idempotent `migration/sql/041_tour_creator.sql` to the test DB (no schema code
> of mine; the column already shipped in LOCAL-718).

---

## Live test — simulator only, own code, $0

**Never Michael's phones.** Ran on the **iPhone 17 simulator**
(`76941285-B4E8-49BC-B327-F94DB1BF1EDC`).

### Server — `live_local762.py` (in-process, against `audiotours_test`, port 5433)

Mounts BOTH the communities blueprint and `register_pricing_routes` on one Flask
app (the two surfaces the user-api + orchestrator serve in production), serves
its own MP3 over a localhost HTTP server, uses `is_test` rows with an
`L762-…{run}` prefix, cleans up only its own rows (D141), no purchase-bearing
rows (D690). **ALL CHECKS PASSED:**

```
[build] members tour creator_user_id=<organiser> source_kind=organiser_audio ✓
[role owner]  is_owner / is_organiser / is_broadcast = True ✓
[role member] is_owner / is_organiser = False ✓
[price members-only] owner refused members_only_no_price (400) ✓
[price members-only] clearing (tier=null) allowed ✓
[build public+price] price_tier=3 is_paid=True ✓
[build members+price] refused members_only_no_price, no row ✓
[price by member] refused (403) ✓
[budget] $0.00 — no OpenAI/AI calls ✓
```

**Row counts** (`audio_tours`, `communities`):
`before {0, 1}` → `after {2, 2}` (delta **+2 / +1**) → after cleanup back to
`{0, 1}`. (The one pre-existing `communities` row is unrelated and untouched.)

**DB note:** the two surfaces resolve the DB differently — `communities_api`
reads `DATABASE_URL`; `tour_pricing_service` uses `db_connection` which resolves
by `AUDIOURA_DB_TARGET`. The driver sets both to the test DB so a publish and the
role/price reads agree.

### App — simulator screenshots (`screenshots_local762/`)

Built `flutter build ios --simulator --debug` (Xcode build done) and captured via
`flutter drive` (the LOCAL-758 integration-test screenshot pattern — deterministic,
seeded, $0):

- `01_app_launch_simulator.png` — the app running on the simulator.
- `01_members_no_price.png` — builder, **Members** visibility: **no** price control.
- `02_public_price.png` — builder, **Public**: *"Price for non-members: Free"* with
  the grandfather note *"Members get it included; non-members pay this price.
  People who already downloaded it keep it."*
- `03_role_lines.png` — the three role-line cases with their owner-only
  Price/Re-score gating: *"Your community tour — you are the organiser"* (Price +
  Re-score), *"Community tour · Salem TV show funs"* (member → no Price/Re-score),
  *"Broadcast tour · Salem TV show funs — you are the organiser"* (no Re-score).

The simulator was shut down after the run. `simctl` has no tap subcommand and
`idb` is not installed, so coordinate-driven UI capture of the full
onboarding→Listen flow was not possible; the deterministic `flutter drive`
screenshots above cover the feature, and the share-spinner / role-line / price
behaviours are additionally pinned by the 15 widget/unit tests.

---

## Files

**Changed (app):** `lib/widgets/share_tour_sheet.dart`,
`lib/screens/home_screen.dart`, `lib/screens/my_tours_screen.dart`,
`lib/screens/subscription_management_screen.dart`,
`lib/screens/edit_stop_screen.dart`, `lib/screens/organiser_audio_tour_screen.dart`,
`lib/screens/tour_generator_screen.dart`, `lib/services/tour_pricing_service.dart`.

**New (app):** `lib/utils/tour_role_label.dart`,
`test/share_spinner_nested_navigator_local762_test.dart`,
`test/tour_role_label_local762_test.dart`,
`test/organiser_builder_price_local762_test.dart`,
`integration_test/local762_price_screenshot_test.dart`,
`test_driver/local762_screenshot_driver.dart`.

**Changed (server):** `tour_pricing_service.py`, `user-tracking/communities_api.py`.

**New (server/tests/live):** `tests/test_local762_tour_role_and_pricing.py`,
`live_local762.py`, `screenshots_local762/*.png`.

**No new Python module** was introduced (both changes extend existing files), so
no Dockerfile change is required. `audio_tour_app/ios/Podfile.lock` was modified
by `pod install` during the simulator build — an incidental artifact, **not
committed**.

**Not edited:** `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
`.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`.
