# SUBMISSION — LOCAL-868: App "Paste a list of places" + free map preview + Share → Audioura (D762, app side)

**Branch:** `LOCAL-868-app-paste-list` · **Base:** subscribed `6bdd3dbe` (`git merge-base --is-ancestor 6bdd3dbe HEAD` exits 0).
**Build number:** not bumped.

## Result in one line

Paste → free preview (10/10 pins, live, iOS simulator) → review → Generate sends the LOCAL-867 object contract (live: orchestrator `imported 10 stops (10 with a reviewed pin carried, order kept)`, the generator got all 10 FORCED in order). Android Share → Audioura works live on the emulator. **10/10 delivered is NOT proven:** the one live generation was aborted by the generator's own $0.40 cost ceiling (D45), and the task budget is spent (**$0.4645 metered against a $0.40 budget, over by $0.06**, see Budget).

## What changed (all under `audio_tour_app/` unless noted)

| File | Change |
|---|---|
| `lib/utils/pasted_list.dart` (new) | Pure logic: the `/preview-stops` body `{text, city}`, input checks that match the server's (blank, > 8000 chars), response parsing (`PreviewStop`, resolved or unresolved), delete/reorder, conversion to the existing user-stop maps, and `userStopsForGeneration`. A pasted list becomes **objects** `{name, lat, lng, resolved_name[, matched_name]}`. An unresolved stop is `{name}` only. A hand-built list stays the **plain string list**, so the default request body is byte-for-byte unchanged. Also: city from the request text and from a Nominatim reverse result. |
| `lib/services/preview_stops_service.dart` (new) | `POST /preview-stops` on the generator (`Endpoints.post`, 60 s timeout). 400 (no city), 404 (USER_STOPS_ENABLED off / route missing) and transport errors become plain messages. |
| `lib/screens/paste_list_screen.dart` (new) | Step 1: a multi-line box (hint `e.g. Cathedral → Post Office → Book Street`) and a City field. The City field takes the Create Tour location first, then the device's last-known position via Nominatim reverse. It never raises a permission prompt and never overwrites what the user typed. Step 2: a flutter_map with numbered pins on `MapTiles.primaryTemplate` + `ResilientTileProvider` (the tile proxy, same as the other maps), fitted to the pins. Below it, a reorderable list: number, name, "You wrote: …", "Found: …", note, a confidence chip, and **"no pin, we'll find it by name"** for unresolved stops. Delete and drag-reorder update the list and the pin numbers. "Use these N stops" pops the result. Nothing paid happens on this screen. |
| `lib/screens/tour_generator_screen.dart` | A **"Paste a list of places"** button under the "Audioura suggests / I will name the stops" selector. The result goes into the same `_userStops` list the LOCAL-523 loop edits and switches to "name" mode, so the existing review, "Edit your N stops", retry snapshot and generate/progress flow are reused unchanged (D564). If the request box is empty it is filled with `walking tour for <city>` (the orchestrator needs a location). Both generate paths (foreground and background) now send `userStopsForGeneration(_userStops)`; `total_stops` is the count, as before. Listens to `PendingSharedText` and opens the paste box pre-filled. |
| `lib/services/shared_text_service.dart` (new) | `PendingSharedText` (a parked ValueNotifier, same shape as `PendingShareSearch`), the Android channel `com.audioura.app/share`, and `textFromPasteUri` for `audioura://paste?text=…`. |
| `lib/screens/main_screen.dart` | When shared text arrives, switch to the Create Tour tab. |
| `lib/services/deep_link_service.dart` | Cold- and warm-start `audioura://paste?text=` URIs are handed to `PendingSharedText` (the existing `/t/<CODE>` handling is untouched). |
| `lib/main.dart` | `SharedTextService.instance.init()` at startup (unawaited, never throws). |
| `lib/config/endpoints.dart` | A debug-only `DEBUG_PORT_OFFSET` dart-define, applied only when `DEBUG_SERVER_IP` is set. It let the simulator reach my own stack on 150xx while the shared containers hold 5000–5030. Default 0 means no behaviour change. |
| `android/.../com/audioura/app/MainActivity.kt` | `ACTION_SEND text/*`: cold start answers `getInitialSharedText`; warm start (`singleTop`) uses `onNewIntent` → `sharedText`. The extra is stripped after reading so a recreate doesn't deliver it twice. The **existing** `SEND text/plain` intent-filter (the Gmail newsletter one) already routes here, so the manifest change is a comment only. |
| `ios/AudiouraShare/` (new target) + `ios/Runner.xcodeproj` + `ios/Runner/Info.plist` | **iOS choice: a Share Extension that hands off by URL scheme.** `ShareViewController` reads the shared plain text (or a URL, or `attributedContentText`), cuts it at 8000 characters and opens `audioura://paste?text=<percent-encoded>`. It needs no App Group and no shared container, so the only signing addition is one new bundle id, `com.audioura.audiotours.ShareExtension`, under the existing team `4HGRU6TKGQ` with Automatic signing. Runner registers the `audioura` scheme and sets `FlutterDeepLinkingEnabled=false` (app_links handles URLs, not the engine router). The extension's version comes from `Flutter/Generated.xcconfig`, so its CFBundleVersion always matches Runner's. The "Embed Foundation Extensions" phase is placed before "Thin Binary" (the standard fix for the Flutter build cycle). |
| `test/storied_compat_allowlist.txt` | Two SAFE entries for the new raw calls (preview service; best-effort city reverse lookup). |
| `docker-compose.local868-proof.yml` (repo root) | My own stack: project `local868`, own postgres on :55968, generator :15000, orchestrator :15002, user-api :15003. Meter wired (`TASK_BUDGET_ID=LOCAL-868`, `TASK_BUDGET_USD=0.40`). |
| `integration_test/local868_paste_live_test.dart` | The live simulator/emulator run (`paste` and `share` modes, host-side screenshots). |

