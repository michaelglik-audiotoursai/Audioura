# SUBMISSION — LOCAL-709: Tour share links (D671)

**Branch:** `LOCAL-709-tour-share-links` (from `subscribed` = `859b92e4`)
**Agent:** Mac Mini Kiro
**App version:** `2.4.24+61` → `2.4.25+62`

## What this delivers (D671)

A tour/community code in an email is now a link: `https://audioura.com/t/<CODE>`.

- **App installed** → the OS opens Audioura straight to **Home → Search** with the
  code filled in and the search already run, via the **same code path a pasted
  code takes** (`classifySearchInput` → share-code branch → `_resolveShareCode`).
  No second resolver. Paid tours still follow the normal paid flow (D660: a link
  never grants a download).
- **App not installed** → a static landing page on `audioura.com/t/` appeals to
  the visitor and sends them to the right store, carrying the code so the app
  picks it up after install (Android Install Referrer; iOS clipboard).

## 1. Link builder — one place (`lib/utils/share_code.dart`)

- `buildShareLink(code, tourName)` → `https://audioura.com/t/<CODE>?n=<Uri.encodeQueryComponent(name)>`.
  `n` is for the landing page headline only; the app ignores it.
- `buildShareMessage` now leads with the link (D671 §5):
  `Listen to my Audioura tour "<name>": https://audioura.com/t/<CODE>  (or open Audioura, tap Search and paste <CODE>)`.
- `buildCommunityInviteLink(code)` / `buildCommunityInviteMessage(name, code)` —
  community invites ride the **same** `/t/` link (the app's share-code branch
  resolves a `/t/` code as tour-first, then community; the landing page copies
  the code regardless).
