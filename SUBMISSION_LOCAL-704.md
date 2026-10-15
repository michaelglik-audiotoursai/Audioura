# SUBMISSION — LOCAL-704: $1 minimum to join any community; member count everywhere (D665 / D666)

**Branch:** `LOCAL-704-paid-only-member-count` (from `subscribed` @ 94bc015f)
**Agent:** Mac Mini Kiro

Every community member now pays at least **$1** to join (the commitment fee —
D665), there are **no free communities**, every community **shows its member
count** (owner excluded), the **organiser is never a member**, and after launch
a community that drops **below 2** active members is warned weekly and
**archived only after a full week at 0** active members (D666). Decisions read:
D657, D658, D663, D664, D665 (+ addendum), D666.

---

## 1. No free communities; the $1 commitment-fee pass (D665)

* **Catalogue.** `audioura.pass.usd1` ($1.00, label `$1`) added to
  `community_pass_products` in **migration 029** (so a fresh DB has it) and
  re-asserted idempotently in the new **migration 038**. Added to
  `ios/Audioura.storekit` as a non-renewing subscription (internalID
  `E001E001-0000-4000-8000-000000000704`). The Flutter pass ladder
  `kPassLadderDollars` now starts at **1** (35 prices); `kPassStoreIds` therefore
  includes `audioura.pass.usd1`. **Tour prices are unchanged** — the tour ladder
  (`kTierProductIds`) keeps its $2 floor; only the community-pass ladder gained a
  $1 floor.
* **Pass price picker.** Create-form quick picks are now **$1, $3, $5, $10, $20**;
  a custom price snaps to the ladder, floored at **$1** (`snapDollarsToLadder`
  over the $1-floor ladder).
* **Create.** `create_community` forces `is_paid = TRUE` and returns **400
  `pass_required`** when no pass option is offered. The create form removed the
  "Free" toggle: `_isPaid` is a const `true`, the pass section is always shown,
  and the submit requires ≥ 1 price + length.
* **Free join.** `POST /communities/<id>/join` now returns **402 `pass_required`**
  for every community (and **409 `owner_cannot_join`** for the owner). The free
  path is gone.

## 2. The organiser is not a member (D665 addendum)

* The owner **cannot buy or join** their own community: both
  `verify_community_pass` and the free-join endpoint return **409
  `owner_cannot_join`**.
* The owner is **excluded** from `member_count` and the launch bar (every count
  joins against `owner_user_id` and excludes it).
* The owner has **full access without a pass**: `_community_page` already treats
  `is_owner` as active, so the owner sees every episode/tour; the app hides the
  Join/Buy section from the owner.
* **Migration 038** deletes any owner self-membership a pre-rule build may have
  written, so the count and bar start correct.

## 3. Launch bar is always 2 paying members (D664, amended by D665)

* `_qualifying_member_count` lost its free-community branch — it now counts only
  **paid** members (`transaction_id IS NOT NULL`), owner excluded, for every
  community. The LOCAL-703 free-community tests were removed/rewritten to paid.

## 4. Member count everywhere (D665)

New `_active_member_count` (unexpired **paid** passes, owner excluded) is the
single source of truth. `member_count` is now in:

* the community page payload (`_community_page`);
* the map pin list (`/communities/map`) → shown on a new **map pin sheet**;
* `/communities/mine` → shown on each **My communities** row;
* the community page UI (a prominent "N members" line, `Key('member_count_label')`);
* the **invite email** (`CommunityCopy.emailInviteBody(..., memberCount:)` → "12 members").

`CommunityCopy.memberCountLabel` gives "1 member" / "12 members". A code/search
result opens the community page, which shows the count.

## 5. After launch: weekly warnings below 2, archive after a week at 0 (D666)

New columns on `communities` (migration 038): `low_members_since`,
`last_low_warning_at`, `zero_members_since`; `archived_reason` CHECK widened to
include `no_members`.

`run_post_launch_member_health` (called from the hourly `run_launch_window`):

* count **≥ 2** → healthy: clear the low/zero trackers.
* count **< 2** → warn the **day it drops (day 0)**, then **every 7 days**
  (`last_low_warning_at` guards the cadence — not daily); stops when back to ≥ 2.
* count **== 0** → also track `zero_members_since`; at **7 consecutive days** →
  archive (status `archived`, reason `no_members`). **1 member is never
  archived.**

