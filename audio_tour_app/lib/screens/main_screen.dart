import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'tour_generator_screen.dart';
import 'my_tours_screen.dart';
import 'treats_screen.dart';
import 'about_screen.dart';
import 'home_screen.dart';
import 'plan_screen.dart';
import '../services/notification_service.dart';
import '../services/background_service.dart';
import '../services/entitlements_service.dart';
import '../services/deep_link_service.dart';
import '../renewal_logic.dart';
import '../widgets/renewal_sheet.dart';
import '../services/communities_service.dart';
import '../services/pass_expiry_warning.dart';
import '../widgets/pass_expiry_warning_dialog.dart';
import 'community_page_screen.dart';

/// [LOCAL-761 / D710 as amended] Keys on the persistent bottom bar and the
/// animated wrapper that slides it away while the user scrolls content down.
/// Exposed so widget tests can assert the bar stays visible on pushed screens
/// and that the slide wrapper exists.
const Key kMainBottomBarKey = Key('main_bottom_bar');
const Key kMainBottomBarSlideKey = Key('main_bottom_bar_slide');

/// The five tabs, in order. Unchanged by D710 (amended): no Communities tab,
/// no Settings move. Community pages open INSIDE the current tab.
const int kHomeTab = 0;
const int kGenerateTab = 1;
const int kListenTab = 2;
const int kTreatsTab = 3;
const int kAboutTab = 4;
const int kTabCount = 5;

class MainScreen extends StatefulWidget {
  final int initialTab;
  const MainScreen({super.key, this.initialTab = 0});

  @override
  MainScreenState createState() => MainScreenState();
}

/// Public so widget tests can reach the per-tab Navigator keys, the current
/// index, the Android-back handler and the auto-hide state. Nothing outside
/// tests needs these; they carry the `...ForTest` suffix to make that clear.
class MainScreenState extends State<MainScreen> with WidgetsBindingObserver {
  late int _selectedIndex;
  int _listenTabVersion = 0;

  // [LOCAL-761] Tabs the user has actually visited. A tab's heavy root is only
  // built once it is in this set (the initial tab is added in initState). This
  // defers constructing the other four screens until they are needed.
  final Set<int> _visitedTabs = {};

  // [LOCAL-761] One Navigator per tab. A screen pushed inside a tab pushes into
  // that tab's Navigator (the pushing context lives below it), so the bottom
  // bar — which is OUTSIDE the IndexedStack — stays visible. The IndexedStack
  // keeps every tab's Navigator mounted, so each tab keeps its own navigation
  // stack, scroll position, map position and search text when you switch away
  // and back.
  final List<GlobalKey<NavigatorState>> _tabNavigatorKeys =
      List.generate(kTabCount, (_) => GlobalKey<NavigatorState>());

  // [LOCAL-761] app_mode preservation. Pre-761, switching tabs disposed and
  // rebuilt each screen, so HomeScreen / TourGeneratorScreen / MyToursScreen
  // re-read 'app_mode' in initState — that fresh initState is THE mechanism the
  // Tours<->Audio switch (set on the About tab) relied on. With persistent
  // Navigators the roots stay mounted, so we reproduce the contract explicitly:
  // we remember the app_mode each content tab's root was built under, and when
  // the user switches INTO a content tab whose root is now stale we reset that
  // tab's Navigator to a fresh root (a fresh initState, exactly as before).
  static const Set<int> _modeSensitiveTabs = {kHomeTab, kGenerateTab, kListenTab};
  final Map<int, String?> _tabBuiltUnderMode = {};
  // Bumped per content tab to force its root widget to rebuild from scratch.
  final Map<int, int> _tabRootVersion = {kHomeTab: 0, kGenerateTab: 0, kListenTab: 0};

  // [LOCAL-761] Auto-hide-on-scroll. The bar is visible unless the user is
  // actively scrolling content downward. It returns on scroll up, at the top of
  // a list, and on any screen that does not scroll.
  bool _barVisible = true;

