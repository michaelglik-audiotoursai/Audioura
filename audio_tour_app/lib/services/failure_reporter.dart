import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/endpoints.dart';

/// [LOCAL-785 / D723] The ONE place the app records a failure.
///
/// Michael (D723): record every failure so we can later tell OUR bug from the
/// user's mistake. Today an app failure vanishes — a snackbar shows and nothing
/// is kept. `FailureReporter.instance.report(...)` sends the failure to the
/// server's `/client-failure` endpoint (user-api), which stores it in
/// failure_events beside the server failures for failure_report.py.
///
/// HARD RULES (why this class is shaped the way it is):
///   * Sending is ALWAYS in the background and NEVER blocks the UI or throws
///     into the caller. `report()` returns immediately; the network happens in
///     a fire-and-forget future, and every path is wrapped.
///   * Failures are QUEUED OFFLINE (SharedPreferences, up to 50, FIFO) when the
///     send fails, and flushed later (on the next report, or `flush()` at app
///     start / resume). The queue is capped so a long offline spell can't grow
///     without bound — the oldest reports are dropped first.
///   * Uncaught errors (FlutterError.onError / PlatformDispatcher.onError) are
///     THROTTLED to 5 per minute so an error loop cannot spam the server; the
///     throttle applies ONLY to the uncaught-error path, not to the deliberate
///     one-shot reports from error dialogs/snackbars and the known silent
///     failures (those are rare and each one matters).
class FailureReporter {
  FailureReporter._();
  static final FailureReporter instance = FailureReporter._();

  /// SharedPreferences key for the offline queue (list of JSON strings).
  @visibleForTesting
  static const String queueKey = 'failure_report_queue';

  /// Max reports held offline. Oldest dropped first (FIFO) when exceeded.
  static const int maxQueue = 50;

  /// Uncaught-error throttle: at most this many in [_throttleWindow].
  static const int _throttleMax = 5;
  static const Duration _throttleWindow = Duration(minutes: 1);
  final List<DateTime> _uncaughtTimes = <DateTime>[];

  /// Cached app version (name+build), resolved once.
  String? _appVersion;

  /// Test seam: when set, used instead of the real HTTP POST. Returns true on
  /// a successful "send" (so the report is NOT re-queued).
  @visibleForTesting
  Future<bool> Function(Map<String, dynamic> body)? sendOverride;

  /// Reset throttle + cached state (tests only).
  @visibleForTesting
  void resetForTest() {
    _uncaughtTimes.clear();
    _appVersion = null;
    sendOverride = null;
  }

  /// Report a failure the app is already handling (an error dialog/snackbar for
  /// a tour/download/save/translate/play/purchase, or a known silent failure).
  ///
  /// [surface] is where it happened ('download', 'translate', 'play', ...),
  /// [errorCode]/[message] describe it, [httpStatus] is set for a wire failure.
  /// Returns immediately; the send happens in the background. NEVER throws.
  void report({
    required String surface,
    String? errorCode,
    String? message,
    String? exceptionType,
    int? httpStatus,
    String? requestText,
    String? tourId,
    String? frames,
  }) {
    // Fire-and-forget: build + enqueue + flush off the UI path.
    unawaited(_reportAsync(
      surface: surface,
      errorCode: errorCode,
      message: message,
      exceptionType: exceptionType,
      httpStatus: httpStatus,
      requestText: requestText,
      tourId: tourId,
      frames: frames,
    ));
  }

  /// Awaitable version of [report] for tests: completes after the report has
  /// been sent (or queued) and the queue has been flushed. Behaviour is
  /// identical to [report]; only the awaitability differs.
  @visibleForTesting
  Future<void> reportAndWaitForTest({
    required String surface,
    String? errorCode,
    String? message,
    String? exceptionType,
    int? httpStatus,
    String? requestText,
    String? tourId,
    String? frames,
  }) {
    return _reportAsync(
      surface: surface,
      errorCode: errorCode,
      message: message,
      exceptionType: exceptionType,
      httpStatus: httpStatus,
      requestText: requestText,
      tourId: tourId,
      frames: frames,
    );
  }

  /// Report an UNCAUGHT error (FlutterError.onError / PlatformDispatcher). Same
  /// as [report] but throttled to [_throttleMax] per [_throttleWindow] so an
  /// error loop cannot flood the server. Dropped reports are simply not sent
  /// (an error loop is one failure, not hundreds).
  void reportUncaught(Object error, StackTrace? stack, {String surface = 'uncaught'}) {
    if (!_allowUncaught()) return;
    report(
      surface: surface,
      exceptionType: error.runtimeType.toString(),
      message: error.toString(),
      frames: _topFrames(stack),
    );
  }

  bool _allowUncaught() {
    final now = DateTime.now();
    _uncaughtTimes.removeWhere((t) => now.difference(t) > _throttleWindow);
    if (_uncaughtTimes.length >= _throttleMax) return false;
    _uncaughtTimes.add(now);
    return true;
  }

  static String? _topFrames(StackTrace? stack, {int max = 8}) {
    if (stack == null) return null;
    final lines = stack.toString().split('\n')
        .where((l) => l.trim().isNotEmpty)
        .take(max)
        .toList();
    return lines.isEmpty ? null : lines.join('\n');
  }

