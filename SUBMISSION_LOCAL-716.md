# LOCAL-716 — "Downloaded" message: singular/plural, and a View that opens Listen and the tour

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-716-download-snackbar` (from `subscribed` = `7c43c0d4`)
**Base verified:** `git merge-base --is-ancestor 7c43c0d4 HEAD` → exit 0.
**Version:** `2.4.30+71` → `2.4.30+72` (build +1).

## The two problems

1. **Wording disagreed with its count.** A one-tour download said *"1 tour downloaded
   and now **are** available on your Listen Page"* — plural verb, singular count
   (Michael, Pixel-7, 2026-10-19).
2. **The View button did nothing.** `home_screen.dart` called
   `Navigator.pushNamed(context, '/my_tours')` in three places, but `/my_tours` is
   **not a registered route** (only `/treats` is, in `main.dart`). Tapping View was a
   no-op.

## What changed

### 1. One pure wording helper — `lib/utils/downloaded_message.dart` (new)

`downloadedMessage({downloaded, translations, alreadyDownloaded, failures})` builds the
text with correct agreement for **every** count it mentions:

| Input | Output |
|---|---|
| `downloaded: 1` | `1 tour downloaded and is now on your Listen page` |
| `downloaded: 2` | `2 tours downloaded and are now on your Listen page` |
| `downloaded: 1, translations: 1` | `1 tour downloaded with 1 translation and is now on your Listen page` |
| `downloaded: 2, translations: 3` | `2 tours downloaded with 3 translations and are now on your Listen page` |
| `downloaded: 1, alreadyDownloaded: 1` | `… (1 was already downloaded)` |
| `downloaded: 2, alreadyDownloaded: 3` | `… (3 were already downloaded)` |
| `downloaded: 0` | `No new tours downloaded - all selected tours were already on your phone` |

It is pure (no `BuildContext`, no I/O), so the goldens pin every wording directly.

### 2. One way to say "go to Listen, optionally open tour X" — `PendingListenOpen`

Added to `lib/services/deep_link_service.dart`, mirroring the existing
`PendingShareSearch`:

- `PendingListenOpen.instance.offer(tourId?)` parks a request. A `tourId` means
  "open that one tour"; `null`/empty means "just show Listen" (several tours — the
  newest is at the top of the list).
- A `PendingListenOpenRequest(tourId, token)` carries a monotonic **token** so two
  offers of the *same* id both notify listeners (a plain `ValueNotifier<String?>`
  would de-dupe and a second View tap would silently do nothing).
- `consume()` clears it.

**`MainScreen`** listens and, when a request fires, switches to the Listen tab
(index 2) and bumps `_listenTabVersion` — the **same mechanism** a notification tap
uses in `_initializeNotifications`. It does not consume (the request must survive the
rebuild so MyTours can read it).

**`MyToursScreen`** — extracted the row-tap navigation into `_openTourPlayer(tour)`
(verbatim: same `TourPlayerScreen` args) so a tap and a pending-open open the exact
same screen. After `_loadTours`, `_consumePendingListenOpen()` reads the request,
consumes it immediately (so it fires at most once), matches the saved tour by
`tour_id` **or** `server_tour_id`, and opens its player after the frame. A miss leaves
the user on the list; a `null` id just shows the list.

### 3. Every download snackbar now uses the helper + a working View

| Site | Before | After |
|---|---|---|
| `home_screen._downloadMultipleTours` (bulk) | plural-only text; `pushNamed('/my_tours')` | `downloadedMessage(...)`; View → `PendingListenOpen.offer(id)` when exactly 1 new tour, else `offer(null)` |
| `home_screen._downloadTour` — already-downloaded "Open" | `pushNamed('/my_tours')` | `PendingListenOpen.offer(tourId)` |
| `home_screen._downloadTour` — success "View" | `pushNamed('/my_tours')` | `PendingListenOpen.offer(tourId)` |
| `home_screen._downloadSingleTour` (primary Home map/search path) | *"Tour downloaded successfully!"*, **no View** | `downloadedMessage(downloaded: 1, translations: N)` + View → `offer(tourId)` |
| `community_page_screen._downloadCommunityTour` | *"Downloaded — it's now on this phone."* | `downloadedMessage(downloaded: 1)` + View → `offer(tour.id)` |

The fourth site (`_downloadSingleTour`) was **not** one of the three the ticket named,
but it is the path a tester actually hits when downloading from the Home map/search,
and it had no View button at all — so it was brought in line for consistency (it is
always exactly one tour, hence the singular "is now").

### 4. Unregistered named routes

Grepped the whole app for `pushNamed` / `pushReplacementNamed` / `popAndPushNamed`.
**`/my_tours` was the only unregistered named route, used only in the three
`home_screen.dart` sites above** — all now replaced. No other `pushNamed` named-route
navigation exists anywhere in `lib/`, so there was nothing else of the same pattern to
fix.

## Tests — `test/downloaded_message_and_listen_open_test.dart` (new, 17 tests)

- **9 message goldens**: 1/2 tours, with/without translations, already-downloaded
  (1 vs N agreement), and the none-downloaded line; plus a per-tour translation-failure
  tail.
- **5 `PendingListenOpen` units**: `offer(id)`/`offer()`/`offer("")`, `consume`, and
  the "two offers of the same id both notify" token guarantee.
- **1 MainScreen widget test**: firing the notifier switches the body to
  `MyToursScreen` (the Listen tab).
- **2 MyToursScreen widget tests** (consume-once): a matching saved tour pushes the
  player (asserted via a `NavigatorObserver`) and the request is consumed; a miss
  consumes the request and pushes no player. (path_provider channel mocked so
  `_healTourPaths`/`_loadTours` completes in the test VM.)

**Full `flutter test`: 675 passed, 6 failed.** The 6 failures are the pre-existing
baseline — all in `test/local109_swipe_e2e_test.dart` (`SocketException: Connection
refused`, they need a live server). That is +17 passing vs. the baseline's 658, and
the same 6 baseline failures, nothing new. `flutter analyze` on the changed files:
no errors (only pre-existing style lints in the large screens).

## Live test (Android emulator only — `emulator-5554`, AVD `local715_test`)

Never installed on any phone. Cloud mode is behind an app-attestation gate that a
debug emulator build cannot satisfy ("Audioura couldn't connect securely"), so the APK
was rebuilt with `--dart-define=DEBUG_SERVER_IP=10.0.2.2` to use the **already-running
local Docker backend** via the emulator's host alias. No server change; the
`audioura-*` containers were only read through the app (never started, stopped, renamed
or `-p audioura`). The debug signing keystore (`android/app/debug.keystore`, gitignored)
was copied from the standard `~/.android/debug.keystore`.

Verified (screenshots in `docs/LOCAL-716/`):

1. **`01_one_tour_message_and_view.png`** — downloading one tour shows the green
   snackbar *"1 tour downloaded and is now on your Listen page"* with a **View** button.
   The singular agreement is exactly the fix.
2. **`02_view_switched_to_listen.png`** — tapping **View** switches to the **Listen**
   tab.
3. **`03_tour_player_opened.png`** — the tour's player opens and auto-starts
   (logcat: `TOUR_PLAYER: Using mobile file URL …`, `Auto-start command executed`).
4. **`04_two_tours_on_listen.png`** — two downloaded tours on the Listen tab.

The two-tour aggregate wording ("2 tours … **are** now …") is pinned by the golden test.

## Files

- `audio_tour_app/lib/utils/downloaded_message.dart` (new)
- `audio_tour_app/lib/services/deep_link_service.dart` (PendingListenOpen)
- `audio_tour_app/lib/screens/main_screen.dart`
- `audio_tour_app/lib/screens/my_tours_screen.dart`
- `audio_tour_app/lib/screens/home_screen.dart`
- `audio_tour_app/lib/screens/community_page_screen.dart`
- `audio_tour_app/pubspec.yaml` (+1 → `2.4.30+72`)
- `audio_tour_app/test/downloaded_message_and_listen_open_test.dart` (new)
- `docs/LOCAL-716/01–04*.png` (live-test screenshots)

No changes to DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE, `.continuous_dev`, or any server
code.