  // [LOCAL-732] When the app last went to the background. A resume is only a
  // fresh "entry" (that re-checks pass expiry) when it has been more than an
  // hour. Null until the first pause.
  DateTime? _lastPausedAt;

  // [LOCAL-732] Guards against two overlapping warning checks (e.g. cold-start
  // post-frame racing a very fast background→foreground on some platforms).
  bool _passWarnInFlight = false;

  @override
  void initState() {
    super.initState();
    _selectedIndex = widget.initialTab;
    _visitedTabs.add(_selectedIndex);
    WidgetsBinding.instance.addObserver(this);
    _initializeNotifications();
    BackgroundService.startBackgroundMonitoring();
    // LOCAL-598 D2: tell the server the app opened (records activity) and act
    // on the renewal state it returns. Runs on launch; also on each resume via
    // didChangeAppLifecycleState.
    _runAppOpenEntitlementsCheck();
    // [LOCAL-709 / D671] When a share link produces a code (cold/warm start or
    // the deferred check), make sure we are on the Home tab so Home can fill
    // Search and run it. Home itself consumes the code via the same notifier.
    PendingShareSearch.instance.code.addListener(_onShareCodeArrived);
    // [LOCAL-716] A download snackbar's "View" asks to go to the Listen tab
    // (optionally opening one tour). Switch to the Listen tab exactly as a
    // notification tap does; MyToursScreen consumes the tour id itself.
    PendingListenOpen.instance.request.addListener(_onListenOpenRequested);
    // The one-shot deferred-link check (Android Install Referrer; iOS clipboard
    // prompt), run once ever, after the first frame so a BuildContext exists.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _onShareCodeArrived(); // act on a code already waiting at launch.
      _runDeferredLinkCheck();
      // [LOCAL-732] Cold start: once Home is visible, warn (once) about any
      // community pass ending within 3 days. Deferred to the first frame so a
      // BuildContext exists and Home is mounted.
      _maybeWarnPassExpiry();
    });
  }

  /// [LOCAL-709] A share code just became available: switch to Home so its
  /// listener runs the search. If already on Home, Home handles it directly.
  void _onShareCodeArrived() {
    if (PendingShareSearch.instance.code.value == null) return;
    if (_selectedIndex != kHomeTab && mounted) {
      _switchToTab(kHomeTab);
    }
  }

  /// [LOCAL-716] A "go to Listen (optionally open tour X)" request fired. Switch
  /// to the Listen tab and bump `_listenTabVersion` so MyToursScreen rebuilds
  /// with a fresh key — the SAME mechanism a notification tap uses in
  /// [_initializeNotifications]. MyToursScreen reads the pending tour id on load
  /// and opens that tour; it also calls consume(). We do NOT consume here: the
  /// request must survive the rebuild so MyTours can read it.
  void _onListenOpenRequested() {
    if (PendingListenOpen.instance.request.value == null) return;
    if (!mounted) return;
    setState(() {
      _listenTabVersion++;
      _tabRootVersion[kListenTab] = (_tabRootVersion[kListenTab] ?? 0) + 1;
      _selectedIndex = kListenTab;
      _visitedTabs.add(kListenTab);
      _barVisible = true; // a tab switch always reveals the bar.
    });
    // The Listen root is rebuilt fresh, so it is now built under the live mode.
    _resetTabToRoot(kListenTab);
  }

  /// [LOCAL-709 / D671 §4] The deferred-link one-shot: on the FIRST launch only,
  /// read the Android Play Install Referrer (no prompt) or, failing that, offer
  /// once to open a code-shaped clipboard string on iOS. Guarded internally so
  /// it never runs twice. Any failure is silent.
  Future<void> _runDeferredLinkCheck() async {
    await DeepLinkService.instance.runDeferredCheckOnce(
      readInstallReferrer: DeepLinkService.readPlayInstallReferrer,
      readClipboardCode: DeepLinkService.readClipboardShareCode,
      prompt: _promptOpenSharedTour,
    );
  }

  /// [D671 §4] The single iOS clipboard prompt: "Open the tour you were sent?".
  Future<bool> _promptOpenSharedTour(String code) async {
    if (!mounted) return false;
    final open = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Open the tour you were sent?'),
        content: Text('We found a tour code ($code) you copied. '
            'Open it in Audioura?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Not now'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Open'),
          ),
        ],
      ),
    );
    return open ?? false;
  }

  /// Guards against overlapping app-open checks (launch + a fast resume).
  bool _appOpenInFlight = false;

  /// POST /entitlements/app-open and, based on the result, show the renew-or-
  /// lapse sheet (at/after the anniversary) or the one-time 3-day warning
  /// banner. Any network failure is silent — the app must open normally even
  /// when the user-api is briefly unreachable.
  Future<void> _runAppOpenEntitlementsCheck() async {
    if (_appOpenInFlight) return;
    _appOpenInFlight = true;
    try {
      final ent = await EntitlementsService.appOpen();
      if (ent == null || !mounted) return;

      final prefs = await SharedPreferences.getInstance();
      final lastWarned = prefs.getString('renewal_last_warned_anniversary');
      final action =
          decideRenewalAction(ent, lastWarnedAnniversary: lastWarned);

      if (!mounted) return;

      if (action.showRenewalSheet) {
        final choice = await showRenewalSheet(context, entitlements: ent);
        if (choice == RenewalChoice.renew) {
          if (!mounted) return;
          // Buy again — the buy buttons + StoreKit flow live on the plan screen.
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const PlanScreen()),
          );
        } else if (choice == RenewalChoice.lapse) {
          await EntitlementsService.lapse();
        }
        // Dismissed (null): leave server state unchanged, ask again next open.
      } else if (action.showWarningBanner) {
        showRenewalWarningBanner(context, entitlements: ent);
        if (action.markWarnedAnniversary != null) {
          await prefs.setString('renewal_last_warned_anniversary',
              action.markWarnedAnniversary!);
        }
      }
    } finally {
      _appOpenInFlight = false;
    }
  }

  /// [LOCAL-732] Warn the member, ONCE per pass period, that a community pass
  /// ends within 3 days. Only when Home (tab 0) is the visible tab — the task
  /// says "once Home is visible, not over the onboarding or first-run notice
  /// screens". (MainScreen is only mounted AFTER onboarding + the first-run
  /// notice, so those screens can never be on top of this dialog; the Home-tab
  /// check keeps the warning off the Generate/Listen/Treats/About tabs.)
  ///
  /// Loads My communities (the same endpoint My communities uses, which carries
  /// expires_at + active), selects the active passes ending within 72 h, drops
  /// any already warned for this exact expires_at, shows ONE dialog for the
  /// rest, and only THEN marks them warned. A network failure shows nothing and
  /// stores nothing (CommunitiesService returns an empty list on error).
  Future<void> _maybeWarnPassExpiry() async {
    if (_passWarnInFlight) return;
    // Only on the Home tab.
    if (_selectedIndex != kHomeTab) return;
    _passWarnInFlight = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      if (userId == null || userId.isEmpty) return;

      // Network failure / feature absent → empty list → nothing shown, nothing
      // stored (CommunitiesService.mine swallows transport errors to []).
      final mine = await CommunitiesService.mine(userId);
      if (mine.isEmpty) return;

      final qualifying = PassExpiryWarning.select(mine);
      if (qualifying.isEmpty) return;

      // Drop the pass periods already warned (the once rule). A renewal changes
      // expires_at (D701), so its new period is not yet in the store.
      final toShow = await PassWarnedStore.unwarned(qualifying);
      if (toShow.isEmpty) return;

      // Re-check we are still on Home and mounted before putting up a dialog.
      if (!mounted || _selectedIndex != kHomeTab) return;

      await showDialog<void>(
        context: context,
        builder: (ctx) => PassExpiryWarningDialog(
          passes: toShow,
          onRenew: (communityId) {
            Navigator.pop(ctx);
            Navigator.push(
              context,
              MaterialPageRoute(
                  builder: (_) =>
                      CommunityPageScreen(communityId: communityId)),
            );
          },
          onLater: () => Navigator.pop(ctx),
        ),
      );

      // Mark warned AFTER the dialog was actually shown — never before, so a
      // network failure (handled above) can never silently consume a warning.
      await PassWarnedStore.markWarned(toShow.map((p) => p.warnedKey));
    } finally {
      _passWarnInFlight = false;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    PendingShareSearch.instance.code.removeListener(_onShareCodeArrived);
    PendingListenOpen.instance.request.removeListener(_onListenOpenRequested);
    BackgroundService.stopBackgroundMonitoring();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      // [LOCAL-732] Remember when we went to the background so a later resume
      // can tell "away for more than an hour" from a brief switch-away.
      _lastPausedAt = DateTime.now();
    }
    if (state == AppLifecycleState.resumed) {
      BackgroundService.startBackgroundMonitoring();
      // LOCAL-598 D2: app-open fires on resume too, not just launch.
      _runAppOpenEntitlementsCheck();
      // [LOCAL-732] Resume after more than an hour in the background re-runs the
      // 3-day pass-expiry warning (the once-per-pass-period key still prevents a
      // repeat for the same pass). A brief switch-away does not re-check.
      final pausedAt = _lastPausedAt;
      if (pausedAt != null &&
          DateTime.now().difference(pausedAt) > const Duration(hours: 1)) {
        _maybeWarnPassExpiry();
      }
      _lastPausedAt = null;
      // Refresh Home, My Tours, or Treats when the app is resumed. Pre-761 this
      // relied on a full rebuild; now we reset the tab's root to a fresh route
      // so its initState runs again (re-reading app_mode and reloading data).
      if (_selectedIndex == kHomeTab ||
          _selectedIndex == kListenTab ||
          _selectedIndex == kTreatsTab) {
        if (_selectedIndex == kListenTab) {
          _listenTabVersion++; // NF10: force Listen reload on resume
        }
        setState(() {
          final v = _tabRootVersion[_selectedIndex];
          if (v != null) _tabRootVersion[_selectedIndex] = v + 1;
        });
        _resetTabToRoot(_selectedIndex);
      }
    }
  }

  Future<void> _initializeNotifications() async {
    await NotificationService.initialize((NotificationResponse response) {
      // Navigate to the Listen tab when a notification is tapped.
      if (!mounted) return;
      setState(() {
        _listenTabVersion++; // NF11: force Listen reload (background-generated tour)
        _tabRootVersion[kListenTab] = (_tabRootVersion[kListenTab] ?? 0) + 1;
        _selectedIndex = kListenTab;
        _visitedTabs.add(kListenTab);
        _barVisible = true;
      });
      _resetTabToRoot(kListenTab);
    });
  }

  // ---------------------------------------------------------------------------
  // Tab roots. Returns a FRESH root widget whenever the per-tab root version is
  // bumped (notification / resume / Listen-open / stale app_mode). Each root
  // carries a ValueKey so bumping the version forces a new State and a new
  // initState — the pre-761 Tours<->Audio pickup, preserved.
  // ---------------------------------------------------------------------------
  Widget _buildTabRoot(int index) {
    switch (index) {
      case kGenerateTab:
        return TourGeneratorScreen(
            key: ValueKey('gen_${_tabRootVersion[kGenerateTab]}'));
      case kListenTab:
        return MyToursScreen(key: ValueKey('listen_$_listenTabVersion'));
      case kTreatsTab:
        return const TreatsScreen();
      case kAboutTab:
        return const AboutScreen();
      case kHomeTab:
      default:
        return HomeScreen(key: ValueKey('home_${_tabRootVersion[kHomeTab]}'));
    }
  }

  /// Reset one tab's Navigator to a single fresh root route. Used when we need a
  /// content tab to re-run its root initState (notification, resume, stale
  /// app_mode). Safe before the Navigator mounts (no-op until it exists).
  void _resetTabToRoot(int index) {
    final nav = _tabNavigatorKeys[index].currentState;
    if (nav == null) return; // not mounted yet; the IndexedStack will build it.
    nav.popUntil((r) => r.isFirst);
  }

  /// Read the live app_mode and, if a content tab's root was built under a
  /// different mode, bump that tab's root version and reset its Navigator so the
  /// root rebuilds from scratch. Called when switching INTO a content tab.
  Future<void> _refreshModeForTab(int index) async {
    if (!_modeSensitiveTabs.contains(index)) return;
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('app_mode') ?? 'Tours';
    final builtUnder = _tabBuiltUnderMode[index];
    if (builtUnder == mode) return; // already fresh for this mode.
    _tabBuiltUnderMode[index] = mode;
    if (!mounted) return;
    setState(() {
      final v = _tabRootVersion[index];
      if (v != null) _tabRootVersion[index] = v + 1;
      if (index == kListenTab) _listenTabVersion++;
    });
    _resetTabToRoot(index);
  }

  // ---------------------------------------------------------------------------
  // Tab selection + re-tap-to-root.
  // ---------------------------------------------------------------------------
  void _onTabTapped(int index) {
    if (index == _selectedIndex) {
      // D710: re-tapping the active tab pops it back to its first screen.
      final nav = _tabNavigatorKeys[index].currentState;
      if (nav != null && nav.canPop()) {
        nav.popUntil((r) => r.isFirst);
      }
      // A re-tap of the Listen tab also bumps its version (pre-761 behaviour).
      if (index == kListenTab) {
        setState(() => _listenTabVersion++);
        _resetTabToRoot(kListenTab);
      }
      setState(() => _barVisible = true);
      return;
    }
    _switchToTab(index);
  }

  void _switchToTab(int index) {
    setState(() {
      _selectedIndex = index;
      _visitedTabs.add(index);
      _barVisible = true; // any tab switch reveals the bar.
    });
    // Picking up a mode change made on the About tab (Tours<->Audio).
    _refreshModeForTab(index);
  }

  // ---------------------------------------------------------------------------
  // Android Back.
  //   * If the current tab can pop, pop it (stay in the app).
  //   * Else if we are not on Home, switch to Home.
  //   * Else (Home root) do not consume — let the system background/exit.
  // Returns true when the back was handled inside the app.
  // ---------------------------------------------------------------------------
  Future<bool> _handleBack() async {
    final nav = _tabNavigatorKeys[_selectedIndex].currentState;
    if (nav != null && nav.canPop()) {
      nav.pop();
      return true;
    }
    if (_selectedIndex != kHomeTab) {
      _switchToTab(kHomeTab);
      return true;
    }
    return false; // Home root → allow the system to handle it.
  }

  // ---------------------------------------------------------------------------
  // Auto-hide on scroll. A reverse scroll (content moving up, finger up) hides
  // the bar; a forward scroll (content moving down) or reaching the top shows
  // it. Idle / non-scrolling screens keep it visible.
  // ---------------------------------------------------------------------------
  bool _onScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final delta = notification.scrollDelta ?? 0;
      if (delta > 2 && _barVisible) {
        setState(() => _barVisible = false); // scrolling down → hide.
      } else if (delta < -2 && !_barVisible) {
        setState(() => _barVisible = true); // scrolling up → show.
      }
      // At the very top of the list, always show.
      if (notification.metrics.pixels <= notification.metrics.minScrollExtent &&
          !_barVisible) {
        setState(() => _barVisible = true);
      }
    } else if (notification is UserScrollNotification) {
      _applyScrollDirection(notification.direction);
    } else if (notification is ScrollEndNotification) {
      // At rest at the top → reveal.
      if (notification.metrics.pixels <=
              notification.metrics.minScrollExtent &&
          !_barVisible) {
        setState(() => _barVisible = true);
      }
    }
    return false; // let the notification keep bubbling.
  }

  void _applyScrollDirection(ScrollDirection direction) {
    if (direction == ScrollDirection.reverse && _barVisible) {
      setState(() => _barVisible = false);
    } else if (direction == ScrollDirection.forward && !_barVisible) {
      setState(() => _barVisible = true);
    } else if (direction == ScrollDirection.idle && !_barVisible) {
      // Idle does not force the bar back; it returns on scroll up or at top.
    }
  }

  // ---------------------------------------------------------------------------
  // Testing hooks (used by test/persistent_tabs_local761_test.dart).
  // ---------------------------------------------------------------------------
  GlobalKey<NavigatorState> tabNavigatorKeyForTest(int index) =>
      _tabNavigatorKeys[index];
  int get currentIndexForTest => _selectedIndex;
  bool get barVisibleForTest => _barVisible;
  Future<bool> handleBackForTest() => _handleBack();
  void onScrollForTest(ScrollDirection direction) =>
      _applyScrollDirection(direction);

  // ---------------------------------------------------------------------------
  // Build.
  // ---------------------------------------------------------------------------
  // [LOCAL-761] Lazy tab content. Every tab's Navigator is created eagerly (so
  // its GlobalKey, navigation stack, scroll position and map survive switching
  // away once the tab has been visited), but a tab's heavy root screen is not
  // built until the tab is first selected. This keeps the pre-761 contract that
  // a content screen's initState runs on tab entry, avoids constructing all
  // five screens at launch, and means the initial tab is the only screen built
  // up front (exactly as before: production always starts on Home).
  Widget _buildTabNavigator(int index) {
    if (!_visitedTabs.contains(index)) {
      // Not visited yet: an empty placeholder. The Navigator still mounts so
      // its key is live; the real root is generated on first visit.
      return const SizedBox.shrink();
    }
    return Navigator(
      key: _tabNavigatorKeys[index],
      onGenerateRoute: (settings) => MaterialPageRoute(
        settings: settings,
        builder: (_) => _buildTabRoot(index),
      ),
    );
  }

  /// True only when a system Back should be allowed to leave the app: we are on
  /// the Home tab and its Navigator has nothing to pop. In every other case we
  /// intercept Back and handle it in-app (pop the tab, or switch to Home).
  bool get _canPopApp {
    if (_selectedIndex != kHomeTab) return false;
    final nav = _tabNavigatorKeys[kHomeTab].currentState;
    return nav == null || !nav.canPop();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _canPopApp,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return; // the system already popped (Home root → exit).
        // Intercepted: handle Back inside the app (pop the tab, or go Home).
        _handleBack();
      },
      child: Scaffold(
        // The body is an IndexedStack of per-tab Navigators. The bar sits in
        // bottomNavigationBar, OUTSIDE the stack, so any screen pushed inside a
        // tab keeps it visible. A single NotificationListener drives auto-hide
        // for whatever scrollable is on top in any tab.
        body: NotificationListener<ScrollNotification>(
          onNotification: _onScrollNotification,
          child: IndexedStack(
            index: _selectedIndex,
            children: List.generate(kTabCount, _buildTabNavigator),
          ),
        ),
        bottomNavigationBar: AnimatedSlide(
          key: kMainBottomBarSlideKey,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeInOut,
          offset: _barVisible ? Offset.zero : const Offset(0, 1),
          child: AnimatedOpacity(
            duration: const Duration(milliseconds: 200),
            opacity: _barVisible ? 1 : 0,
            child: BottomNavigationBar(
              key: kMainBottomBarKey,
              type: BottomNavigationBarType.fixed,
              currentIndex: _selectedIndex,
              onTap: _onTabTapped,
              items: const [
                BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
                BottomNavigationBarItem(
                    icon: Icon(Icons.add), label: 'Generate Tour'),
                BottomNavigationBarItem(
                    icon: Icon(Icons.library_music), label: 'Listen'),
                BottomNavigationBarItem(
                    icon: Icon(Icons.local_cafe), label: 'Treats'),
                BottomNavigationBarItem(icon: Icon(Icons.info), label: 'About'),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
