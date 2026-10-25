# SUBMISSION — LOCAL-761: persistent tab bar that hides while scrolling (D710 as amended)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-761-persistent-tabs`
**Base:** `subscribed` @ `c6823105` (contains LOCAL-760) — verified
`git merge-base --is-ancestor c6823105 HEAD` exits 0.
**Release gate:** hold until LOCAL-760 is merged (both touch community/listen screens).

---

## What D710 (amended by Michael, 2026-10-24) asked for, and what shipped

| Requirement | Status |
|---|---|
| Persistent bottom bar — a screen pushed inside a tab keeps the bar | ✅ one `Navigator` per tab inside an `IndexedStack`; the bar lives outside the stack |
| NO swipe between tabs | ✅ none added |
| Tabs unchanged: **Home · Generate Tour · Listen · Treats · About**, same order | ✅ identical items/labels; no Communities tab, no Settings move |
| A community page opens inside the **current** tab with the bar visible | ✅ in-tab `Navigator.push(context, …)` now pushes into the current tab's own Navigator |
| Re-tap the active tab → pop that tab to its first screen | ✅ `_onTabTapped` pops the tab's Navigator to its first route |
| Android Back → pop inside the tab; at a tab's first screen → Home; at Home → leave the app | ✅ `PopScope` + `_handleBack()` |
| Auto-hide: bar slides down on scroll-down, returns on scroll-up / at top / no scroll | ✅ `NotificationListener<ScrollNotification>` + `AnimatedSlide`/`AnimatedOpacity` |
| Never hidden while a SnackBar needs it as an anchor | ✅ the bar is a normal `bottomNavigationBar`; a SnackBar anchors above it (see Android screenshot 01, bar + SnackBar coexist) |
| Full-screen / modal flows may hide the bar but always keep a close/back control | ✅ pushed detail screens carry their own AppBar/back; the bar rides with them |
| Keep each tab's state (scroll, map, search) when switching | ✅ `IndexedStack` keeps every visited tab's Navigator mounted |

---

## The one file changed

`audio_tour_app/lib/screens/main_screen.dart` — rewritten.
`git diff --stat`: **1 file changed, 314 insertions(+), 49 deletions(-)**.

### Architecture

- **One `Navigator` per tab.** Five `GlobalKey<NavigatorState>` in an `IndexedStack(index: _selectedIndex)`. The `BottomNavigationBar` is the Scaffold's `bottomNavigationBar`, **outside** the stack, so any screen pushed inside a tab keeps the bar visible. Because `IndexedStack` keeps every visited tab's Navigator mounted, each tab preserves its own navigation stack, scroll position, map and search text.
- **Auto-hide.** A single `NotificationListener<ScrollNotification>` wraps the stack and drives one `bool _barVisible`. A reverse scroll (content up) hides the bar; a forward scroll, reaching the top, a scroll-end at the top, or any tab switch shows it. The bar is wrapped in `AnimatedSlide` (offset `(0,1)` when hidden) + `AnimatedOpacity`.
- **Re-tap-to-root.** Tapping the already-selected tab pops that tab's Navigator to its first route.
- **Android Back** (`PopScope`): `canPop` is true only at the Home tab's root with an empty Home stack. Otherwise Back is intercepted — pop the current tab's Navigator if it can pop, else switch to Home, else (Home root) let the system background/exit the app (current behaviour).
- **`app_mode` (Tours ⇄ Audio) preserved.** Pre-761, switching tabs disposed/rebuilt each screen, so Home/Generate/Listen re-read `app_mode` in `initState` — that fresh `initState` on tab entry was the Tours/Audio switch mechanism. With persistent Navigators the roots stay mounted, so the same contract is reproduced explicitly: `_refreshModeForTab(index)` (on entering a content tab) and the notification/resume/Listen-open paths bump a per-tab root version and `popUntil(first)`, giving the root a fresh `initState` exactly as before.
- **Lazy tab content.** Each tab's Navigator mounts eagerly (its key/stack/scroll survive once visited), but a tab's heavy root screen is only built on first visit. Production always starts on Home, so Home still builds up front — behaviour unchanged — while the other four screens defer until selected.

### Navigation call sites changed: **ZERO beyond `main_screen.dart`**

Audited every `Navigator.*` in `lib/` (91 sites):

- With one Navigator per tab, **every existing in-tab `Navigator.push(context, …)` now pushes into the current tab's own Navigator automatically** (the pushing `context` is below the tab's Navigator). Community pages and tours therefore open inside the current tab with the bar visible — the required behaviour — with **no edits to any call site**.
- `pushNamed`: none in `lib`.
- `rootNavigator: true`: one use (`home_screen.dart:2683`) — a dialog *dismissal*, not a page push; renders above everything regardless. No change needed.
- `pushReplacement` in `news_player_screen.dart` and `communities_about_screen.dart`: both use in-tab `context`, so they replace within the current tab and the bar stays — desired.
- Root-level entry points already select the correct tab via `MainScreen`: notification "View" → Listen tab; `PendingListenOpen` → Listen; `PendingShareSearch` → Home; deep links only set those notifiers (never push). No global `navigatorKey` exists (`communityScaffoldMessengerKey` is a ScaffoldMessenger key for SnackBars).

