# SUBMISSION — LOCAL-780

**The creator's own priced tour: the translated copy's download gets 402 (no `user_id`), so "Russian only" ends on English with nothing playing**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-780-download-user-id` (from `subscribed` @ `572a4844`)
- **Base verified:** `git merge-base --is-ancestor 572a4844 HEAD` → exit 0

---

## 1. Root cause

map-delivery's pay-before-download gate (`_download_gate`) decides unlock / grandfather /
**creator-exemption** from the `?user_id=` query parameter. Three of the four app call sites
already attached it; the **Generate screen** did not:

`tour_generator_screen.dart _processAdditionalLanguages` built the translated download as
`Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId')` with `apiHeaders` only —
**no `user_id`**. The server therefore treated it as anonymous and returned **402** even for the
**creator's own priced tour**. With `wantsEnglish=false` the download returned null, the English
fallback was never played, and **no message** was shown — the listener was left on a blank Listen
screen with the English copy silently saved (Michael, TestFlight 79, USER-41659366, tour 452→453).

The server gate is correct (the creator IS exempt — it just needs the client to identify itself).
**No server change.**

## 2. The fix — ONE helper every call site goes through

New single source of truth in `lib/config/endpoints.dart`:

```dart
static Future<Uri> downloadTourUrl(Object tourId) async {
  final prefs = await SharedPreferences.getInstance();
  final userId = prefs.getString('user_id') ?? '';
  final uri = await url(Service.mapDelivery, '/download-tour/$tourId');
  final params = Map<String, String>.from(uri.queryParameters);
  if (userId.isNotEmpty) params['user_id'] = userId;
  return uri.replace(queryParameters: params.isEmpty ? null : params);
}
```

A blank/absent id yields the bare URL (unchanged for an anonymous device).

### Every `/download-tour` call site — now via the helper (grep, file:line)

| # | Call site | Line | Path |
|---|-----------|------|------|
| 1 | `lib/services/tour_download_service.dart` (`downloadAndSave`) | 152 | `final uri = await Endpoints.downloadTourUrl(tourId);` |
| 2 | `lib/services/tour_download_service.dart` (`reDownloadAndReplace`) | 259 | `final uri = await Endpoints.downloadTourUrl(tourId);` |
| 3 | `lib/screens/home_screen.dart` (`_downloadTourUri`) | 1984 | `Endpoints.downloadTourUrl(tourId);` |
| 4 | `lib/services/tour_translation_helper.dart` (`downloadTranslatedVersions`) | 121 | `final translatedUri = await Endpoints.downloadTourUrl(translatedId);` |
| 5 | `lib/screens/tour_generator_screen.dart` (`_processAdditionalLanguages`) | 1046 | `await Endpoints.downloadTourUrl(translatedId),` **← the bug** |

The builder itself: `lib/config/endpoints.dart:203` (`downloadTourUrl`), the **only** place that
constructs a `/download-tour/` URL via `Endpoints.url` (endpoints.dart:206). A source-level guard
test fails if any other `lib/` file hand-builds one.

### `_processAdditionalLanguages` failure/success UX (Build §2)

- **Success:** unchanged — the translated tour is played at once (the "instant" play), English
  fallback pruned.
- **Failure** (`translatedPath == null`, user did not ask for English): previously just cleared the
  progress label (silent). Now it **shows a clear message** and **plays the English copy** already
  downloaded/extracted at `tours/<finalTourId>`:
  > "Couldn't download the Russian version — showing English."
  (pure helper `TourTranslationHelper.translationFallbackMessage(langCode)`, names the language in
  full.) A `wantsEnglish` param was added to `_processAdditionalLanguages` so its own finally-block
  snackbar is suppressed on the Russian-only path — the caller owns the one message + playback, no
  double snackbar.

## 3. Tests — red first

`test/download_tour_user_id_local780_test.dart` (8 tests):

1. helper appends `user_id` when stored; omits it (bare URL) when absent (anonymous device);
2. a `MockClient` map-delivery that **402s WITHOUT `user_id` and 200s WITH it** is satisfied by a
   request built from the helper — i.e. the translated download now sends `user_id` and gets 200;
3. **source guard:** no `lib/` file hand-builds a `/download-tour` URL via `Endpoints.url` (only the
   helper may), plus a counter-guard that the four known caller files reference `downloadTourUrl`;
4. the Generate-screen fallback message names the language and says it is showing English.

