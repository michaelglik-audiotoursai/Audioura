# SUBMISSION — LOCAL-739: One "Communities" page (C0)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-739-communities-hub`
**Base:** `subscribed` @ `54cb87c7` (verified `git merge-base --is-ancestor 54cb87c7 HEAD` → exit 0)
**code_sha:** `17ca62de04e9cf5b0343ad28ffda6971c0abd96f`

---

## Why (Michael's C0 ruling, review 2026-10-22)
A listener had no visible way back to a community they joined — the list hid
behind a small icon in the Listen app bar (`my_tours_screen.dart` ~1887,
`MyCommunitiesScreen`). Ruling: **one page**, reached from where people look;
non-members see it only from About.

## What shipped

### 1. One "Communities" page — `lib/screens/communities_hub_screen.dart` (new)
`CommunitiesHubScreen`, with the four parts, reusing existing pieces (no second
copy of any list):
1. **Your communities** — the communities the user **belongs to OR organises**,
   merged into one de-duplicated list (`YourCommunity.merge`): organiser rows
   first ("You are the organizer"), then member rows with their status/expiry
   via the shared `JoinedCommunitySubtitle` ("Member until …"). A community the
   user both owns and holds a pass in shows once, as an organiser row that keeps
   its expiry line. Tap → the community page (`CommunityPageScreen`).
2. **Join with a code** — a code box using the SAME resolver as the Home search
   (`CommunitiesService.resolveByCode`).
3. **Start a community** — opens the LOCAL-738 create form
   (`CreateCommunityScreen`).
4. **About communities** — the explanation (`CommunitiesAboutScreen`,
   `CommunityCopy`), behind a link at the bottom.

Keys for tests: `hub_your_communities_header`, `hub_your_communities_empty`,
`hub_community_<id>`, `hub_organizer_subtitle`, `hub_about_communities`.

### 2. Entry points
- **About tab** (`about_screen.dart`): the button now reads **"Communities"**
  (was "About Communities") and opens the hub — **for everyone**. (Removed the
  now-unused `CommunitiesAboutScreen` import.)
- **Members/organisers ONLY** (non-members see none of the three):
  - **Home map** (`home_screen.dart`): a "My communities" `ActionChip`
    (`Key('home_my_communities_chip')`), gated on `_isCommunityMember`.
  - **Generate tab** (`tour_generator_screen.dart`): a "My communities"
    `TextButton` (`Key('generate_my_communities_link')`), gated on
    `_isCommunityMember`, placed above the organiser-only "For:" selector.
    Generate → Community (the create form) is unchanged and open to everyone.
  - **Listen tab** (`my_tours_screen.dart`): the hidden app-bar icon is
    **removed**; a VISIBLE row **"My communities (N)"**
    (`Key('listen_my_communities_row')`) now sits at the top of the tours view,
    shown only when the count > 0. (Removed the now-unused `MyCommunitiesScreen`
    import.)

The members-flag is a single rule, `CommunityRules.hasAnyCommunity` — a member
(`/communities/mine`) OR an organiser (`/communities/mine-owned`) qualifies.

### 3. Members-only tour → join → download → Listen
When a NON-MEMBER taps Download on a members-only community tour (on Home, or
opened from an emailed link), the server's `402 membership_required` now shows
the gate **"This tour is for members of &lt;community&gt;"** with **Join**
(`home_screen._showMembersOnlyTourGate`). Join opens the community page carrying
the tour id (`CommunityPageScreen(pendingDownloadTourId:)`). After the pass is
granted (free join or pass purchase), `_maybeDownloadPendingTour()` downloads
that exact tour via `TourDownloadService.downloadAndSave` and opens the Listen
tab on it through `PendingListenOpen.offer(...)` — the SAME after-download
behaviour as any other download.

### Pure, testable helpers (`lib/services/communities_models.dart`)
- `CommunityRules.hasAnyCommunity({joinedCount, ownedCount})`
- `CommunityRules.membersOnlyTourGate(communityName)`
- `CommunityRules.yourCommunitiesCount({joinedIds, ownedIds})` (distinct)
- `YourCommunity.merge({joined, owned})` + `OwnedCommunityRef`
- `ListenMyCommunitiesRow` extracted (in the hub file) so the row's
  members-only visibility is widget-tested offline.

## Tests — `test/communities_hub_local739_test.dart` (new, 14 tests, all pass)
- Non-member vs member: the members-only widgets render only for a member
  (the hub shows for everyone; the Listen row / chip / link are count-gated).
- **RED test:** `ListenMyCommunitiesRow` is **hidden for a non-member (count 0)**
  and **shown for a member (count > 0)**. Verified it genuinely fails
  (`+11 -1`) when the count gate is removed, then reverted.
- Download-after-pass → Listen: `PendingListenOpen.offer(tourId)` arms a
  Listen-open request carrying that tour id — the exact mechanism
  `CommunityPageScreen._maybeDownloadPendingTour` uses after a granted pass.
- Unit: `hasAnyCommunity`, `membersOnlyTourGate`, `yourCommunitiesCount`,
  `YourCommunity.merge` (organiser-first ordering, de-duplication).
- Widget: `CommunitiesHubScreen` shows the four sections + the empty
  Your-communities state.

### Verification
- `flutter analyze`: **1377 issues** — identical to the pre-change baseline
  (77 errors / 70 warnings unchanged). **No new issues.** The new hub file
  analyzes clean.
- `flutter test` (full suite): **889 passed, 7 failed**. The 7 failures are
  ONLY in `test/local109_swipe_e2e_test.dart` (`SocketException: Connection
  refused` — it requires a live local server). Confirmed identical failures on
  the clean base (`git stash` → same `+6 -6`), so the **baseline Flutter
  failures are unchanged**. All community/widget suites pass (92).

## Live test
Not run in this environment: no simulator/emulator or `-p local739` container
stack was available to the agent, so **no screenshots or row-count deltas were
produced**. No database rows were touched; no `DELETE FROM audio_tours`, no
deletes of purchase-bearing rows (D690). Budget used: **$0.00**.

The behaviour is covered by the offline widget/unit tests above (including the
required red test and the download-after-pass → Listen contract). A live pass on
a simulator with the `-p local739` stack is the remaining manual step.

## Process
- Committed to `LOCAL-739-communities-hub` with an explicit file list (no
  `git add -A`).
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
  `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD or `legal/`.
- Did not change ClickUp status.

### Files
- `audio_tour_app/lib/screens/communities_hub_screen.dart` (new)
- `audio_tour_app/test/communities_hub_local739_test.dart` (new)
- `audio_tour_app/lib/services/communities_models.dart`
- `audio_tour_app/lib/screens/about_screen.dart`
- `audio_tour_app/lib/screens/home_screen.dart`
- `audio_tour_app/lib/screens/tour_generator_screen.dart`
- `audio_tour_app/lib/screens/my_tours_screen.dart`
- `audio_tour_app/lib/screens/community_page_screen.dart`
