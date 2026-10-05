# SUBMISSION — LOCAL-579: Mobile share-a-tour-by-code (Phase 1, ST-4)

**Branch:** `LOCAL-579-share-button`  **Base:** `subscribed` (2487d13)
**Agent:** Mac Mini Kiro (Flutter)  **ClickUp:** "Share a tour by code — Phase 1" (wdvrdaykja)

## What Michael asked
> "Can you enhance Mobile to get from the Tour and place in the Home page search
> link/Tour ID to share the tour by the curator?"

The server side (ST-1/ST-2) and the Home-search *receiving* side (ST-3) already
existed. What was missing: nothing in `lib/` called `POST /tour/share`, so a
curator had no way to *get* the code. This task adds the sending side and
teaches the receiver to accept the whole shared message, not just a bare code.

## What I built

### 1. Share action on a tour the listener has
- **My Tours** (`lib/screens/my_tours_screen.dart`): a new **Share** item at the
  top of each tour's ⋮ menu (`_shareTour(tour)`), using `tour['tour_id']`.
- **Tour player** (`lib/screens/tour_player_screen.dart`): a Share icon in the
  AppBar (`_shareTour()`), using `widget.tourId`. My Tours now passes `tourId`
  into the player so in-player sharing has the id.
- Both call one entry point, `shareTour(context, audioTourId:, tourName:)` in
  `lib/widgets/share_tour_sheet.dart`.

### 2. The service — `lib/services/tour_share_service.dart`
`TourShareService.share(audioTourId)` → `ShareResult`.
- Calls `POST /tour/share {"audio_tour_id": N}` through the existing `Endpoints`
  config and auth headers (new `Service.generator`, port 5000 local, cloud path
  `/generator`, marked protected so cloud carries X-API-Key + attestation like
  the orchestrator). The server derives location/type/stops/text from the
  `audio_tours` row, so the app sends **one integer**, never re-uploads text.
- Idempotent per tour (same tour → same 8-char code).

### 3. The result sheet — `lib/widgets/share_tour_sheet.dart`
A bottom sheet with: the **8-char code, large and selectable**; **Copy code**;
and **Share…** via the OS share sheet (`share_plus`, with an iPad anchor
rectangle). The shared text is exactly:
> Listen to my Audioura tour "<tour name>". Open Audioura, tap Search on the
> Home page and paste this code: <CODE>

No email integration (ST-5 explicitly NOT needed, per Michael).

### 4. Paste-friendly receiving — `lib/utils/share_code.dart`
`extractShareCode()` pulls the 8-char token out of a bare code, the full share
message, a share link (`…/tour/<CODE>`), or any of those with surrounding
whitespace. It reuses ST-3's discriminator (8 base62 chars **with a digit or an
internal capital**), so a place name like "Boston", "Newton MA", "Brooklyn" or
"Portland" is never mistaken for a code and falls through to a location search.
`home_screen.dart` `_looksLikeShareCode` now delegates to it, and `_searchTours`
extracts the token before resolving — the only functional change on the
receiving side.

### 5. Errors
- Offline / timeout / 5xx → a plain, non-crashing message (SnackBar).
- 404 / 401 / 503 → the server's own message when present (capitalised),
  otherwise a status-based fallback.
- A tour whose id is non-numeric (a freshly generated job-id string) is rejected
  **locally** with a clear message — the server keys on the numeric
  `audio_tours.id`, so that round trip could never resolve.

### Dependency
`share_plus: 10.1.4` — **pinned** (no caret) on purpose: 11.x+ raises the min
Dart SDK above this project's 3.5 floor. 10.1.4 needs Dart ≥3.4 / Flutter ≥3.22.
`pub get` auto-registered the plugin on macOS/Windows registrants and `pod
install` added it to `ios/Podfile.lock` — all committed.

## The `original_tour_id` question (deliberate decision)
The task said: share the original (`original_tour_id`) *if that is what the
server expects, otherwise show the server's message*.

I read `sharing_endpoints.py` and `map_delivery/app.py`. The share endpoint
takes **only** `audio_tour_id` and reads that exact `audio_tours` row; it does
**not** accept or expect `original_tour_id`. A translation (and a test tour) is
itself a real `audio_tours` row, so sharing it by its own id is valid and
resolves correctly; `/tour-by-code` returns `original_tour_id` in its payload as
the app's existing translation chain. **Correct behaviour therefore = send the
tour's own id and surface the server's message on any error** — which is what
the service does. No server change was needed.