**Red confirmed before the fix:** with the call sites still hand-building the URL, the two source-
guard tests failed (`+6 -2`); after routing all sites through the helper, **all 8 pass**.

**Existing suite green:** full `flutter test` → `+1132 -7`. The 7 failures are pre-existing and
network/DB-dependent (`local109_swipe_e2e_test.dart`, `storied_compat_screens_404_test.dart` —
`SocketException: Connection refused` to localhost ports). Verified **identical on the clean base**
by stashing this task's changes and re-running those two files (`+14 -7`) — this change causes none
of them. `flutter analyze` on the five changed files: no error-level issues (only pre-existing
info/warning lints).

## 4. Live test — Android emulator ONLY, against the LOCAL stack, $0.00

Debug build `--dart-define=APP_TRACK=subscribed --dart-define=DEBUG_SERVER_IP=192.168.0.187`,
installed on AVD `local715_test` (emulator-5554), pointed at the **existing running LOCAL
`audioura-*` stack** (192.168.0.187). Because the server gate is correct and **unchanged**, no new
server containers were needed — so **no `-p local780` containers were created, and `audioura-*` was
never touched, replaced, or renamed** (still Up 17h, healthy). **No tour was generated → budget
$0.00.**

Evidence (`/tmp/local780_mapdelivery_evidence.txt`, map-delivery access log, ANSI-stripped):

```
GET /download-tour/749                        HTTP/1.1  402 -   ← curl, no user_id
GET /download-tour/749?user_id=USER-41659366  HTTP/1.1  200 -   ← curl, creator exemption
GET /download-tour/557?user_id=USER-41659366  HTTP/1.1  200 -   ← the FIXED app
GET /download-tour/683?user_id=USER-41659366  HTTP/1.1  402 -   ← the FIXED app
```

- **Server gate proven** on the creator's own priced tour **749** (`creator_user_id = USER-41659366`,
  `price_tier 9`): **402 without `user_id`, 200 with it.** The exemption is real and correct.
- **The fixed app now attaches `user_id` on every `/download-tour` request** (last two lines). 683
  is the **paid Russian translation of 557**; its 402 is the *correct* per-language purchase gate
  (this device didn't create 557, and 683 is a separate paid unlock) — the point LOCAL-780 is about
  is that **the request carries `user_id`**, which it now does. Before the fix the Generate-screen
  translated download carried **none**.
- **Graceful fallback proven on-device:** after the Russian download was refused, the **English copy
  was saved and shown playable (▶) on the Listen tab** (never "nothing playing"); the app surfaced a
  clear "English version was saved" notice. Screenshots `screenshots/local780_01..13`
  (`local780_12_download.png`, `local780_13_listen.png`).

**Scope note (honest):** the full *generate → price → Russian plays* happy path was not driven on
the emulator because the Generate-screen **price picker is gated on `EntitlementsService.canSell`**
(curator/seller only), and the fresh emulator device user is not a seller. Pricing a freshly
generated tour would require a **server-side seller-entitlement change**, which this ticket forbids
("don't change the server gate"). The fix mechanism is nonetheless proven end-to-end by the above:
the gate flips 402→200 purely on `user_id`, and the fixed client now always sends it.

**Cleanup:** emulator killed (`adb emu kill`; `adb devices` empty afterward); the dev-only,
gitignored `android/app/debug.keystore` used to sign the debug build was removed.

## 5. Files changed

- `lib/config/endpoints.dart` — new `downloadTourUrl` helper.
- `lib/services/tour_download_service.dart` — both sites via helper.
- `lib/screens/home_screen.dart` — `_downloadTourUri` delegates to helper.
- `lib/services/tour_translation_helper.dart` — translated download via helper; new pure
  `translationFallbackMessage`.
- `lib/screens/tour_generator_screen.dart` — translated download via helper; failure path plays
  English + shows the message; `wantsEnglish` param to avoid a double snackbar.
- `test/download_tour_user_id_local780_test.dart` — new (8 tests).
- `screenshots/local780_12_download.png`, `screenshots/local780_13_listen.png` — live evidence.

## 6. Process compliance

Branched from `subscribed` HEAD (`572a4844`), never from `origin/*`. No `git add -A`. No edits to
DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE / `.continuous_dev/` /
SUBSCRIBED_COMMUNICATION_01.MD / `legal/` / GCLOUD_STORIED_START_HERE.md. No `DELETE` of any kind;
no DB rows modified (read-only inspection). One heavy build. Emulator only — never Michael's phones.
