# SUBMISSION — LOCAL-742: Organiser's community page gets "Add a tour" → Generate with that community preselected

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-742-community-add-tour`
**Base:** `subscribed` @ `b6427bba` (verified: `git merge-base --is-ancestor b6427bba HEAD` → 0)
**code_sha:** `32a3973c36679f031f63829397ddf448d6949029`

## Why
Michael (2026-10-23, iPhone, his new "Salem" community): *"When I come to my
community I see no ability to create a tour."* The only path was Generate tab →
the "For:" selector. An organiser looking at their own community page had no hint
it existed.

## What changed

### `audio_tour_app/lib/screens/community_page_screen.dart`
- Owner-only **"Add a tour"** button (key `add_a_tour_button`), prominent, near
  the top above the tour list (before the Organiser card). Non-owners (members,
  visitors) never see it.
- Owner **empty-state** action when the community has no tours yet:
  "No tours yet. Add the first one." + an "Add a tour" button (key
  `add_first_tour_button`).
- `_openAddTour(c)` pushes `TourGeneratorScreen(initialCommunityId: c.id)` as a
  route and reloads the page on return (so a tour just generated for the
  community appears — existing `community_id` path, not re-implemented).
- Added an `initialCommunity` **test seam** (constructor param + assert) so the
  page renders a supplied community offline for widget tests.

### `audio_tour_app/lib/screens/tour_generator_screen.dart`
- New optional `initialCommunityId` param. Once `_ownedCommunities` has loaded,
  `_applyInitialCommunity` preselects that community in the "For:" selector with
  visibility = `CommunityTourRules.defaultVisibility` (`'members'`). No param →
  today's behaviour exactly ("Just me / public as usual"). An id the organiser
  does not own is a no-op (falls back to "Just me").
- Added an `initialOwnedCommunities` **test seam** so the selector renders
  offline for the widget test.

### `docker-compose.local742.yml`
Isolated live-test stack: `user-api-742` + a throwaway tmpfs `postgres-742`.
Own project name `local742`, spare 549xx ports, own DB. Never `-p audioura`,
never `audioura-*`, never the production DB.

## Tests (`audio_tour_app/test/community_add_tour_local742_test.dart`, 6 tests, all green)
- **OWNER sees** the top button AND the empty-state button + "No tours yet…".
- **MEMBER does NOT see the button — the RED test** (a member shown the button
  fails). Verified it is the gate: the button is `if (c.isOwner)`.
- **NON-MEMBER does NOT see** the button.
- `TourGeneratorScreen(initialCommunityId: 55)` → "For: my community Salem"
  selected, Members radio `groupValue == 'members'`, no "Just me".
- No `initialCommunityId` → "Just me / public as usual", no visibility radios.
- Unknown `initialCommunityId` (9999) → falls back to "Just me".

```
flutter test test/community_add_tour_local742_test.dart  → 00:01 +6: All tests passed!
```

### Full suite / baseline
```
flutter test  → 895 passed, 7 failed
```
The 7 failures are the pre-existing baseline, all `SocketException: Connection
refused` (need a live local server), none in my touched files:
- 6 in `test/local109_swipe_e2e_test.dart`
- 1 in `test/storied_compat_screens_404_test.dart`

No new failures.

### Analyze (touched files)
```
flutter analyze lib/screens/tour_generator_screen.dart \
                lib/screens/community_page_screen.dart \
                lib/config/endpoints.dart \
                test/community_add_tour_local742_test.dart
```
0 errors. Only pre-existing `info`/`warning` lints; the one item in new code is a
`groupValue` deprecation `info` in the test, which matches the production widget's
own usage. No new issues introduced by the lib edits.

## Live test (iOS simulator — iPhone 17 Pro Max, `CB4B3D66-…`)
NEVER Michael's phones. Own isolated stack only (`-p local742`, 549xx), own
throwaway Postgres. Michael's connected iPhone and the `audioura-*` containers
were never targeted or touched.

Setup: stood up `docker-compose.local742.yml`, applied `migration/sql/*` to the
throwaway DB, seeded `local742_owner` at level `l2`, created the "Salem"
community (id 1, `is_owner: true`) via the real `POST /communities`. Ran the app
on the simulator in local mode as `local742_owner` against the isolated user-api.
(For the simulator to reach the isolated user-api, a **temporary, uncommitted**
one-line local-port override and a throwaway harness entrypoint were used, then
both reverted/deleted — the committed source is unchanged apart from the three
feature files.)

Screenshots (`local742_shots/`):
- `01_community_page_owner.png` — the owner's Salem page with the purple
  **"+ Add a tour"** button near the top (plus "You are the organizer", invite
  tools, Step down, Delete — i.e. `is_owner: true`).
- `02_generator_salem_preselected.png` — the generator opened with
  `initialCommunityId: 1` (exactly what the button pushes) showing the "For:"
  selector preselected to **"For: my community Salem"** with **Members**
  selected and the members hint.

### Row counts (throwaway `local742` postgres — never production)
| table | before | after | delta | note |
|---|---|---|---|---|
| communities | 0 | 1 | +1 | the Salem test community |
| community_passes | 0 | 1 | +1 | Salem's $5/month pass |
| community_pass_products | 35 | 35 | 0 | migration catalog |
| community_memberships | 0 | 0 | 0 | — |
| device_entitlement | 1 | 2 | +1 | `local742_owner` → l2 |
| audio_tours | 0 | 0 | 0 | the two screens are read-only |
| users | 0 | 0 | 0 | — |

No deletes of any rows. No `DELETE FROM audio_tours` (D141). No purchase-bearing
rows removed (D690). The stack was torn down with `down -v` (throwaway DB gone);
`audioura-user-api-2-1` confirmed still running afterwards.

### Budget
**$0.00.** The feature is app-side navigation/preselect; no tour generation / AI
calls were made during the live test. (≤ $0.20 allowed.)

## Verify-not-reimplement
Point 4 (a tour finished for the community appears in its tour list) goes through
the existing `community_id` generate path (verified in LOCAL-701, unchanged here).
`_openAddTour` reloads the community page on return so a newly generated tour
surfaces; the generate body still carries `community_id` + `community_visibility`
via the unchanged `CommunityTourTarget.generateFields()`.

## Process
- Committed only the intended files (no `git add -A`). CocoaPods version bump in
  `ios/Podfile.lock` (a build side-effect) was reverted.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
- ClickUp status unchanged.