## Verification

### `flutter analyze` — no new issues
Measured the baseline on `subscribed` in a throwaway git worktree: **1384**
issues. My branch: **1386**. Delta **+2**, both `avoid_relative_lib_imports`
*infos* on my two new test files — the identical `../lib/...` convention the 4
pre-existing test files already use. **Zero** new warnings/errors in `lib/`; my
three new `lib/` files analyze clean.

### `flutter test` — new tests green
- `test/share_code_test.dart` — 18 tests (bare code, full message, link,
  whitespace; Boston/Newton MA/Brooklyn/Portland reject; discriminator; message
  builder). **Pass.**
- `test/tour_share_service_test.dart` — 6 tests (non-numeric/null/empty id
  rejected locally without throwing; `ShareResult` invariants). **Pass.**
- The only failures in the suite are 6 in `test/local109_swipe_e2e_test.dart`,
  all `SocketException: Connection refused` — a pre-existing live-backend E2E,
  unrelated to this change.

### Scripted LOCAL round trip (ports 5000 / 5005)
Stack up: `audioura-tour-generator-1` (:5000), `audioura-map-delivery-1`
(:5005), `development-postgres-2-1` (:5433). Using real tour id 1:
```
POST /tour/share {"audio_tour_id": 1}
  → {"share_id":"AzuwQYnf","share_url":"http://localhost:5000/tour/AzuwQYnf"}
GET  /tour-by-code/AzuwQYnf  (map-delivery)
  → tours[0].id == 1  ("Palais Lascaris, Nice, France - museum Tour")  ✓
Idempotent:   re-share tour 1 → same "AzuwQYnf"                        ✓
Error path:   POST audio_tour_id 999999 → HTTP 404 {"error":"tour not found"} ✓
```

### iOS build (build only — phone not tethered)
`xcrun devicectl` shows Michael's phone unavailable, so build only, no install,
no TestFlight. The canonical `build_ios_release.sh` targets
`~/Audioura/audio_tour_app` (a different worktree on a different branch) and only
*prints* the TestFlight upload command — it does not build this branch. To
verify **this** branch compiles I ran, in this worktree:
```
flutter build ios --release --no-codesign
  → Running pod install… (share_plus integrated, checksum 50da8cb…)
  → ✓ Built build/ios/iphoneos/Runner.app (36.4MB)
```
**Build path:**
`/Volumes/AudiouraSSD/audioura-worktrees/LOCAL-579/audio_tour_app/build/ios/iphoneos/Runner.app`

Leave install for when the phone is plugged in: codesign + `install_to_iphone.sh`
(or the signed `build_ios_release.sh` from `~/Audioura` once this branch is
checked out there).

## Files changed
```
audio_tour_app/pubspec.yaml                         share_plus 10.1.4 (pinned)
audio_tour_app/pubspec.lock                         resolved lock
audio_tour_app/lib/config/endpoints.dart            Service.generator (:5000)
audio_tour_app/lib/utils/share_code.dart            NEW — extractor + message
audio_tour_app/lib/services/tour_share_service.dart NEW — POST /tour/share
audio_tour_app/lib/widgets/share_tour_sheet.dart    NEW — flow + result sheet
audio_tour_app/lib/screens/my_tours_screen.dart     Share menu item + handler
audio_tour_app/lib/screens/tour_player_screen.dart  Share AppBar button
audio_tour_app/lib/screens/home_screen.dart         accept full message/link
audio_tour_app/test/share_code_test.dart            NEW — 18 tests
audio_tour_app/test/tour_share_service_test.dart    NEW — 6 tests
audio_tour_app/ios/Podfile.lock                     share_plus pod
audio_tour_app/macos/.../GeneratedPluginRegistrant  share_plus registrant
audio_tour_app/windows/flutter/generated_plugins*   share_plus registrant
```

## Scope honoured
No server changes (the round trip proved none were needed). No GCloud. No
TestFlight upload. No DELETE from `audio_tours`. Did not touch DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or `.continuous_dev/STATUS.md`.