**Workaround still works:** a whole list typed into one "Stop name or description" field still goes through as one string, and the server's D762 quick path expands it. This is covered by a unit test; the code path is unchanged.

## Tests (offline)

`test/paste_list_local868_test.dart`: **18 passed**.
- **Preview payload:** exactly `{text, city}`, trimmed. Blank or oversize input is refused with 0 requests. The 400 and 404 errors map to messages.
- **Parsing:** resolved and unresolved stops, confidence chips.
- **Delete/reorder:** in the pure helpers, and in the real widget (delete updates the list and the pins; a real drag gesture reorders; Use pops the new order, 9 stops).
- **Generate payload, through the real `TourGeneratorScreen`:** Paste → Preview → Use → Generate Now sends `user_stops` as 10 objects with `name/lat/lng/resolved_name`, first Cathedral, last Thi Bar, `total_stops == 10`, `location == "Ho Chi Minh City"`. A hand-built list stays strings, and the single-field workaround stays one string.
- **Share:** text offered while Create Tour is open opens the box pre-filled; text waiting at launch does too. `audioura://paste?text=` parsing; blank/oversize handling.

**Full Flutter suite:** HEAD 1273 passed / 8 failed. The 8 failing test IDs are **identical** on an untouched base (I stashed my changes and re-ran; the diff is empty). One of them is `storied_compat_guard` on `services/failure_reporter.dart`, which was already failing on base. `flutter analyze` shows no errors or warnings in the new files.

**Builds:** `flutter build ios --simulator --debug` succeeds with `Runner.app/PlugIns/AudiouraShare.appex` embedded. The Android debug APK builds and installs on the emulator.

## Live — own stack only (D753), simulators/emulator only

The stack was `docker-compose.local868-proof.yml`, every image built from this worktree, with its own DB. :5000/:5002, the shared `audioura-*` containers and the live DB were not touched. The stack is now down (`down -v` on project `local868` only). The devices were the iPhone 17 simulator (iOS 26.4) and the Android emulator `local715_test`. A physical Android phone was attached over adb: every adb command named `-s emulator-5554`, and nothing was installed on it.

### 1. Preview of Michael's exact list — PASS (iOS simulator)

`preview-stops: 10 stops, 0 unresolved, city='Ho Chi Minh City', cost $0.004, 0 LLM calls`. The app shows **10 numbered pins** on the tile-proxy map (`pins_on_map=10`) and 10 rows with resolved names and chips. Screenshots: `screenshots_local868/ios_preview_PREVIEW_TOP.png` and `ios_preview_PREVIEW_LIST_LOWER.png`. Pins 1–3 (Cathedral, Post Office, Book Street, about 100 m apart) overlap at this zoom; the list makes the order unambiguous.

