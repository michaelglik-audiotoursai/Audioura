# SUBMISSION — LOCAL-610 Plan page corrections (app 2.4.5+31)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-610-plan-page-r2`
**Base:** `subscribed` @ `33606ec` (verified: `git merge-base --is-ancestor 33606ec HEAD` → 0)
**App version:** `2.4.5+31` (pubspec kept CRLF)

Michael's four corrections after testing 2.4.4+30, plus the required tests. No
DELETE, no GCloud, and **no server behaviour change** — the only server edit is a
passthrough of a column the `plans` table already holds.

---

## 1. The Free card is now level-aware (request 1)

`audio_tour_app/lib/screens/plan_screen.dart`

`_freeCard()` now branches on the current level:

| Current level | Title | Queue action | Code box | "Get the Free plan" |
|---|---|---|---|---|
| **l1 Introduction** | "Get the Free plan" | **shown** (Join the queue / Update my queue email) | shown | yes |
| **l2 Free** | "Have a code?" | **hidden** | shown | **no** |
| **l3 / l4 (paid)** | "Have a code?" | hidden | shown | no |
| **tester / admin** | "Have a code?" | hidden | shown | no |

- A Free (l2) user is never invited to "get" the Free plan they already hold.
- The code box is reachable from **every** level — it is how Michael switches
  levels with a level code, and how a friend's invitation or a queue offer is
  redeemed. The server still decides which of the three code kinds it is
  (`/l2/claim` in `entitlements_api.py`, unchanged).
- Only l1 — the one level that can still join the free queue — shows the queue.

Implementation: `_freeCard()` → `_freeCardIntroduction()` (l1) or
`_codeOnlyCard()` (everything else), sharing one `_codeBox()` widget.

## 2. Buy-button labels; "round" removed from user-facing text (request 2)

`audio_tour_app/lib/screens/plan_screen.dart` (buy card):

- `$10 Pack — 5 new tours + 5 edits, up to 10 stops`
- `Curator ($25) — 25 tours or edits, up to 25 stops, sell your tours`

`audio_tour_app/lib/services/entitlements_service.dart` (`levelLabel`): l3 →
`$10 Pack`, l4 → `Curator`. The word **"round"** no longer appears anywhere a
user sees it (verified by a test that scans every visible `Text` widget). The
`IapProduct.l4Round` enum / `audioura.round.l4` StoreKit product id are internal
identifiers the user never sees and are intentionally left unchanged.

## 3. Plain rules under the levels (request 3)

`audio_tour_app/lib/screens/plan_screen.dart` → `_rulesText()`, shown under the
level list in the "The plans" card:

- **Free:** "Stay active: open Audioura at least once a week. After **N** days
  without a visit your Free plan returns to Introduction, and you can rejoin the
  queue." — **N comes from the API** (`plans.inactivity_days`), not a constant
  (see §5).
- **$10 Pack and Curator:** "Each purchase is good for one month. Anything
  unused after a month expires, and you can buy another pack at any time. Buying
  early starts a new month and replaces what's left. Nothing renews
  automatically." When the device holds a pack, the current anniversary date is
  shown ("Your current month ends on <date>").

### These statements match `subscription_levels.py` behaviour (D613)

The pack rule is a plain-words restatement of `grant_pack()` in
`subscription_levels.py` (the authority used by the orchestrator and editing
service; `SUBSCRIPTION_LEVELS.md` / D613 cited at `subscription_levels.py:5`):

- **"good for one month" / anniversary:** `grant_pack` sets the anniversary to
  `paid_at + 1 calendar month` — `subscription_levels.py:262`
  (`anniversary = add_one_calendar_month(paid_at)`) and the stored
  `anniversary_at = EXCLUDED.anniversary_at` at `subscription_levels.py:276`.
- **"Buying early starts a new month and replaces what's left" (no carry-over,
  D613):** the docstring at `subscription_levels.py:257-258` — *"Paying early
  resets the date and replaces the allowance (unused units do not carry over)"* —
  realised by the `ON CONFLICT … DO UPDATE` that resets
  `fresh_used = 0, edits_used = 0, ops_used = 0` at
  `subscription_levels.py:277-279`. An early purchase overwrites `anniversary_at`
  and zeroes the counters, so remaining units are discarded, not added.