`run_launch_window` now returns `low_members_warned` and `archived_no_members`
alongside the existing buckets; the warn buckets are the ids to notify (the push
is the notification layer's job, same split as the launch reminders).

## 6. Demo book club conversion + 30-day grandfather (D665)

Migration 038, scoped to **currently-free** communities (covers the demo book
club, id 1, and any other free community):

* adds a **$1 / month** option (`audioura.pass.usd1`, 30 days) if none exists;
* **grandfathers** current free members (NULL expiry) to `NOW() + 30 days`
  (their `transaction_id` stays NULL, so they do **not** count toward the paid
  launch bar — a grandfathered member is not a committed paid member);
* flips `is_paid = TRUE`.

Idempotent (ON CONFLICT / value-asserting backfill / IF NOT EXISTS). Applied to
my **test DB** (`audiotours_test`); LEAD applies it to the shared DB.

---

## Tests

New **`tests/test_local704_dollar_minimum_and_member_count.py`** (10 tests, all
green) covers: pass_required on create and free join; the $1 product verifies
(stub) and grants; member_count excludes owner and expired members; owner
join/buy → 409; owner plays everything without a pass; demo-book-club conversion
+ 30-day grandfather; post-launch drop to 1 → warnings **day 0, 7, 14 (not
daily)** and **back to 2 → stops**; **0 for 6 days still active, 7 days →
archived (no_members)**; **1 member for 30 days → never archived**.

Adjusted existing suites (free communities → paid, owner-buy → 409, free-join →
402): `test_local690_communities.py`, `test_local700_communities_ux.py`,
`test_local702_organiser_steps_down.py`, `test_local703_launch_window.py`.

Flutter `test/communities_service_test.dart` gained member-count parsing +
`memberCountLabel` + invite-email member-count tests and the updated 35-price
ladder assertion.

### Results (verified this session)

* **Community pytest (combined):** `test_local690/700/701/702/703/704` +
  `test_local693` → **112 passed**.
* **Flutter community units:** `communities_service_test.dart` (51) +
  `launch_window_countdown_test.dart` → **all passed**.
* **Full Flutter suite:** 515 passed, 6 failed — the 6 are pre-existing
  **environmental** failures in `single_playback_controller_test.dart` (needs
  Node) and `local109_swipe_e2e_test.dart` (needs a live server on localhost);
  neither file was touched by this task.
* **`flutter analyze`** on all changed `lib/` files: **0 errors**.
* **Migration 038** applied to `audiotours_test` and re-applied (idempotent
  no-op) successfully.

## App build

`pubspec.yaml`: `2.4.23+60` → **`2.4.23+61`**.

## Process

Own containers + test DB only — migration 038 applied to `audiotours_test` via
`docker exec development-postgres-2-1` (never `-p audioura`, no rename of
`audioura-*`); LEAD applies migrations to the shared DB. No DECISIONS / CLAUDE /
BACKLOG / WORK_QUEUE / .continuous_dev edits.

## Files changed

* `migration/sql/029_communities.sql` — add `audioura.pass.usd1` to the catalogue.
* `migration/sql/038_community_dollar_minimum_and_member_count.sql` — **new**:
  $1 re-assert, D666 columns, `no_members` reason, owner self-membership
  cleanup, free→paid conversion + 30-day grandfather.
* `user-tracking/communities_api.py` — paid-only launch bar, `_active_member_count`,
  `member_count` in payloads, owner 409, pass_required, D666 health pass.
* `audio_tour_app/ios/Audioura.storekit` — `audioura.pass.usd1`.
* `audio_tour_app/lib/services/iap_service.dart` — $1 floor on the pass ladder.
* `audio_tour_app/lib/services/communities_models.dart` — `memberCount`,
  `memberCountLabel`, email member count, no-free about text.
* `audio_tour_app/lib/screens/communities_about_screen.dart` — no Free toggle,
  $1/3/5/10/20 quick picks, email member count.
* `audio_tour_app/lib/screens/community_page_screen.dart` — member-count line,
  hide Join/Buy from owner.
* `audio_tour_app/lib/screens/my_communities_screen.dart` — member count on rows.
* `audio_tour_app/lib/screens/home_screen.dart` — map pin sheet with member count.
* `audio_tour_app/pubspec.yaml` — build +61.
* Tests: `test_local704_*` (new) + adjusted `690/700/702/703` +
  `communities_service_test.dart`.
