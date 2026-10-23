import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';

import 'outbox_service.dart';
import 'community_tours_sync.dart';
import 'foreground_community_messages.dart';

/// Drives the offline outbox's sync triggers (LOCAL-670C) AND the community-
/// tours sync-on-open baseline (LOCAL-713 / D675 §4):
///   * on app START (when [start] is called),
///   * on app RESUME (lifecycle → resumed),
///   * on a CONNECTIVITY CHANGE that gains a usable connection,
///   * [LOCAL-750 C] every 5 minutes WHILE the app is in the foreground, and
///   * [LOCAL-750 C] on demand when the Communities hub or a community page
///     opens (via [syncNow]).
///
/// Michael (2026-10-10): send to the server "only when it had connection".
/// This coordinator is the ONLY place the app watches connectivity; the
/// [OutboxService] owns the actual batching, ordering, backoff and expiry, and
/// [CommunityToursSync] owns the new-tours fetch + download + `since` advance,
/// so each sync policy stays testable without a device. Attaching the real
/// connectivity stream here (rather than inside those services) keeps them pure
/// and unit-testable.
///
/// Overlap: [CommunityToursSync.run] is self-guarding (a run in flight is a
/// no-op), so none of these triggers can start a second community sync on top of
/// a running one — the 5-minute timer in particular just no-ops if a sync is
/// already going.
class AppSyncCoordinator with WidgetsBindingObserver {
  AppSyncCoordinator._();
  static final AppSyncCoordinator instance = AppSyncCoordinator._();

  final Connectivity _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _started = false;

  /// [LOCAL-750 C] How often the foreground timer re-runs the community sync so
  /// new/updated tours arrive without leaving and re-entering the app.
  static const Duration foregroundSyncInterval = Duration(minutes: 5);

  /// The foreground-only periodic sync timer. Created on resume / start, torn
  /// down on pause so it never fires in the background (where the WorkManager /
  /// BGTask path owns syncing).
  Timer? _foregroundTimer;

  /// Flush the outbox AND run the community-tours sync-on-open baseline. The
  /// community sync is self-gating (it checks connectivity + the per-community
  /// switches and only advances `since` on success), so it is safe to call on
  /// every trigger.
  void _syncAll() {
    unawaited(OutboxService.instance.flush());
    unawaited(CommunityToursSync.instance.run());
  }

  /// [LOCAL-750 C] Run the community sync NOW (e.g. the Communities hub or a
  /// community page just opened). Self-gating + overlap-safe like every other
  /// trigger, so a screen can call it freely on open.
  void syncNow() {
    _syncAll();
  }

  /// [LOCAL-750 C] (Re)start the 5-minute foreground timer. Cancels any existing
  /// one first so there is never more than a single timer. Each tick only runs
  /// a sync when the app is still in the foreground; a stray tick after a pause
  /// is ignored (defence-in-depth — the timer is also cancelled on pause).
  void _startForegroundTimer() {
    _foregroundTimer?.cancel();
    _foregroundTimer = Timer.periodic(foregroundSyncInterval, (_) {
      if (shouldRunForegroundTick(
          isForeground: ForegroundCommunityMessages.instance.isForeground)) {
        _syncAll();
      }
    });
  }

  /// PURE: a foreground timer tick runs a sync only while the app is in the
  /// foreground. (Overlap with an in-flight sync is prevented separately by
  /// [CommunityToursSync.run]'s own self-guard, so a tick that fires during a
  /// running sync simply no-ops inside run().) Exposed for the unit test.
  static bool shouldRunForegroundTick({required bool isForeground}) =>
      isForeground;

  void _stopForegroundTimer() {
    _foregroundTimer?.cancel();
    _foregroundTimer = null;
  }

  /// Begin observing lifecycle + connectivity and do an immediate start-up
  /// flush. Safe to call more than once (idempotent).
  Future<void> start() async {
    if (_started) {
      _syncAll();
      return;
    }
    _started = true;

    WidgetsBinding.instance.addObserver(this);
    // The app is on screen at start-up.
    ForegroundCommunityMessages.instance.setForeground(true);

    _sub = _connectivity.onConnectivityChanged.listen((results) {
      if (_hasConnection(results)) {
        _syncAll();
      }
    });

    // App start: flush whatever accumulated offline since last run, and sync
    // the community tours.
    _syncAll();
    // [LOCAL-750 C] Keep syncing every 5 minutes while the app is up.
    _startForegroundTimer();
  }

  /// Stop observing (e.g. in tests or teardown).
  void stop() {
    _sub?.cancel();
    _sub = null;
    _stopForegroundTimer();
    if (_started) {
      WidgetsBinding.instance.removeObserver(this);
      _started = false;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // [LOCAL-750 C] Back in the foreground: messages show in-app again, and
      // the 5-minute timer resumes.
      ForegroundCommunityMessages.instance.setForeground(true);
      _syncAll();
      _startForegroundTimer();
    } else {
      // paused / inactive / detached / hidden → background: messages go to the
      // system notification and the foreground timer stops.
      ForegroundCommunityMessages.instance.setForeground(false);
      _stopForegroundTimer();
    }
  }

  /// True when at least one result is a real connection (not `none`).
  static bool _hasConnection(List<ConnectivityResult> results) {
    return results.any((r) => r != ConnectivityResult.none);
  }
}
