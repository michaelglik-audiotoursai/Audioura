# SUBMISSION — LOCAL-753: Members find their community's tours on map/search, and can translate them from the community page

**Branch:** `LOCAL-753-member-discovery-translate` (from `subscribed` @ `ebc3c3bf`, which contains LOCAL-752)
**Base verified:** `git merge-base --is-ancestor ebc3c3bf HEAD` → 0 (on the correct, unpushed-local tree, not `origin/*`).

## Decisions implemented
- **D707** — an **active member or the owner** of a community now SEES its **members-only** tours on `/tours-near`, `/search`, `/tour-by-code` and `/tour-info`, with the community badge; everyone else still never does. A member (not just the owner) **may translate** a community tour; the result becomes part of the community.
- **D663 §3** — a **public** community tour shows to everyone with the badge; download still requires an active membership (402 `membership_required` → the app opens the community join/invite screen).
- **D706** — a **listed** community's new tour defaults to **public** in the Generate "For:" selector (members-only stays selectable); a **private** community keeps the members default.
- **LOCAL-752 A2** — the community page now uses the server's per-tour `languages` list (originals only).

## What changed

### Server
**`map_delivery/app.py`** (the discovery image; self-contained DB reads, no cross-container import)
- New pure helper `_discovery_visible(community_id, visibility, is_member) -> bool`: ordinary → visible; public → visible to all; members-only → visible only when `is_member`.
- `/tours-near` and `/search-tours`: read `user_id` (already present for Match %), add a per-community membership cache (`_is_active_member`, one read per community), and replace the old blanket `members → hidden` filter with `_discovery_visible(...)`. A members-only tour shown to its member/owner carries the same community badge a public one does.
- `/tour-info`: previously had **no** community handling (a members-only tour's detail leaked to anyone). Now reads the tag + viewer membership while the cursor is open, returns **404** for a members-only tour to a non-member (same answer the list gives), and adds the community badge fields to a visible one.
- `/tour-by-code`: previously had **no** community handling. Now resolves a members-only tour through its code only for an active member/owner (else a clean 404 — a members-only tour is never leaked by its code), and adds the badge to a resolved community tour.

**`translation-service/translation_service.py`**
- `_community_translate_block` now allows the **owner OR an active member** (new `_is_active_community_member` reads `community_memberships.expires_at` NULL/future, mirroring map_delivery's `_is_active_member`). A non-member/expired member → **403 `NOT_COMMUNITY_MEMBER`** (was `NOT_COMMUNITY_OWNER`); no `user_id` → 401. This undoes, per D707, the LOCAL-752 A3 member-403. Translations already inherit `community_id`/`community_visibility` (LOCAL-752 A1, unchanged), so a member's translation becomes community content every member can download free.
- **D708 / organiser-audio (LOCAL-754B):** not present in this tree (no organiser-audio refusal code exists), so "refused for everyone" is **not applicable here** and was not added; it belongs with 754B when that merges.

**`user-tracking/communities_api.py`**
- `GET /communities/mine-owned` now returns each community's `visibility` (`COALESCE(visibility,'private')`) so the app can preselect the Generate visibility (D706).

### App (`audio_tour_app/lib`)
- `services/community_tour_models.dart`: `OwnedCommunity.visibility` (`listed`|`private`, default `private`) + `isListed`; `CommunityTourRules.initialVisibilityFor(c)` (listed→public, private→members); `translateLanguageCodes` (the 10 canonical languages, matching `TourTranslationHelper.availableLanguages`) and `translateCandidates(present)` (canonical languages not yet present).
- `services/communities_models.dart`: `CommunityInviteTourOption.languages` parsed from the server's `languages`.
- `services/community_tour_service.dart`: `ownedCommunities` parses `visibility`.
- `screens/tour_generator_screen.dart`: the "For:" selector preselects visibility via `initialVisibilityFor` (both the dropdown and the `_applyInitialCommunity` path) — public for a listed community, members for a private one; members-only stays selectable.
- `screens/home_screen.dart`: the `/tour-by-code` call now sends `user_id` (with the existing `adult` flag) so a members-only community tour resolves for a member. `/tours-near` and `/search-tours` already sent it.
- `screens/community_page_screen.dart`: each tour row shows its languages; **Download** picks the member's this-community listening language when the tour already has it (else the original), fetching an existing translation via the shared `TourTranslationHelper` (no new generation on download); a **Translate** action (key `translate_tour_<id>`) offers only the not-yet-present languages (key `translate_lang_<id>_<code>`) to members/owners, runs the same helper/plan allowance as Listen → Translate, and refreshes the list. Public-tour download by a non-member still opens the join/invite gate (`_showMembersOnlyTourGate` on 402 `membership_required`), unchanged across map, search and tour-by-code (shared download path).

## Tests (red first, then green)

### New
- `tests/test_local753_member_discovery.py` — 5 tests for `_discovery_visible` (imports the real `map_delivery/app.py` with deps stubbed). RED before, GREEN after.
- `tests/test_local753_member_translate.py` — 6 tests for the member-allowed translate gate (fake cursor; active free/paid member + owner allowed, expired/stranger 403, no user_id 401, ordinary tour open). RED before, GREEN after.
- `audio_tour_app/test/community_member_discovery_local753_test.dart` — 8 tests for the app models/rules (OwnedCommunity visibility, `initialVisibilityFor`, `languages` parsing, `translateCandidates`). GREEN.

### Updated
- `tests/test_local752_organiser_only_translate.py` — the "member" case there holds **no** membership row, i.e. a non-member, so it still asserts 403; renamed accordingly and dropped the `NOT_COMMUNITY_OWNER` error-code assertion (the code is now `NOT_COMMUNITY_MEMBER`). D707's member-allowed path is covered by the new 753 test.

### Results
- **Python touched/related suites: 49 passed** — 753 discovery (5), 753 translate (6), 752 organiser-only (5), 752 listed-default (10), 752 inherits, 701 community tours, 745 organiser-only, 745 member-update. All hermetic.
- **`test_local666` / `test_local671`** (map_delivery scripted-DB endpoint tests): **14 failed / 12 passed, IDENTICAL on base `ebc3c3bf` and with my changes** (verified by `git stash` A/B). These are **pre-existing baseline failures** — their `_install_db` harness is out of sync with the endpoints independently of LOCAL-753. My changes add **zero** new failures (the community reads return `(None, None)` when the columns are absent, so the ordinary-tour path is unchanged).
- **Flutter: +977 passed.** The only failures are the **7 known network/server-dependent baseline** cases: `local109_swipe_e2e_test.dart` (6, `SocketException: Connection refused`) and `storied_compat_screens_404_test.dart` (1). No new deterministic failures; `flutter analyze` reports no errors in any touched file.

## Live test (own containers only, budget $0.00)
- Brought up my **own** throwaway `postgres:13` container `local753-pg` on spare port **5455** — never `audioura-*` / `development-*` / `postgres-2`, never `-p audioura`.
- **Discovery proof:** seeded a listed community (owner `owner-753`), an active member, a members-only tour, a public tour, an ordinary tour and a share code; ran the **real** `map_delivery` endpoints in-process (DB pointed at 5455). Asserted the member sees the members-only tour on tours-near/search/tour-info(200)/tour-by-code(200) **with the badge**; a non-member does **not** (lists omit it; tour-info/tour-by-code 404 with the log line `Tour 75301 hidden — members-only community tour, viewer not a member`); the public tour is badged for all; the ordinary tour is visible to all. **Row count 3 → 3 (inserts only; no deletes).**
- **Translate-gate proof:** ran the **real** `_community_translate_block` against the real DB — owner + active free member + active paid member allowed; expired member + stranger 403; no `user_id` 401; ordinary tour open. **No paid translation was run.**
- Shut down `local753-pg` and removed the temporary proof scripts. Confirmed Michael's 14 `audioura-*` containers are still up and no `local753` containers remain. **No `DELETE FROM audio_tours`, no deletes of purchase-bearing rows (D690).**

## Not touched
DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`.
