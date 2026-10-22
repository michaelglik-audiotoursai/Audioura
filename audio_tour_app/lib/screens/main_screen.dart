import 'package:flutter/material.dart';
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

class MainScreen extends StatefulWidget {
  final int initialTab;
  const MainScreen({super.key, this.initialTab = 0});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> with WidgetsBindingObserver {
  late int _selectedIndex;
  int _listenTabVersion = 0;

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
    // (optionally opening one tour). Switch to index 2 exactly as a
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
    if (_selectedIndex != 0 && mounted) {
      setState(() => _selectedIndex = 0);
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
      _selectedIndex = 2;
    });
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
    if (_selectedIndex != 0) return;
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
      if (!mounted || _selectedIndex != 0) return;

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
      // Refresh Home, My Tours, or Treats screen when app is resumed
      if (_selectedIndex == 0 || _selectedIndex == 2 || _selectedIndex == 3) {
        if (_selectedIndex == 2) _listenTabVersion++; // NF10: force Listen reload on resume
        setState(() {});
      }
    }
  }

  Future<void> _initializeNotifications() async {
    await NotificationService.initialize((NotificationResponse response) {
      // Navigate to My Tours tab when a notification is tapped
      setState(() {
        _listenTabVersion++; // NF11: force Listen reload (background-generated tour)
        _selectedIndex = 2;
      });
    });
  }

  // Returns a FRESH widget on every build. Switching tabs swaps the body child
  // to a different widget type, so Flutter disposes the outgoing screen's State
  // and runs the incoming screen's initState. That re-run of initState is THE
  // mechanism that makes Tours <-> Audio mode switching work: HomeScreen,
  // TourGeneratorScreen, and MyToursScreen all re-read 'app_mode' from
  // SharedPreferences in their initState/_loadAppMode.
  //
  // DO NOT wrap this in IndexedStack. IndexedStack keeps every screen mounted
  // permanently, initState runs only once at launch, and a mode change made in
  // the About tab is never picked up. That was the v1.2.9+59/+60 regression.
  Widget _buildBody() {
    switch (_selectedIndex) {
      case 1:
        return const TourGeneratorScreen();
      case 2:
        return MyToursScreen(key: ValueKey(_listenTabVersion));
      case 3:
        return const TreatsScreen();
      case 4:
        return const AboutScreen();
      default:
        return const HomeScreen();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _buildBody(),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: _selectedIndex,
        onTap: (index) {
          if (index == 2) _listenTabVersion++;
          setState(() => _selectedIndex = index);
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.add), label: 'Generate Tour'),
          BottomNavigationBarItem(icon: Icon(Icons.library_music), label: 'Listen'),
          BottomNavigationBarItem(icon: Icon(Icons.local_cafe), label: 'Treats'),
          BottomNavigationBarItem(icon: Icon(Icons.info), label: 'About'),
        ],
      ),
    );
  }
}
