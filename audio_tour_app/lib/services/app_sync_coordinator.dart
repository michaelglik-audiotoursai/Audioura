import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';

import 'outbox_service.dart';

/// Drives the offline outbox's sync triggers (LOCAL-670C):
///   * on app START (when [start] is called),
///   * on app RESUME (lifecycle → resumed),
///   * on a CONNECTIVITY CHANGE that gains a usable connection.
///
/// Michael (2026-10-10): send to the server "only when it had connection".
/// This coordinator is the ONLY place the app watches connectivity; the
/// [OutboxService] owns the actual batching, ordering, backoff and expiry, so
/// the sync policy stays testable without a device. Attaching the real
/// connectivity stream here (rather than inside the outbox) keeps the outbox a
/// pure, plugin-free, unit-testable class.
class AppSyncCoordinator with WidgetsBindingObserver {
  AppSyncCoordinator._();
  static final AppSyncCoordinator instance = AppSyncCoordinator._();

  final Connectivity _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _started = false;

  /// Begin observing lifecycle + connectivity and do an immediate start-up
  /// flush. Safe to call more than once (idempotent).
  Future<void> start() async {
    if (_started) {
      unawaited(OutboxService.instance.flush());
      return;
    }
    _started = true;

    WidgetsBinding.instance.addObserver(this);

    _sub = _connectivity.onConnectivityChanged.listen((results) {
      if (_hasConnection(results)) {
        unawaited(OutboxService.instance.flush());
      }
    });

    // App start: flush whatever accumulated offline since last run.
    unawaited(OutboxService.instance.flush());
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
      unawaited(OutboxService.instance.flush());
    }
  }

  /// True when at least one result is a real connection (not `none`).
  static bool _hasConnection(List<ConnectivityResult> results) {
    return results.any((r) => r != ConnectivityResult.none);
  }
}
