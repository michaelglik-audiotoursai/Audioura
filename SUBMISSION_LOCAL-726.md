# SUBMISSION — LOCAL-726: App Store must-haves

Block in communities (Apple Guideline 1.2), first-run "informational only"
notice, and crime wording in the content rater. Lawyer review ClickUp
`wdvrdayzt2`, items 2, 9, 10.

- **Branch:** `LOCAL-726-store-musts`
- **Base:** `subscribed` = `bf5ff0b8cb8f9b01b651cb66cfa81590804779e8`
  (`git merge-base --is-ancestor bf5ff0b8 HEAD` exits 0 — verified before commit).
- **code_sha:** the single commit on `LOCAL-726-store-musts` above its base
  `bf5ff0b8` — `git rev-parse HEAD` on the branch (e.g. `1766c931…`). The branch
  carries exactly one commit on top of `subscribed`.
- **Spend:** $0.00 — no paid API was called. Every rater test monkeypatches
  `tour_content_rating.classify`; every server test runs in `stub` IAP mode; the
  Flutter tests are hermetic. Well under the $0.50 budget.

---

## Item 9 — rater wording: history of crime vs how to commit crime

`tour_content_rating.py` — the model PROMPT (and the module docstring) now draw
the line the lawyer asked for:

- **general** explicitly includes the **history of crime** told factually (a
  heist, a gangster, a red-light district's past, a prison museum, a true-crime
  site) — "it does NOT become mature merely for naming crimes or criminals".
- **mature** is crime "dwelt on for lurid thrill or glamorised as entertainment
  rather than told as history" (the bare "crime treated as entertainment" is
  gone).
- **not_allowed** is scoped to content that "teaches, instructs or otherwise
  encourages the listener to COMMIT a crime (how to pick a lock, evade police,
  make a weapon, buy drugs)", with the dividing line stated explicitly:
  "recounting the history of a crime is allowed (general, or mature if lurid);
  explaining how to commit one is not_allowed."

Prompt-only change — no model behaviour is hard-coded; the model is held to the
new wording.

**Test:** `tests/test_local726_crime_wording.py` — two fixtures
(`HISTORY_OF_CRIME` → not `not_allowed`; `HOW_TO_COMMIT_CRIME` → `not_allowed`)
driven through the real `rate_text`/`review_status_for` with `classify` mocked
by a prompt-faithful rule, plus prompt-structure assertions, plus a **RED test**
(`RedWhenPromptMisreadTest`) in which an over-blocking rater that blocks all
crime, history included, fails the history fixture — proving the green test is
not vacuous.

```
python3 -m pytest tests/test_local726_crime_wording.py \
    tests/test_local687_content_rating.py \
    tests/test_local724_content_policy_truth.py -q
46 passed
```

---

## Item 10 — block function (Apple Guideline 1.2)

### Server

**Migration (additive, idempotent):** `migration/sql/044_community_blocks.sql`
creates ONE table, `community_blocks`, carrying both directions of block:

- `kind = 'member_block'` — a member hides a blocked user's communities and
  community tours from their OWN view (the block is the blocker's business only).
- `kind = 'organiser_bar'` — an organiser removes and bars a member: their
  membership is deleted (no new content) and a bar is recorded so they cannot
  rejoin by code. **Downloaded audio stays on the device (D658)** — the server
  never deletes it.

`UNIQUE (community_id, blocker_user_id, blocked_user_id, kind)` (re-block is a
no-op); `CHECK (blocker_user_id <> blocked_user_id)`; `ON DELETE CASCADE` from
`communities`. No DROP/DELETE/retype; `CREATE TABLE/INDEX IF NOT EXISTS`.

**Endpoints** (`user-tracking/communities_api.py`):

- `POST /communities/<id>/block` `{user_id, blocked_user_id, kind?, reason?}` —
  member_block (anyone) or organiser_bar (owner only → 403 otherwise; also
  deletes the membership row). Idempotent (`ON CONFLICT DO NOTHING`).
- `POST /communities/<id>/unblock` `{user_id, blocked_user_id, kind?}` — the
  blocker lifts their own block (member from Settings, organiser from the member
  list). Returns `removed: 0|1`.
- `GET  /communities/blocks?user_id=` — everything this user has blocked, for
  Settings → Blocked. Schema-tolerant (empty list on an un-migrated DB).
- `GET  /communities/<id>/members?user_id=<owner>` — the owner's member list
  (owner only), each row `{user_id, expires_at, active, barred}`, for the
  member-row ⋯ "Remove & bar".

**Enforcement:**

- A barred member cannot rejoin by code — `is_user_barred` gate added to BOTH
  `verify_community_pass` (the pass purchase path → 403 `barred`) and
  `join_free_community`.
- A blocked organiser's communities and community tours disappear for the
  blocker — `member_block` filtering added to `_active_community_ids_for_user`
  (drives `/communities/new-tours`), `my_communities` (`/communities/mine`) and
  `map_communities` (`/communities/map`). The community page payload now also
  carries `owner_user_id` so the app knows whom to block.

**Tests:** `tests/test_local726_community_blocks.py` — 14 tests, DB-backed
through the real blueprint (stub IAP), covering member-block hiding on mine/map/
new-tours, "only the blocker's view", list + unblock restores the view;
organiser bar removes membership + blocks rejoin-by-code, owner-only guard,
member-list `barred`, unbar lets the member return; guards (self-block, missing
fields, bad kind, unknown community, idempotent double-block); and a **RED test**
(`test_red_broken_bar_gate_lets_barred_member_rejoin`) that forces the bar gate
to always return False and shows the barred member rejoins — proving the "cannot
rejoin" guard is real.

```
# Own throwaway container only (never audioura-*):
docker run --rm --name local726-pg -e POSTGRES_USER=admin \
    -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=audiotours_test \
    -p 5455:5432 postgres:15
# schema cloned from the shared audiotours_test, migration 044 applied,
# plans + community_pass_products seeded.
DATABASE_URL=postgresql://admin:password123@localhost:5455/audiotours_test \
  DB_HOST=localhost DB_PORT=5455 python3 -m pytest \
  tests/test_local726_community_blocks.py \
  tests/test_local690_communities.py tests/test_local700_communities_ux.py \
  tests/test_local702_organiser_steps_down.py \
  tests/test_local704_dollar_minimum_and_member_count.py \
  tests/test_local713_new_tours.py -q
100 passed   # 14 new + 86 existing community tests, no regressions
```

### App

- `community_page_screen.dart` — the AppBar ⋯ menu now has **Report to owner**
  (everyone), **Block organiser** (a member only, not the owner), and **Manage
  members** (owner only). "Manage members" opens `_ManageMembersSheet` with a
  per-row ⋯ → **Remove & bar** (confirmation names the D658 download-stays rule).
- `my_communities_screen.dart` — the Listen-tab community row ⋯ menu gains
  **Block organiser** (fetches the page to learn the owner id, then blocks).
- `blocked_users_screen.dart` (new) — **Settings → Blocked**: lists everything
  the device has blocked (member blocks and organiser bars), each with
  **Unblock**. Reached from the Communities card in `about_screen.dart`.
- `communities_service.dart` / `communities_models.dart` — `blockUser`,
  `barMember`, `unblockUser`, `members`, `myBlocks`; `Community.ownerUserId`,
  `CommunityMember`, `CommunityBlock`.

---

## Item 2 — first-run informational notice

`informational_notice_screen.dart` (new), gated in `main.dart` after onboarding:
shown ONCE per device via the versioned key `info_notice_ack_v1`. A new install
and an existing install updating to this version both lack the key, so both see
it exactly once; "Got it" sets the key and it never shows again. Short, calm,
friendly — the four required messages:

- tours are written with AI and may contain errors;
- they are for information and entertainment, not navigation or safety advice;
- follow local signs and laws, and walk, ride or drive at your own risk;
- a **Read the Terms** link to `https://audioura.com/terms`.

---

## Verification

- **Python:** 46 rater tests + 100 community/block tests pass (see above). Both
  suites include a RED test.
- **Flutter tests:** `flutter test test/local726_store_musts_test.dart` → 10
  passed (block model parsing incl. `ownerUserId`, `CommunityMember`,
  `CommunityBlock`; notice `seen()/markSeen()` once-per-device incl. the
  "existing install sees it once after update" case; a widget test that renders
  the four points + "Got it" and asserts the ack). Full suite: **731 passed, 6
  failed** — the 6 failures are all in `local109_swipe_e2e_test.dart`, a live-
  server E2E test (SocketException: connection refused to a local HTTP server);
  they are environment-dependent and unrelated to this change.
- **flutter analyze** on every changed file: no new warnings or errors (only
  pre-existing `info`/`warning` lints in `about_screen.dart`/`main.dart`).
- **Debug build on the emulator ONLY** (`emulator-5554`, the `local715_test`
  Android AVD — never Michael's wirelessly-connected iPhone): `flutter build apk
  --debug` built `app-debug.apk`, installed and launched on the emulator. The
  first-run flow was exercised end to end: onboarding → **the informational
  notice** → "Got it" → the app. Screenshots in
  `submission_screens/local726/`:
  - `01_onboarding.png` — onboarding (DEBUG banner visible).
  - `02_first_run_notice.png` — **the first-run notice** (all four points + the
    Terms link + "Got it"). This is the key item-2 artifact.
  - `03_app_home_after_notice.png` — the app after acknowledging.

  **Block-menu screenshot limitation:** the community ⋯ block menu needs a live
  community page, which requires the user-api backend. The emulator debug build
  cannot reach the production backend ("Audioura couldn't connect securely" —
  the debug build has no baked gateway key / attestation), and the block
  endpoints are not deployed there, so a live on-device block-menu screenshot
  was not achievable from the emulator. The block UI is instead proven by the 14
  passing DB-backed server tests (including the RED test) and the passing
  Flutter model/widget tests, plus the menu code in `community_page_screen.dart`
  / `my_communities_screen.dart` / `blocked_users_screen.dart`.

## Live DB — additive migration, row counts

Migration `044_community_blocks.sql` is additive (one new table). Applied and
tested ONLY on the throwaway `local726-pg` container (postgres:15, host port
5455), never on `audioura-*` and never on the live `audiotours` DB. No
`DELETE FROM audio_tours`. Row counts on the migration-touched table
(before → after the full test run, which cleans up its own rows):

| table                  | before | after |
|------------------------|--------|-------|
| community_blocks (new) | 0      | 0     |
| communities            | 0      | 0     |
| community_memberships  | 0      | 0     |

LEAD applies migration 044 to the shared/live DB when merging, exactly as prior
community migrations (029/035/036/042) were applied — this agent tested it on
its own container only.

## Files

- `tour_content_rating.py` (PROMPT + docstring)
- `migration/sql/044_community_blocks.sql` (new)
- `user-tracking/communities_api.py` (block helpers + endpoints + gates/filters)
- `audio_tour_app/lib/screens/informational_notice_screen.dart` (new)
- `audio_tour_app/lib/screens/blocked_users_screen.dart` (new)
- `audio_tour_app/lib/screens/community_page_screen.dart`
- `audio_tour_app/lib/screens/my_communities_screen.dart`
- `audio_tour_app/lib/screens/about_screen.dart`
- `audio_tour_app/lib/main.dart`
- `audio_tour_app/lib/services/communities_service.dart`
- `audio_tour_app/lib/services/communities_models.dart`
- `tests/test_local726_crime_wording.py` (new)
- `tests/test_local726_community_blocks.py` (new)
- `audio_tour_app/test/local726_store_musts_test.dart` (new)
- `submission_screens/local726/*.png`
