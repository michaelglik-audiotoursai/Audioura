# SUBMISSION — LOCAL-757

**Community tours stand out on the Home map (green) and in search, before the listener taps**

- **Branch:** `LOCAL-757-community-tours-stand-out`
- **Base (code_sha):** `9a86e6e8e09a9002aa0e66a34ec774a2ddc0ba27` (`subscribed`, contains LOCAL-756)
- **Agent:** Mac Mini Kiro
- **Base verified:** `git merge-base --is-ancestor 9a86e6e8 HEAD` → exit 0.

---

## Why (Michael, 2026-10-24 ~14:15, iPhone, map near Salem)

> "The community's tours do NOT show the purple community sign, only the community
> itself does show 'Salem TV show funs'. When I click on the tours, they correctly
> identify that they are for Members only of Salem community. The text is small and
> does not take attention. Is it possible to have a green color for 'members' and
> 'community', so people would know before they click and then asked to join;
> otherwise, they may think that all tours are for community and we are just hassling
> money from them."

Confirmed live: `/tours-near` near Salem withholds the members-only community tours
(716/733/735, community 10) from a **non-member**, so on the shared server a non-member
only sees the community PIN, not its tours. The fix makes a community tour unmistakable
**the moment it does appear** — green marker + green chip — so joining is an informed
choice, not a surprise after the tap.

---

## What changed

### A. The map marker of a community tour is now green with the groups symbol (both marker paths)
`home_screen.dart` builds tour markers on TWO paths — the cached path
(`_loadCachedTours`, ~491) and the live `/tours-near` path (~814). Both now decide the
marker's look from ONE pure rule:

- `CommunityRules.homeMarkerKind(clusterTours)` → `'treat' | 'community' | 'multiple' | 'single'`
  (treat wins over community; a cluster holding **any** community tour is `'community'`).
- `homeMarkerColor(kind)` / `homeMarkerIcon(kind)` (in `community_tour_chip.dart`) map that
  to a colour + icon: **community → green (`kCommunityGreen`) + `Icons.groups`**; treat /
  multiple / single keep their exact pre-LOCAL-757 colour and icon.

A plain Audioura tour's marker is unchanged (blue walk / purple layers / orange cup). The
green multi-tour "apps" badge is suppressed on a community pin (it is already green + groups,
so the badge would be green-on-green). The LOCAL-690 **community PIN** is untouched and stays
visually distinct (deep-purple teardrop `Icons.location_on`, different shape from the circular
tour markers).

### B. One green `CommunityTourChip` on every Home tour surface, before the tap
New widget `audio_tour_app/lib/widgets/community_tour_chip.dart` — the SINGLE chip used by
every surface (no per-screen copies):

- Green, groups (👥) icon, 13-px bold. Label from the pure
  `CommunityRules.homeTourChipLabel(tour)`:
  - members-only → `Members only · <community name>`
  - public / listed community tour (D706) → `Community tour · <community name>`
- Light mode: solid green fill, white text. Dark mode: tinted green fill + light-green
  outline/text (contrast handled; see note on the app theme below).
- Returns `SizedBox.shrink()` for a plain Audioura tour, so no tour that is not a community
  tour ever shows it (nobody thinks every tour costs a membership).

Wired through the existing `_communitySign(tour)` helper (now returns the chip) at all three
chip surfaces, unchanged call sites:
- the List / search bottom-sheet row (`_showVisibleToursList`, ~701),
- the detail sheet (`_onTourMarkerTapped` dialog, ~1634),
- the multi-tour dialog (`_showMultipleTourDialog`, ~2324).

The LOCAL-756 **price line** is kept exactly as written ("Included with membership" /
"Members only — join <community>" / "Community tour — join to download") and recoloured from
deep-purple into the same green family (`kCommunityGreen`) so the chip and the price line read
as one colour language.

`communities_models.dart` stays Flutter-free (pure rules only); the colour/icon mapping and the
widget live in `community_tour_chip.dart`.

### Files
- `audio_tour_app/lib/services/communities_models.dart` — added `isMembersOnlyTour`,
  `homeTourChipLabel`, `clusterHasCommunityTour`, `homeMarkerKind` (pure).
- `audio_tour_app/lib/widgets/community_tour_chip.dart` — NEW: `CommunityTourChip`,
  `kCommunityGreen`/`kCommunityGreenLight`, `homeMarkerColor`, `homeMarkerIcon`.
- `audio_tour_app/lib/screens/home_screen.dart` — both marker paths use the shared rule;
  `_communitySign` returns the chip; price line recoloured green.
- `audio_tour_app/test/home_community_marker_chip_local757_test.dart` — NEW red tests.

---

## Tests

### Red test file (RED on `9a86e6e8`, GREEN after the fix)
`audio_tour_app/test/home_community_marker_chip_local757_test.dart` — 15 tests.

