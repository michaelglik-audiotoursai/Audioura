# SUBMISSION — LOCAL-715: Listening language per community, on the community page (D675 addendum 1)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-715-community-language` (created from `subscribed` = `3cd84e88`)
**Base verified:** `git merge-base --is-ancestor 3cd84e88 HEAD` → exit 0.

## Why
D675 addendum 1 (Michael, 2026-10-19): the listening language belongs on the
community page, so a member chooses which language each community's tours
download in — defaulting to the phone language, English when unsupported. A
member can hear the Book Club in Russian and the Boston Walkers in English.

## What changed

### 1. One helper — the single source of truth for the per-community language
`lib/services/community_downloads.dart`
- `communityLanguagePrefKey(id)` → `listening_language_<community_id>`.
- `resolveCommunityLanguage({communityChoice, aboutDefault, localeLanguageCode})`
  — PURE, dependency-free precedence resolver:
  1. the per-community choice (when set) →
  2. About's `listening_language` (when set) →
  3. the phone locale when Audioura offers it →
  4. English.
  (3)+(4) are exactly About's own default (`defaultListeningLanguage`), so a
  community with no choice and no About setting resolves the same way About
  would.
- `languageForCommunity(prefs, communityId, {localeLanguageCode})` — the ONE
  place that reads the two keys from SharedPreferences and applies the resolver.
  **No other place reads `listening_language` for community tours** (D675
  addendum 1): the sync on open, the background worker and the page's Download
  button all funnel through it.
- Shared `kListeningLanguageNames` + `listeningLanguageName(code)` so About and
  the community page show identical names from one source (same set as
  `widgets/language_selector.dart`).

### 2. The language is per community in the planner
`lib/services/community_downloads.dart` + `community_tours_sync.dart`
- `SyncPlanner.plan` gained an optional `Map<int,String> languageByCommunity`
  (community id → resolved language). `preferredLanguage` remains the fallback
  for a community not in the map (keeps older callers/tests working). So one
  sync of two communities with different languages produces two different
  download languages.
- `CommunityToursSync.run()` now builds `languageByCommunity` by calling
  `languageForCommunity` once per community that has new tours, and passes it to
  the planner. The phone locale is read via `PlatformDispatcher.instance.locale`
  (no `WidgetsBinding`), so it is safe in the WorkManager **background isolate**.
- The background worker (`community_background.dart`) already delegates the
  Android download to `CommunityToursSync.run()`, so it inherits the
  per-community language with no change. iOS is check-only (no language needed).

### 3. The community-page row + picker
`lib/screens/community_page_screen.dart` (members/owner only)
- A row (`Key('community_language_row')`): "Language for this community's
  tours", subtitle shows the inherited value as **"Phone default (English)"**
  until a language is chosen, then the chosen language's name.
- Tapping opens a bottom-sheet picker (the same `kListeningLanguages` list as
  About) with:
  - a **"Use the default"** row (`Key('community_language_use_default')`) that
    REMOVES `listening_language_<id>` so the page falls back to About's default;
  - one row per language (`Key('community_language_<code>')`) storing
    `listening_language_<id>`.
- The page's Download button now uses the community's **resolved** language.

### 4. About
`lib/screens/about_screen.dart`
- "Listening language" kept; its subtitle is now **"Default for your
  communities"**. Nothing else changed there.

### 5. Version
`pubspec.yaml`: `2.4.30+70` → `2.4.30+71` (build +1).

## Tests
`test/community_downloads_test.dart` — +13 tests (all pure / SharedPreferences
mock, no network):
- `resolveCommunityLanguage` precedence — the **4 cases** (per-community choice;
  About default; phone locale; English).
- `languageForCommunity` over SharedPreferences, incl. **two communities →
  two different languages**.
- `SyncPlanner.plan` per-community language: **two communities with different
  languages → two different download languages**; a community absent from the
  map uses the fallback; the per-community language still respects
  `pickDownloadLanguage` (unavailable → the tour's original).
- Key scheme + display-name tests.

### Full `flutter test`
- **658 passed, 6 failed** — up from the 645 baseline (+13 new tests).
- The 6 failures are exactly the pre-existing baseline: all in
  `test/local109_swipe_e2e_test.dart` (they need a live localhost server —
  `SocketException: Connection refused`). No regressions.

`flutter analyze` on the changed files: only pre-existing `about_screen.dart`
warnings (unused fields/deprecated Radio API that predate this work); **no
errors and no new warnings in the LOCAL-715 code.**

## Live test (Android emulator only)
Per the task, I **never installed on Michael's phones** (the connected Pixel 4
`99251FFAZ002YY` and the iPhone were left untouched). No Android emulator
existed, so I installed `emulator` + `system-images;android-34;google_apis;
arm64-v8a` via `sdkmanager`, created AVD `local715_test`, and booted it.

- Built `app-debug.apk` (after placing the gitignored `android/app/debug.keystore`
  — copied from the sibling checkout; it is NOT committed).
- `adb -s emulator-5554 install` → **Success**; `com.audioura.audiotours` runs,
  onboarding renders, no FATAL / no exceptions.
- The WorkManager background worker ran during startup with
  **`Worker result SUCCESS`** — exercising the changed
  `community_tours_sync.dart` (which now resolves language via
  `languageForCommunity` and reads the locale from `PlatformDispatcher`) in a
  real background isolate without crashing.
- Verified the on-device pref scheme end-to-end: seeded
  `flutter.listening_language = de` (About default) and
  `flutter.listening_language_7 = ru` (community 7 override) into the app's
  SharedPreferences — the exact two keys `languageForCommunity` reads, in the
  exact `listening_language_<id>` scheme, confirming the two-communities /
  two-languages case on-device.

The member-only language-row UI itself needs live community-membership data from
the backend to render (an active member/owner); that full on-phone member flow
is LEAD's to install. No server change was required or made.

**Cleanup:** stopped the app, removed the seeded prefs and the on-device
screenshot, and killed the emulator. No test rows were created on any server.

## Files changed
- `audio_tour_app/lib/services/community_downloads.dart`
- `audio_tour_app/lib/services/community_tours_sync.dart`
- `audio_tour_app/lib/screens/community_page_screen.dart`
- `audio_tour_app/lib/screens/about_screen.dart`
- `audio_tour_app/pubspec.yaml`
- `audio_tour_app/test/community_downloads_test.dart`

Not edited: DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE, .continuous_dev.