  Future<void> _reportAsync({
    required String surface,
    String? errorCode,
    String? message,
    String? exceptionType,
    int? httpStatus,
    String? requestText,
    String? tourId,
    String? frames,
  }) async {
    try {
      final body = await _buildBody(
        surface: surface,
        errorCode: errorCode,
        message: message,
        exceptionType: exceptionType,
        httpStatus: httpStatus,
        requestText: requestText,
        tourId: tourId,
        frames: frames,
      );
      // Try to send this one; if it fails, queue it. Either way, attempt to
      // drain any previously-queued reports.
      final sent = await _send(body);
      if (!sent) {
        await _enqueue(body);
      }
      await flush();
    } catch (_) {
      // A failure in the failure reporter must never surface. Best-effort only.
    }
  }

  Future<Map<String, dynamic>> _buildBody({
    required String surface,
    String? errorCode,
    String? message,
    String? exceptionType,
    int? httpStatus,
    String? requestText,
    String? tourId,
    String? frames,
  }) async {
    String? userId;
    String? track;
    try {
      final prefs = await SharedPreferences.getInstance();
      userId = prefs.getString('user_id');
    } catch (_) {}
    try {
      track = await Endpoints.cloudTrack();
    } catch (_) {}
    final version = await _resolveAppVersion();
    final platform = _platformName();

    // Cap message/frames/request the same way the server does (<= 8 KB body).
    final body = <String, dynamic>{
      'surface': surface,
      'platform': platform,
      if (userId != null && userId.isNotEmpty) 'user_id': userId,
      if (version != null) 'app_version': version,
      if (track != null) 'track': track,
      if (errorCode != null) 'error_code': _cap(errorCode, 128),
      if (message != null) 'message': _cap(message, 2000),
      if (exceptionType != null) 'exception_type': _cap(exceptionType, 128),
      if (httpStatus != null) 'http_status': httpStatus,
      if (requestText != null) 'request_text': _cap(requestText, 2000),
      if (tourId != null) 'tour_id': _cap(tourId, 64),
      if (frames != null) 'frames': _cap(frames, 2000),
    };
    return body;
  }

  static String _cap(String s, int max) => s.length <= max ? s : s.substring(0, max);

  static String _platformName() {
    try {
      if (Platform.isAndroid) return 'android';
      if (Platform.isIOS) return 'ios';
      return Platform.operatingSystem;
    } catch (_) {
      return 'unknown';
    }
  }

  Future<String?> _resolveAppVersion() async {
    if (_appVersion != null) return _appVersion;
    try {
      final info = await PackageInfo.fromPlatform();
      _appVersion = '${info.version}+${info.buildNumber}';
    } catch (_) {
      _appVersion = null;
    }
    return _appVersion;
  }

  /// Send one report. Returns true on success (HTTP 2xx). Never throws.
  Future<bool> _send(Map<String, dynamic> body) async {
    if (sendOverride != null) {
      try {
        return await sendOverride!(body);
      } catch (_) {
        return false;
      }
    }
    try {
      final resp = await Endpoints.post(
        Service.userDb, '/client-failure',
        body: body,
        timeout: const Duration(seconds: 10),
      );
      return resp.statusCode >= 200 && resp.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  Future<void> _enqueue(Map<String, dynamic> body) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final queue = prefs.getStringList(queueKey) ?? <String>[];
      queue.add(jsonEncode(body));
      // FIFO cap: drop the OLDEST when over the limit.
      while (queue.length > maxQueue) {
        queue.removeAt(0);
      }
      await prefs.setStringList(queueKey, queue);
    } catch (_) {}
  }

  /// Drain the offline queue, sending oldest-first. A report that fails to send
  /// is kept (and the drain stops, to preserve order and avoid a tight loop
  /// against a down server). Safe to call often; never throws.
  Future<void> flush() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      var queue = prefs.getStringList(queueKey) ?? <String>[];
      if (queue.isEmpty) return;
      final remaining = <String>[];
      var stillOffline = false;
      for (var i = 0; i < queue.length; i++) {
        if (stillOffline) {
          remaining.add(queue[i]);
          continue;
        }
        Map<String, dynamic>? body;
        try {
          final decoded = jsonDecode(queue[i]);
          body = decoded is Map<String, dynamic> ? decoded : null;
        } catch (_) {
          body = null; // drop an unparseable entry
        }
        if (body == null) continue;
        final sent = await _send(body);
        if (!sent) {
          stillOffline = true;
          remaining.add(queue[i]);
        }
      }
      await prefs.setStringList(queueKey, remaining);
    } catch (_) {}
  }

  /// Current offline-queue length (tests / diagnostics).
  @visibleForTesting
  Future<int> queueLength() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return (prefs.getStringList(queueKey) ?? const <String>[]).length;
    } catch (_) {
      return 0;
    }
  }

  /// Install the global uncaught-error hooks. Call once from main(). Preserves
  /// any existing FlutterError.onError so we add to, not replace, Flutter's
  /// default (red-screen / console) handling.
  void installGlobalHandlers() {
    final previous = FlutterError.onError;
    FlutterError.onError = (FlutterErrorDetails details) {
      try {
        reportUncaught(details.exception, details.stack, surface: 'flutter_error');
      } catch (_) {}
      if (previous != null) previous(details);
    };
    // Dart-level uncaught async errors (outside the Flutter framework).
    PlatformDispatcher.instance.onError = (Object error, StackTrace stack) {
      try {
        reportUncaught(error, stack, surface: 'platform_dispatcher');
      } catch (_) {}
      return false; // false = let the error continue to the default handler
    };
  }
}
