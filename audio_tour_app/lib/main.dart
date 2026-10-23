import 'package:flutter/material.dart';
import 'services/iap_service.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';

import 'screens/main_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/informational_notice_screen.dart';
import 'services/app_sync_coordinator.dart';
import 'services/community_background.dart';
import 'services/community_notifications.dart';
import 'services/community_tours_sync.dart';
import 'services/deep_link_service.dart';
import 'package:workmanager/workmanager.dart';

class MainScreenWithTreatsTab extends StatelessWidget {
  const MainScreenWithTreatsTab({super.key});

  @override
  Widget build(BuildContext context) {
    return const MainScreen(initialTab: 3); // Treats tab index
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  print('=== AUDIOTOURS DEV v1.2.9+61 STARTING ===');
  
  // Clear old article cache to fix 404 errors
  try {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('cached_articles');
    print('🗑️ Cleared old article cache to fix 404 errors');

    // SECURITY (wdvrday4pk): one-time purge of the persisted debug log.
    // Builds before 2.3.2 wrote plaintext credentials and the AES key into
    // SharedPreferences 'debug_logs'. Any device that ran an affected build
    // still has those secrets on disk. Clear them once on first launch of the
    // fixed version. Keyed so it runs exactly once (and again if we ever bump
    // the guard key for a future incident).
    const purgeFlag = 'debug_logs_security_purged_v2';
    if (!(prefs.getBool(purgeFlag) ?? false)) {
      await prefs.remove('debug_logs');
      await prefs.setBool(purgeFlag, true);
      print('🔒 Purged legacy debug_logs (one-time security cleanup)');
    }
  } catch (e) {
    print('Warning: Could not clear cache: $e');
  }
  
  // Initialize InAppWebView (debugging enabled by default in debug mode)

  // [LOCAL-670C] Start the offline-outbox sync coordinator: flush now (app
  // start) and whenever connectivity returns or the app resumes. Never blocks
  // startup — failures are retried by the outbox's own backoff.
  // [LOCAL-746] Surface the ONE "<tour> was updated by the organiser." heads-up
  // when the sync-on-open re-downloads a held community tour the organiser
  // edited — a quiet local notification (same channel as the new-tours one).
  CommunityToursSync.onRefreshMessage = (message) {
    unawaited(CommunityNotifications.postTourUpdated(message));
  };
  // [LOCAL-748] Surface the ONE "New tour in <community>: <tour>" heads-up when
  // the sync finds a new tour in a community the member belongs to (never for
  // the member's own tours; once per tour).
  CommunityToursSync.onNewTourAnnouncement = (announcement, message) {
    unawaited(CommunityNotifications.postNewTourAvailable(message));
  };
  unawaited(AppSyncCoordinator.instance.start());

  // [LOCAL-714 / D675 part 2] Register the background community-tours sync
  // (Android WorkManager periodic / iOS BGTaskScheduler app-refresh). The
  // worker runs the SAME planner + downloader as the sync on open. The periodic
  // task is only meaningful once a member opts a community into auto-download
  // (the join question), but registering it here is harmless (nothing to do
  // when every switch is OFF) and idempotent. Never blocks startup.
  unawaited(() async {
    try {
      await Workmanager().initialize(callbackDispatcher);
      await registerCommunitySyncTask();
    } catch (_) {
      // A platform without WorkManager (desktop/web/test) simply gets no task.
    }
  }());

  // [LOCAL-709 / D671] Capture cold/warm-start share links (App Links /
  // Universal Links) as early as possible. The code is parked in
  // PendingShareSearch; MainScreen switches to Home and Home runs the search
  // through the same path a pasted code takes. Never blocks startup.
  unawaited(DeepLinkService.instance.init());

  // [iOS IAP] StoreKit 2 must be enabled before InAppPurchase is first used,
  // and the purchase listener must run from launch. Bounded inside.
  try {
    await IapService.initAtStartup().timeout(const Duration(seconds: 6));
  } catch (_) {}
  runApp(const AudioTourApp());
}

class AudioTourApp extends StatefulWidget {
  const AudioTourApp({super.key});

  @override
  State<AudioTourApp> createState() => _AudioTourAppState();
}

class _AudioTourAppState extends State<AudioTourApp> {
  bool _onboardingComplete = true; // assume complete until loaded
  // [LOCAL-726 item 2] The first-run informational notice. Assume seen until
  // loaded so we never flash it on a hot reload before the real value arrives.
  bool _noticeSeen = true;

  @override
  void initState() {
    super.initState();
    _checkOnboarding();
  }

  Future<void> _checkOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    final complete = prefs.getBool('onboarding_complete') ?? false;
    final noticeSeen = await InformationalNoticeScreen.seen();
    if (mounted) setState(() {
      _onboardingComplete = complete;
      _noticeSeen = noticeSeen;
    });
  }

  @override
  Widget build(BuildContext context) {
    // Flow: onboarding (new installs) → informational notice (new installs AND
    // existing installs that have not yet seen it) → the app. An existing
    // install already has onboarding_complete=true, so it falls straight to the
    // notice once, then never again (the ack key is set on "Got it").
    final Widget home;
    if (!_onboardingComplete) {
      home = OnboardingScreen(onComplete: () {
        setState(() { _onboardingComplete = true; });
      });
    } else if (!_noticeSeen) {
      home = InformationalNoticeScreen(onAcknowledged: () {
        setState(() { _noticeSeen = true; });
      });
    } else {
      home = const MainScreen();
    }
    return MaterialApp(
      title: 'Audioura',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: home,
      routes: {
        '/treats': (context) => const MainScreenWithTreatsTab(),
      },
    );
  }
}