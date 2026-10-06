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
import '../renewal_logic.dart';
import '../widgets/renewal_sheet.dart';

class MainScreen extends StatefulWidget {
  final int initialTab;
  const MainScreen({super.key, this.initialTab = 0});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> with WidgetsBindingObserver {
  late int _selectedIndex;
  int _listenTabVersion = 0;

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

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    BackgroundService.stopBackgroundMonitoring();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      BackgroundService.startBackgroundMonitoring();
      // LOCAL-598 D2: app-open fires on resume too, not just launch.
      _runAppOpenEntitlementsCheck();
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