`main.dart` is unchanged and still valid (`MainScreen(initialTab: 3)` for `/treats`; `createState()` now returns the public `MainScreenState`).

---

## Tests (red first)

New file: `audio_tour_app/test/persistent_tabs_local761_test.dart` (11 tests). Written **red** against the pre-761 MainScreen (the hooks `MainScreenState`, `kMainBottomBarKey`, `kMainBottomBarSlideKey` did not exist — confirmed compile-fail), then made green by the implementation.

Pinned behaviours:
1. Tab order and labels are exactly **Home · Generate Tour · Listen · Treats · About**; no Communities tab.
2. Each of the five tabs has its own distinct `NavigatorState` key.
3. Pushing a screen inside the current tab keeps the bottom bar (`kMainBottomBarKey` still found).
4. Re-tapping the active tab pops its Navigator to root.
5. Android Back pops within the tab; at a non-Home tab root it goes to Home; at the Home root it is **not** consumed (the app may exit).
6. Firing `PendingListenOpen` selects the Listen tab with the bar visible.
7. A reverse scroll hides the bar; a forward scroll shows it; the `kMainBottomBarSlideKey` slide wrapper exists.
8. A tab's heavy content is built lazily — starting on Treats does not mount the Home Navigator until Home is visited.

### Results

- `flutter test test/persistent_tabs_local761_test.dart` → **11 passed**.
- Existing `downloaded_message_and_listen_open_test.dart` (which pins "PendingListenOpen → Listen tab shows MyToursScreen") → **30 passed**, unchanged.
- **Full suite**: 1088 pass, **7 fail** — the known baseline. The 7 are all pre-existing and network-dependent, unchanged by this work:
  - 6 in `local109_swipe_e2e_test.dart` — `SocketException: Connection refused` (need a live backend).
  - 1 in `storied_compat_screens_404_test.dart` — "Your plan on a Storied gateway 404" (needs a gateway). **Confirmed pre-existing**: stashing the `main_screen.dart` change and re-running shows it still fails on the original code.
  - Zero new failures introduced.
- `flutter analyze lib/screens/main_screen.dart test/persistent_tabs_local761_test.dart` → **No issues found.** (The project-wide analyze's pre-existing issues are all in other, untouched test files; the lone "unused import 'main_screen.dart'" warning is in `tour_generator_screen.dart`, which this work did not modify.)

Flutter 3.41.6 stable.

---

## Live test (iOS simulator + Android emulator only — never Michael's phones)

Targeted **only** the virtual devices: Android emulator `emulator-5554` (sdk gphone64, API 34) and iOS simulator `iPhone 17`. The physical Pixel 4 (`99251FFAZ002YY`) and the iPhone were never targeted. Shared servers read-only; $0 budget (the 401/404 server logs are the read-only backend with no auth — the app renders normally).

A scratch harness mounted the **real `MainScreen`** and pushed a representative *"Beacon Hill Walk — a community tour"* detail screen (back button + a 40-row scrollable) into the current tab's Navigator — the same path an in-tab `Navigator.push` takes. (The harness was deleted after capture; it is not part of this submission.)

### Android — both required states captured

- `screenshots_LOCAL-761/android_01_community_tour_deep_bar_visible.png` — the deep community→tour screen (back arrow, "Stop 1…9") open **inside** the Home tab, with the persistent bar (Home · Generate Tour · Listen · Treats · About) fully visible. A SnackBar sits above the bar (bar-as-anchor requirement).
- `screenshots_LOCAL-761/android_02_bar_hidden_on_scroll.png` — the same screen scrolled down to "Stop 31…39"; the bottom bar has **slid away** (auto-hide confirmed).

### iOS — app builds & runs; screenshot blocked by an environmental impediment

- `screenshots_LOCAL-761/ios_launch_blocked_by_location_dialog.png`.
- The app **builds and runs** on the iPhone 17 simulator — the real `MainScreen` mounts and the Dart VM Service comes up with no crash (and, with lazy tab content, no `HOME:` logs when starting off-Home, confirming the deferred build).
- **Blocker:** the app's location plugin force-presents the native `NSLocation` permission dialog on every iOS launch *before* Dart runs, and this headless environment has no way to dismiss an iOS simulator native dialog. Verified stable across GUI click (no screen-recording permission; `screencapture` fails), System Events AX (Simulator exposes zero windows), synthesized keyboard input (not delivered), and `simctl privacy grant`/`reset` + `location set` + app-process relaunch (the dialog still fires). Android `adb` can tap/grant headlessly; the iOS simulator cannot here.
- The persistent-bar and auto-hide logic is **identical Flutter code on both platforms** — fully demonstrated by the live Android screenshots and locked by the 11 platform-independent widget tests.

Both the simulator and the emulator were shut down after capture (`flutter devices` shows no virtual device running).

---

## Process compliance

- Only `audio_tour_app/lib/screens/main_screen.dart` changed in `lib/`; the new test and the `screenshots_LOCAL-761/` folder are added. No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`, `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, or `legal/`.
- Committed with explicit paths (never `git add -A`). The incidental `ios/Podfile.lock` regenerated by the iOS build was restored; the scratch harness and a local (gitignored) `debug.keystore` were deleted.