- `extractShareCode` still returns the CODE for: the new message, a bare link, a
  link with `?n=`, and a link with a **trailing slash** (it now scans every path
  segment, so an empty final segment from a trailing slash doesn't hide the code).

**Every generated code text routed through the builder:**
- `widgets/share_tour_sheet.dart` — already calls `buildShareMessage` (now links).
- `services/communities_models.dart` `CommunityCopy.emailInviteBody` — now leads
  with `buildCommunityInviteLink`, keeps the `installUrl` line and the code.
- `screens/communities_about_screen.dart` — the local `_inviteMessage` fallback
  now uses `buildCommunityInviteMessage`.

## 2. Incoming links (`lib/services/deep_link_service.dart`)

- Package: **`app_links: 6.4.1`** (pinned — newest version whose SDK constraint
  stays at this project's Dart 3.5 floor; 7.x needs 3.10+). Same floor-protection
  rationale as `share_plus`.
- `DeepLinkService.codeFromUri(Uri)` — **pure**: https/http, host `audioura.com`
  (or `www.`), first segment `t`, next a valid code shape → the code; **a non-`/t/`
  path returns null** (home/legal pages never trigger a search).
- `PendingShareSearch` — a `ValueNotifier<String?>` where a code is parked;
  `main.dart` inits the service (cold + warm start), `main_screen.dart` switches
  to the Home tab when a code arrives, and `home_screen.dart` consumes it and runs
  `_dispatchSearch(code)` — the single shared path.
- **Android:** `AndroidManifest.xml` gets `<intent-filter android:autoVerify="true">`
  for VIEW/BROWSABLE, https, host `audioura.com`, `pathPrefix="/t/"`.
- **iOS:** `Runner/Runner.entitlements` (new) sets
  `com.apple.developer.associated-domains = applinks:audioura.com`, and
  `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements` is added to **all three**
  app build configs (Debug, Release, Profile) in `project.pbxproj`.

## 3. Deferred link after install (D671 §4) — true one-shot

`DeepLinkService.runDeferredCheckOnce(...)` runs **once, ever** (guarded by the
SharedPreferences flag `deferred_share_link_checked_v1`, written *before* any work
so a partial run still spends the shot):

- **Android:** Play Install Referrer (`android_play_install_referrer: 0.4.0`,
  pinned — the last version under the 3.5 floor; the successor `play_install_referrer`
  needs Dart 3.7. It is discontinued upstream but API-stable and Android-only).
  Reads `audioura_code=<CODE>` from the referrer and runs the search (no prompt).
- **iOS:** `Clipboard.hasStrings` is checked **first** (nothing there → **no paste
  prompt**); if the clipboard holds a code-shaped string, one dialog "Open the
  tour you were sent?" (Open / Not now), then never again either way.

The referrer/clipboard reads and the prompt are injected, so the one-shot is
unit-tested with no plugins.

## 4. Website (`website/`, repo-only — Michael/LEAD publish)

- `.well-known/apple-app-site-association` — JSON, no extension, appID
  `4HGRU6TKGQ.com.audioura.audiotours`, components `/t/*`.
- `.well-known/assetlinks.json` — package `com.audioura.audiotours`, two
  fingerprints:
  1. **`E6:2F:E3:27:9B:67:F4:79:BD:78:6A:DD:0E:CC:9A:44:0E:61:46:3E:1A:E8:00:33:14:D9:F4:D5:C8:46:62:28`**
     — the **real** SHA-256 of the keystore that signs our release APK today. There
     is no `key.properties`, so `build.gradle.kts` signs release with the project
     debug keystore (`audio_tour_app/android/app/debug.keystore`). Verified against
     the APK I built: `apksigner verify --print-certs app-release.apk` →
     `Signer #1 certificate SHA-256 digest: e62fe327…66228`.
  2. **`PLAY_APP_SIGNING_SHA256_FROM_PLAY_CONSOLE`** — placeholder for Michael:
     Play Console → Test and release → App integrity → App signing (documented in
     `website/README.md`).
- `t/index.html` — self-contained (no external scripts/fonts/tracking). Reads CODE
  from the path and `n` from the query; tour name inserted as **text, never HTML**
  (XSS-safe); appeal paragraph; code + Copy; platform store button(s) (both on
  desktop). The store button copies the code then goes to the store; the Android
  URL carries `&referrer=audioura_code%3D<CODE>`. Store URLs are in ONE constant
  block; while empty the button reads **"Coming soon to Google Play / the App
  Store"** and is disabled (both listings 404 on 2026-10-18). Works at 360px.
- `_redirects` (`/t/*  /t/index.html  200`), `_headers` (both `.well-known` served
  as `application/json`), `README.md` (file purposes + exact Cloudflare Pages
  upload steps + the two things to fill in at release).
- `screenshots/landing_390px.png`, `landing_1280px.png`.

**Publish whitelist:** the legal pages use `legal/build_html.py` (a route map,
with "nothing here is published"), **not** a whitelist, so per the task `website/`
was **not** added to any whitelist.

## Tests

- **Dart (`test/share_code_test.dart`, `test/deep_link_service_test.dart`):**
  - `buildShareLink` encoding of a name with quotes, `&`, accents (spec uses
    `Uri.encodeQueryComponent`, which form-encodes spaces as `+`; the landing
    page's `URLSearchParams` decodes `+` back to a space).
  - `extractShareCode` on the new message, bare link, `?n=` link, trailing-slash
    link; a code-shaped `?n=` value does **not** override the path code.
  - `codeFromUri` maps `/t/<CODE>` to the same `shareCode` dispatch a pasted code
    takes; a non-`/t/` path / foreign host / non-code segment is ignored.
  - `codeFromInstallReferrer` pulls `audioura_code=<CODE>`; rejects junk.
  - The deferred one-shot: runs once, never twice (Android referrer + iOS
    clipboard Yes/No + empty-clipboard-no-prompt).
- **JS (`website/tests/landing_page.test.js`):** evaluates the page's actual
  `<script>` in a Node vm — path→code, `n`→text, the Android referrer URL, and the
  empty-URL "Coming soon" disabled state.
- `python3 -m json.tool` — both `.well-known` files valid.
- `flutter analyze` — **clean for the changed files** (no new issues; the only
  lints are pre-existing `avoid_print` in `main.dart`, a pre-existing
  `unused_import`, and the test's pre-existing relative-import style).
- **Full `flutter test` vs baseline:**
  - Baseline `@859b92e4`: **526 passed / 6 failed** — all 6 in
    `local109_swipe_e2e_test.dart` (require a live backend at `localhost:5102`;
    `SocketException: Connection refused`).
  - This branch: **551 passed / 6 failed** — the **same 6** server-dependent
    tests. **No new failures;** +25 net new passing tests.

## Live test

- **Release APK built** with the gateway key exactly as the project does:
  `flutter build apk --release --dart-define=GATEWAY_API_KEY="$GATEWAY_API_KEY"`
  → `build/app/outputs/flutter-apk/app-release.apk` (64.9 MB), then
  `./gradlew --stop`. Not installed on any phone. (The project debug keystore was
  copied into the worktree only to sign the build, then removed; it is gitignored.)
- **adb VIEW-intent test: not run — no emulator or Pixel-4 attached** (`adb` not
  present / no device). Note from D671 §2: domain verification would fail anyway
  until the website is published, so an attached-device test would show the
  browser/landing-page fallback, not in-app open, until then.
- **Landing page** previewed via `python3 -m http.server` and screenshotted at
  390px and 1280px (committed). At preview time the code resolves from the `#`
  fallback; `codeFromPath` ignores a dotted `index.html` segment so the preview
  mirrors production (where `_redirects` yields a clean `/t/<CODE>`).

## Notes / scope

- No server change. Only read access to the shared server would be needed for a
  real search; none was required for these tests.
- iOS `Runner.entitlements` is wired via the `CODE_SIGN_ENTITLEMENTS` build
  setting (the signing-relevant path). It is intentionally **not** added as a
  PBXFileReference to avoid hand-editing the project file's object graph; Xcode
  picks it up from the build setting.
- Did not touch DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE, `.continuous_dev`.
- The desktop `generated_plugin_registrant` files and `pubspec.lock` changed
  automatically from `flutter pub get` when the two plugins were added.

## Files

**App (modified):** `lib/utils/share_code.dart`, `lib/services/communities_models.dart`,
`lib/screens/communities_about_screen.dart`, `lib/screens/home_screen.dart`,
`lib/screens/main_screen.dart`, `lib/main.dart`, `pubspec.yaml`, `pubspec.lock`,
`android/app/src/main/AndroidManifest.xml`, `ios/Runner.xcodeproj/project.pbxproj`,
`test/share_code_test.dart`, desktop `generated_plugin_registrant`/`generated_plugins`.
**App (new):** `lib/services/deep_link_service.dart`, `ios/Runner/Runner.entitlements`,
`test/deep_link_service_test.dart`.
**Website (new):** `website/.well-known/apple-app-site-association`,
`website/.well-known/assetlinks.json`, `website/t/index.html`, `website/_redirects`,
`website/_headers`, `website/README.md`, `website/tests/landing_page.test.js`,
`website/screenshots/landing_390px.png`, `website/screenshots/landing_1280px.png`.

---

## 709B — LEAD review fixes (D671)

LEAD reviewed LOCAL-709 at `fb679dc2`. Links, landing page and tests were good;
two defects blocked the merge. Both are fixed on this branch
(`LOCAL-709-tour-share-links`, continued from origin, base `subscribed` =
`859b92e4`).

### Fix 1 — no unexplained paste prompt on an existing user's update

**Problem.** `runDeferredCheckOnce` fires on the first launch after an UPDATE
(not only after a fresh install) because the one-shot flag
`deferred_share_link_checked_v1` is new in this release — absent for everyone
updating. On iOS 16+ its clipboard read pops the system "Allow Paste" prompt;
on Android 12+ the clipboard branch (which also ran when the referrer was empty)
shows a "pasted from your clipboard" toast. So Michael and every tester would
get one unexplained prompt.

**Change (two parts, `lib/services/deep_link_service.dart`):**

1. **Existing-install guard in `DeepLinkService.init()`** (runs in `main()` at
   startup, before onboarding or the deferred check can fire). If the one-shot
   flag is absent AND this is an existing install, init silently sets the flag
   to `true` and does nothing else. The existing-install signal is
   `onboarding_complete` (`kExistingInstallSignalKey`): the app has always
   written it when the user finishes first-launch onboarding, so it is **absent
   on a fresh install at init time** (init runs before any screen) and
   **present on every install old enough to have completed onboarding**. `init`
   now takes an optional `prefs` for testing. Fresh installs (signal absent)
   keep the current one-shot behaviour untouched.
2. **Clipboard branch is iOS-only** in `runDeferredCheckOnce`: after the Android
   Install Referrer yields nothing, the clipboard path runs only when
   `defaultTargetPlatform == TargetPlatform.iOS`. On Android only the Install
   Referrer is read — the clipboard is never touched. A `platform` parameter
   (default `defaultTargetPlatform`) is injected so the iOS branch is testable
   without a device.

### Fix 2 — assetlinks.json holds only real fingerprints

**Problem.** `website/.well-known/assetlinks.json` carried a non-hex placeholder
(`"PLAY_APP_SIGNING_SHA256_FROM_PLAY_CONSOLE"`) as a second fingerprint; a
malformed fingerprint risks Android rejecting the whole statement.

**Change.** Removed the placeholder — the file now lists only the real
`E6:2F:…:62:28` fingerprint. `website/README.md` now instructs Michael to add
the Play App Signing SHA-256 as a **second array entry** in colon-hex format
before uploading, and shows the exact resulting JSON shape with `<PASTE HERE>`
(in the README only; never committed into `assetlinks.json`).

### Version

`audio_tour_app/pubspec.yaml`: `2.4.25+62` → `2.4.25+63` (build +1).

### Verification

- **Deep-link tests** (`flutter test test/deep_link_service_test.dart`): 19/19
  pass, including the new cases:
  - Existing install (`onboarding_complete` present, flag absent) → `init` sets
    the flag; the referrer and clipboard readers are never called afterward.
  - Fresh install → one-shot behaviour unchanged (referrer still read once).
  - Android with an empty referrer → the clipboard reader is never called and
    no prompt is shown; the one shot is still spent.
  - The three pre-existing iOS clipboard tests now inject
    `platform: TargetPlatform.iOS`.
- **assetlinks.json**: `python3 -m json.tool` passes; every fingerprint matches
  `^([0-9A-F]{2}:){31}[0-9A-F]{2}$` (1 fingerprint, matched).
- **`flutter analyze`** on the changed Dart files
  (`lib/services/deep_link_service.dart`, `test/deep_link_service_test.dart`):
  "No issues found!".
- **Full `flutter test`**: 554 pass, 6 fail — the same baseline failures only,
  all in `test/local109_swipe_e2e_test.dart` (`SocketException: Connection
  refused`, require a live server unavailable in this environment); unrelated to
  these changes.

### Files changed (709B)

`audio_tour_app/lib/services/deep_link_service.dart`,
`audio_tour_app/test/deep_link_service_test.dart`,
`audio_tour_app/pubspec.yaml`, `website/.well-known/assetlinks.json`,
`website/README.md`.