Proven RED at base: none of the symbols it imports/calls exist on `9a86e6e8` —
`grep -c` for `homeMarkerKind|homeTourChipLabel|isMembersOnlyTour|homeMarkerColor` in the
base `communities_models.dart` returns **0**, and
`audio_tour_app/lib/widgets/community_tour_chip.dart` **does not exist** at `9a86e6e8`
(`git cat-file -e 9a86e6e8:…` → "exists on disk, but not in '9a86e6e8'"). The test therefore
fails to compile/run on the base.

Coverage:
- **A (marker, both paths):** a community cluster is `'community'`, a plain single is
  `'single'`, a plain multi is `'multiple'`; a community tour mixed into a cluster still makes
  the pin `'community'`; a treat pin stays `'treat'`. The community marker **colour** differs
  from both plain colours and equals `kCommunityGreen`; the community **icon** is `Icons.groups`
  and differs from the plain walk icon. (Both marker paths share this rule, so one assertion
  covers both.)
- **B (chip):** label is `Members only · <name>` (members) / `Community tour · <name>`
  (public); the label always contains the community name; a plain tour has an empty label.
  Widget: shown (with name + groups icon) for members-only and for public community tours,
  **absent** for a plain tour, and renders without exception in dark mode.

### Results
- `flutter test test/home_community_marker_chip_local757_test.dart` → **15/15 pass**.
- Full suite: **1025 pass / 7 fail**.
- Pristine base (via `git stash` of all four changed/new files): **1010 pass / 7 fail**.
  The 7 are the documented known failures and are environmental (need a local server/gateway):
  6 in `local109_swipe_e2e_test.dart` (`SocketException: Connection refused`) + 1 in
  `storied_compat_screens_404_test.dart`. **Zero new failures** — the 15 added are all mine.

### Analyze
`flutter analyze` on the touched files is unchanged from baseline:
`home_screen.dart` still 300 issues (281 info, 19 warning, 0 error — all pre-existing, none in
the edited regions); `communities_models.dart`, `community_tour_chip.dart`, and the new test
file each **0 issues**. No new issues in touched files.

---

## Live test (iOS Simulator — never Michael's phones)

iPhone 17 simulator (iOS 26.4). A wirelessly-connected "Mikhail Glik's iPhone" was present and
deliberately **not** used. GPS set to Salem (42.5186, -70.8979). No DB writes. Budget $0.

1. **Shared server, read-only:** pointed at `https://api.audioura.com` (cloud). `/tours-near`
   near Salem returned HTTP 200 with the 4 plain "Salem Witchcraft Trails" tours only — the
   members-only community tours (716/733/735) are **withheld from a non-member**, exactly the
   gap Michael saw. Screenshot `04_shared_server_salem_readonly.png`.
2. **Community tours visible (fixture path, allowed by the ticket):** a local read-only
   map-delivery stack already running on `:5005` returns community tours of community 10
   "Salem TV show funs" (public visibility). Pointed the app at it (local mode, 127.0.0.1) to
   exercise the green marker + chip. Confirmed:
   - **Green community-tour marker with the groups icon, visibly distinct from the purple plain
     multi-tour marker**, on the live `/tours-near` marker path —
     `01_map_green_community_marker_vs_purple_plain_light.png`, zoom `02_map_markers_zoom_light.png`.
   - **Green chip "👥 Community tour · Salem TV show funs" + green price line
     "Community tour — join to download"** in the List/search surface —
     `03_list_green_community_chip_light.png`.

Screenshots are in `local757_screenshots/`.

### Honest notes
- **Theme:** the Home `MaterialApp` (`main.dart`) defines only one light `ThemeData` (no
  `darkTheme`/`themeMode`), so at runtime `Theme.of(context).brightness` is always light and the
  live chip always renders its light (solid-green / white-text) variant. The dark-mode branch of
  `CommunityTourChip` is therefore verified by the widget test ("renders in dark mode too"),
  not by a live screenshot — a live dark screenshot here would be misleading (the app has no
  dark theme).
- **Detail sheet & multi-tour dialog:** these render the *same* `_communitySign`
  (`CommunityTourChip`) and `_communityPriceLine` as the List row (identical call sites), and are
  covered by the widget tests. A pixel-perfect live screenshot of the detail sheet was not
  captured because the single compact list row's rating-badge tap target overlaps the row and
  the simulator GUI-automation kept opening the "Why this score" sheet instead; the List-row
  screenshot shows the identical chip + price line.
- The pre-existing local `:5005` Docker map server was **not** started or modified by me and was
  left running as found; no DB writes were made on any server.

---

## Process
- Committed only the four feature files + `local757_screenshots/` (no `git add -A`). An incidental
  CocoaPods version bump in `ios/Podfile.lock` from the local build was reverted, not committed.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
- Simulator shut down; app prefs restored to cloud mode after the test.