- **"Nothing renews automatically":** nothing in the codebase charges or
  re-grants on the anniversary; at/after it, generation is simply gated
  (`is_renewal_due`, `subscription_levels.py:97`) until the user buys again.

The Free inactivity rule matches the L2 seat lifecycle:

- The number is `plans.l2.inactivity_days` — `l2_seats.get_inactivity_days()`
  reads exactly that column (`l2_seats.py:78-80`).
- "After N days … returns to Introduction" is the eviction step of the hourly
  seat job: *"EVICT — L2 devices idle >= inactivity_days (plans.l2, design 7)
  drop to L1"* (`l2_seat_job.py:9`). L1 is "Introduction", and the Free card on
  l1 is exactly where the user rejoins the queue.

## 4. Version + build (request 4)

- `audio_tour_app/pubspec.yaml`: `2.4.4+30` → `2.4.5+31`. The file is CRLF;
  the bump was applied byte-wise so every line (incl. the version line) keeps
  `\r\n` (verified with `od -c` and `file`).
- `flutter analyze`: **no new errors or warnings** in the changed files. (The
  repo baseline has pre-existing `info`/`warning` lints in unrelated files;
  none are introduced here.)
- `flutter build ios --no-codesign`: **compiles** — `✓ Built
  build/ios/iphoneos/Runner.app (37.3MB)`.
- **Not installed** — LEAD installs.

## 5. The one server edit: a passthrough, not a behaviour change

`user-tracking/entitlements_api.py`

So the Free rule's day count comes from the DB rather than a hardcoded 7, the
`/entitlements/me` (and `/app-open`, `/lapse`, `/purchases/verify`) payload now
carries `plans.inactivity_days`:

- `_me_payload`: adds `'inactivity_days'` for the current level (from the plan
  row already fetched).
- `_visible_levels`: adds `inactivity_days` to each level dict (so the Free rule
  can read the **Free** level's value even when the device is on another level).

No logic, no gating, no writes change — it only returns a column the `plans`
table already stores and that `l2_seats` / `l2_seat_job` already read. If the
server sends an older payload without the field, the app falls back to the
current-level value and finally to 7, so the copy still reads sensibly offline.

Dart side (`audio_tour_app/lib/services/entitlements_service.dart`):
`Entitlements.inactivityDays`, `PlanLevel.inactivityDays`, parsed defensively,
and `Entitlements.freeInactivityDays` (prefers the l2 level, then the current
level, then 7).

## Tests

`audio_tour_app/test/plan_screen_level_aware_test.dart` (new, 18 tests, all
pass):

- **req 1:** l1 shows "Get the Free plan" + "Join the queue" + code box; l2
  shows "Have a code?" with the code box only and **neither** "Join the queue"
  nor "Get the Free plan"; l3, l4 and admin show the small "Have a code?" row;
  the code box is present at **every** level.
- **req 2:** the two exact button labels render; no visible `Text` contains
  "round".
- **req 3:** the Free rule shows the day count **from the API** (test injects
  `inactivity_days: 9` and asserts "After 9 days", and that the default 7 does
  **not** appear); the pack/Curator one-month rule text is present; the
  anniversary line appears only when a pack is held.

A `PlanScreen(initialEntitlements:)` test seam (null in production) lets the
widget render any level offline without a running user-api.

`audio_tour_app/test/renewal_logic_test.dart`: `levelLabel` expectations updated
to `$10 Pack` / `Curator` and that l4 contains no "round".

**Suite:** 269 pass / 6 fail. All 6 failures are in
`test/local109_swipe_e2e_test.dart`, a pre-existing live-integration test that
requires a backend on `localhost:5102`; it is unrelated to this change and fails
only because no backend is running in this environment.

## Files changed

| File | Change |
|---|---|
| `audio_tour_app/lib/screens/plan_screen.dart` | level-aware Free/code card; button labels; `_rulesText()`; test seam |
| `audio_tour_app/lib/services/entitlements_service.dart` | `inactivityDays`/`freeInactivityDays`; `levelLabel` l3/l4 |
| `audio_tour_app/pubspec.yaml` | `2.4.5+31` (CRLF preserved) |
| `audio_tour_app/test/plan_screen_level_aware_test.dart` | new widget tests |
| `audio_tour_app/test/renewal_logic_test.dart` | `levelLabel` expectations |
| `user-tracking/entitlements_api.py` | `inactivity_days` passthrough (no behaviour change) |
