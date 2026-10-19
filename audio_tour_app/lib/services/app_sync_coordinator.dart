import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';

import 'outbox_service.dart';
import 'community_tours_sync.dart';

/// Drives the offline outbox's sync triggers (LOCAL-670C) AND the community-
/// tours sync-on-open baseline (LOCAL-713 / D675 §4):
///   * on app START (when [start] is called),
///   * on app RESUME (lifecycle → resumed),
///   * on a CONNECTIVITY CHANGE that gains a usable connection.
///
/// Michael (2026-10-10): send to the server "only when it had connection".
/// This coordinator is the ONLY place the app watches connectivity; the
/// [OutboxService] owns the actual batching, ordering, backoff and expiry, and
/// [CommunityToursSync] owns the new-tours fetch + download + `since` advance,
/// so each sync policy stays testable without a device. Attaching the real
/// connectivity stream here (rather than inside those services) keeps them pure
/// and unit-testable.
class AppSyncCoordinator with WidgetsBindingObserver {
  AppSyncCoordinator._();
  static final AppSyncCoordinator instance = AppSyncCoordinator._();

  final Connectivity _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _started = false;

  /// Flush the outbox AND run the community-tours sync-on-open baseline. The
  /// community sync is self-gating (it checks connectivity + the per-community
  /// switches and only advances `since` on success), so it is safe to call on
  /// every trigger.
  void _syncAll() {
    unawaited(OutboxService.instance.flush());
    unawaited(CommunityToursSync.instance.run());
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

    _sub = _connectivity.onConnectivityChanged.listen((results) {
      if (_hasConnection(results)) {
        _syncAll();
      }
    });

    // App start: flush whatever accumulated offline since last run, and sync
    // the community tours.
    _syncAll();
  }

  /// Stop observing (e.g. in tests or teardown).
  void stop() {
    _sub?.cancel();
    _sub = null;
    if (_started) {
      WidgetsBinding.instance.removeObserver(this);
      _started = false;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _syncAll();
    }
  }

  /// True when at least one result is a real connection (not `none`).
  static bool _hasConnection(List<ConnectivityResult> results) {
    return results.any((r) => r != ConnectivityResult.none);
  }
}