### 2. Generate — request PASS, delivery NOT PROVEN

- The app sent `{"location":"Ho Chi Minh City","tour_type":"walking","total_stops":10,"user_stops":[{"name":"Notre-Dame Cathedral Basilica of Saigon","lat":10.779722,"lng":106.699167,"resolved_name":…}, …]}`.
- The orchestrator logged `[LOCAL-867] imported 10 stops (10 with a reviewed pin carried, order kept)`.
- The generator logged `FORCED STOPS ACTIVE` with all 10 in the pasted order (Notre-Dame … Thi Bar).
- The app showed the existing progress UI (`ios_gen_PROGRESS_2.png`).
- The job then failed at the generator: **`COST HARD LIMIT EXCEEDED: $0.4550 > $0.4000 — ABORTING tour delivery`**. The app showed that message with "Try again" (`ios_gen_GENERATE_DONE.png`).
- So the order and pins reached generation intact, but **"10/10 delivered in order" is not shown live.** LOCAL-867 shows delivery from this exact intake on the server side (10/10, order kept); this run adds that the app now produces that intake.
- **Why it cost more than LOCAL-867 ($0.23–0.25):** my containers ran the generator's default models. Gemini alone was $0.405 across 7 calls. LOCAL-867's in-process harness pinned `NARRATION_MODEL=gpt-4.1-mini` and the cheap-arm categories. **For LEAD:** a 10-stop walking tour on the generator's container defaults goes past the D45 $0.40 ceiling. Production would abort the same way unless its env matches LOCAL-867's.
- A first attempt was refused at $0 (`level_cannot_generate`, the test user had no plan). The rerun used the seeded `local821-tester` (L3). Another attempt missed the off-screen Generate button, also $0.

### 3. Share → Audioura

- **Android emulator — PASS.** `adb -s emulator-5554 shell am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT '…'` reached the running app (warm start, `onNewIntent`). It switched to Create Tour and opened the paste box pre-filled (`box_text=Cathedral, Post Office, …`). The City field filled itself from the emulator's location ("Boston", the emulator default), which shows the location-based pre-fill working. Screenshot: `and_share_SHARE_BOX.png`. The red "couldn't connect securely" banner in that shot comes from this test build running in cloud mode without attestation, not from this feature.
- **iOS — PARTIAL.** The extension builds and is embedded. `simctl openurl audioura://paste?text=…` is routed to Audioura (iOS shows "Open in 'Audioura'?", `ios_share_OPEN_IN_AUDIOURA_PROMPT.png`). I could not tap "Open" from the host: System Events has no accessibility access to the Simulator window. So the last hop (URL → box) is proven only by unit tests, which exercise the same `textFromPasteUri` → `PendingSharedText` path the Android run proved end to end. The extension UI itself (picking "Audioura" in another app's share sheet) was **not** exercised. It also needs signing with the new bundle id on the real team, which I did not do (no archive or upload).

### Budget

The meter (`service=LOCAL-868`, `_local868_meterlogs/paid_api_calls.jsonl`, not committed) shows **$0.4645 in total, against a $0.40 budget**: Gemini $0.4052 (7 calls), OpenAI $0.0393 (8), Serper $0.0200 (37). Two previews were $0.004 each; the rest is the one generation.

**The budget was overrun by $0.06.** The generator's COST_HARD_LIMIT ($0.40) stopped delivery, but only after the spend was already $0.455. That ceiling is checked at the end of text generation, not before each call, and the LOCAL-827 whole-task cap did not stop the run at $0.40 inside the container. I did not investigate why. After this I made no further paid calls (the iOS/Android share checks cost $0).

## What this does NOT prove

- 10/10 delivered tour from the app (blocked by the cost ceiling and the budget; see §2).
- The iOS share-sheet extension UI from another app, and its release signing.
- A preview on Android: only the share hand-off was run there, to avoid more spend. The preview screen is the same Dart code that ran on iOS.
- On a real device the city pre-fill uses Nominatim reverse (OSM). That fails silently and only fills an empty field.

## Not committed

`_local868_meterlogs/` (meter rows plus the orchestrator/generator logs), `_local868_tours/`, `build/`, the local debug keystore (removed).
