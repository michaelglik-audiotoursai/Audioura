# SUBMISSION — LOCAL-760: organiser-audio tours on the phone (round 2)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-760-organiser-audio-round2`
**Base (code_sha):** `127cd384` (subscribed — LOCAL-759 + LEAD's `/tour/<id>/resolve` fix)
`git merge-base --is-ancestor 127cd384 HEAD` → exit 0 (correct base).

Michael, 2026-10-24 (~19:30), tour 750 "The Salem Witch Trial" (organiser audio,
community 10), both phones. Downloads now succeed (LEAD fixed resolve). This
round fixes the four remaining issues.

---

## What was wrong and what now happens

### 1. The download status flashed
`_downloadCommunityTour` showed each progress tick as a fresh SnackBar
(`clearSnackBars()` + `showSnackBar()`), so the line appeared, disappeared and
reappeared on every byte update.

**Now:** ONE persistent banner (`DownloadProgressBanner`, driven by
`DownloadProgressController`) stays mounted for the whole download — a
`LinearProgressIndicator`, the shared `downloadingAudioLabel` line ("Downloading
audio — stop 2 of 3 · 45 / 81 MB") and a Cancel. It is **not** a SnackBar, so
nothing clears/re-shows it; it disappears only on success, cancel or the named
failure. The Home path never wired per-stop progress, so it never flashed — the
community page was the only surface with the bug.

### 2. Edit and Translate were still offered on a broadcast tour
Pressing Edit let the user work for a long time, then Save failed ("This tour is
maintained on the organiser's own site…"). Root cause: `communityTourSourceItem`
did not carry `source_kind`, so a member's download record had **no**
`source_kind='organiser_audio'` and the menu stayed enabled.

**Now:**
* The saved record is stamped at download (`communityTourSourceItem` carries
  `source_kind`; the community listing emits it, `CommunityInviteTourOption`
  parses it).
* Records already on the phone are repaired (`stampSourceKindOnSavedRecords`,
  run on community-page load for every organiser-audio tour in the community;
  `isOrganiserAudioFromFiles` recognises a tour folder by its `remote_audio.json`).
* On Listen (`⋮`) Edit and Translate are shown **disabled** (grey, with an ⓘ)
  for a broadcast tour and the edit screen is **never opened**. Tapping shows:
  * Edit — "Editing is not available for broadcast tours. This tour is
    maintained on the organiser's own site; the organiser updates it there."
    (owner also: "Change it in \"Make a tour from your own audio\" on the
    community page." + an **Open in audio-tour builder** button).
  * Translate — "Translation is not available for broadcast tours: the audio
    belongs to the organiser (D708)."
  A generated / ordinary tour keeps the live Edit/Translate. The server 409/403
  stay as the backstop.

### 3. The translation message was misleading
A server 403 `translation_not_offered` showed "Russian wasn't available for this
older tour, so the English version was saved."

**Now:** `TranslationService.translateTour` carries the server `error_code`
through; `TourTranslationHelper.lastTranslationNotOffered` records the 403; both
message sites (`my_tours_screen`, `home_screen`) use the shared
`translationFailureMessage`, which maps `translation_not_offered` → the D708
broadcast text and keeps the original "older tour" wording for the per-language
fallback it was written for.

### 4. The organiser could not reopen the tour and tell members
`OrganiserAudioTourScreen` took `editTourId` + `notify_members` but nothing
opened it for an existing tour and it did not prefill.

**Now:**
* NEW owner-only `GET /communities/<id>/audio-tours/<tour_id>` returns
  `{tour_name, tour_type, visibility, source_kind, stops:[…]}`, the stops rebuilt
  from the stored package (`parse_stops_from_package` — the inverse of
  `build_package`). A member gets 403; a non-organiser-audio tour 409; no row 404.
* Community page (owner only), on a broadcast tour row: an **Edit audio tour**
  action opens the builder **prefilled** from that endpoint. Translate is
  suppressed on broadcast rows (D708).
* From Listen, the owner's disabled-Edit ⓘ offers **Open in audio-tour builder**
  (fetches the `Community`, pushes the builder with `editTourId`).
* The builder's "I changed this tour — tell my members" checkbox (LOCAL-755) is
  shown in edit mode; Save with it ticked bumps the version → members see
  "Updated by the organiser — Re-download" (opt-in, never pushed); unticked is a
  silent save.

---

## Files changed

### App (`audio_tour_app/`)
| File | Change |
|---|---|
| `lib/widgets/download_progress_banner.dart` | **NEW** — `DownloadProgressController` + `DownloadProgressBanner` (one persistent bar, not a SnackBar). |
| `lib/utils/organiser_audio_notices.dart` | **NEW** — pure `editDisabledNotice`, `translateDisabledNotice`, `translationFailureMessage`. |
| `lib/services/community_downloads.dart` | `communityTourSourceItem` carries `sourceKind`; new `isOrganiserAudioFromFiles`, `stampSourceKindOnSavedRecords`. |
| `lib/services/communities_models.dart` | `CommunityInviteTourOption.sourceKind` + `isOrganiserAudio`; new `AudioTourStop`, `AudioTourDetail`. |
| `lib/services/communities_service.dart` | new `audioTourDetail(communityId, tourId, userId)`. |
| `lib/services/translation_service.dart` | non-200 carries `status_code` + `error_code`. |
| `lib/services/tour_translation_helper.dart` | `lastTranslationNotOffered` flag; short-circuits on 403 `translation_not_offered`. |
| `lib/screens/community_page_screen.dart` | persistent banner in the body + wired into `_downloadCommunityTour`; `sourceKind` into the source item; source_kind repair on load; owner "Edit audio tour" row; Translate suppressed on broadcast rows. |
| `lib/screens/my_tours_screen.dart` | Edit/Translate shown disabled with ⓘ for broadcast tours; owner "Open in audio-tour builder"; `translationFailureMessage`. |
| `lib/screens/home_screen.dart` | `translationFailureMessage` on the translate-failure dialog. |
| `lib/screens/organiser_audio_tour_screen.dart` | `_prefillFromServer()` seeds name/type/visibility/stops when `editTourId` is set. |

### Server (`user-tracking/`)
| File | Change |
|---|---|
| `organiser_audio_tours.py` | new pure `parse_stops_from_package`, `tour_type_from_stops`, `_parse_stop_text_block` (inverse of `build_package`). |
| `communities_api.py` | new owner-only `GET /communities/<id>/audio-tours/<tour_id>`; `_tours_for` now emits `source_kind`. |

No NEW Python module — `organiser_audio_tours.py` already existed (LOCAL-754B);
only functions were added, so no Dockerfile change is required.

---

## Red tests first (all now green)

**Flutter** (`audio_tour_app/test/`):
* `download_progress_banner_local760_test.dart` — one persistent bar across 20
  ticks, never a SnackBar, Cancel wired, disappears on `finish()`.
* `organiser_audio_notices_local760_test.dart` — the exact Edit/Translate ⓘ text
  (owner vs member) and the `translation_not_offered` → D708 mapping (older-tour
  kept for its case).
* `source_kind_stamp_local760_test.dart` — `communityTourSourceItem(sourceKind:)`,
  `isOrganiserAudioFromFiles`, `stampSourceKindOnSavedRecords`.

**Python** (`tests/`):
* `test_local760_audio_tour_detail.py` — `parse_stops_from_package` round-trip
  (located + unlocated + garbage), and the owner-only GET (owner 200 with stops /
  member 403 / non-organiser-audio 404-or-409).

Each suite was confirmed RED on `127cd384` before the code existed.

---

## Test results

* **Python touched suites:** `test_local760_audio_tour_detail.py` +
  `test_local754b_translation_refusal.py` + `test_local754b_organiser_audio.py` +
  `test_local755_organiser_audio_updates.py` → **29 passed**.
* **Flutter full suite:** **1078 passed, 7 failed**. The 7 are exactly the
  pre-existing baseline failures that need a live backend/gateway
  (6× `local109_swipe_e2e_test.dart` — `SocketException: Connection refused` to
  localhost; 1× `storied_compat_screens_404_test.dart` — needs a storied gateway).
  None touch the files in this change; **no new failures**.
* `flutter analyze` on every touched file → **no errors** (only pre-existing
  info/warning lints).

---

## Live test (simulator + test DB only, budget $0.00)

`live_local760.py` runs the REAL round-2 server surface against the TEST database
(`audiotours_test`, port 5433) with its own local 3-MP3 HTTP feed, `is_test`
rows, and cleanup back to baseline. **No OpenAI / no AI — $0.00.**

```
[rows] before: {'audio_tours': 0, 'community_episodes': 0, 'communities': 1}
[build] owner published tour_id=7779 source_kind=organiser_audio stops=3 ✓
[GET]  owner reopened tour PREFILLED: name="River Walk …" type=walking
       visibility=members stops=['Town Square','Old Mill','River Bend'] ✓
[GET owner-only] member refused 403 ✓
[parse] stored ZIP → 3 stops, every field recovered ✓
[edit silent] no checkbox → version stays 1 ✓
[edit notify] checkbox → version bumped to 2 (members offered Re-download) ✓
[rows] after:  {'audio_tours': 1, 'community_episodes': 0, 'communities': 2}
[rows] delta:  audio_tours +1, communities +1
[cleanup] removed this run's test rows → counts back to {'audio_tours': 0, ...}
LOCAL-760 LIVE: ALL CHECKS PASSED ✓   (final == before asserted)
```

**Row counts before/after** (test DB): `audio_tours 0 → 1 → 0`,
`communities 1 → 2 → 1` — every row created was `is_test=true` and removed in
cleanup (D141); no purchase-bearing rows touched (D690). **Tour 750 was never
read or modified** — the live test uses its own `is_test` community/tour.

**App on the simulator:** `flutter build ios --simulator --debug` → built
`Runner.app` (Xcode build done, 58 s). Installed and launched on the iPhone 17
simulator (`com.audioura.audiotours`), rendered the onboarding screen
(`local760_screenshots/01_app_launch.png`). The simulator was shut down
afterwards (no booted devices).

**Screenshots:** `local760_screenshots/01_app_launch.png` proves the built app
with these changes runs on-device. The specific in-app screens (persistent
banner, disabled Edit/Translate ⓘ dialogs, prefilled builder, member
Re-download) are each proven by a widget test that renders the real production
widget and asserts the exact strings/keys, plus the live server E2E above for the
owner-reopen/notify path; interactive navigation to those screens on a running
backend was not scriptable in this environment without an integration-test
harness.

---

## Process notes
* Committed to `LOCAL-760-organiser-audio-round2` with explicit paths (never
  `git add -A`); `Podfile.lock` (touched by `pod install` during the build) was
  restored and NOT committed.
* No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD or `legal/`.
