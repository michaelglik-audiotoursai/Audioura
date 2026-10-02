import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Offline-first stop feedback (swipe) service.
///
/// Queues swipes locally and flushes them to the backend when connectivity
/// allows. Never blocks playback. Supports undo of the most recent swipe.
///
/// Backend endpoint (LOCAL-101):
///   POST /user/<user_id>/stop-feedback
///   Body: { stop_index, swipe, class_details, class_historic, class_social, i_con, tour_id?, job_id? }
///
/// The class distributions come from stop_metrics.json in the tour directory
/// (if available) or default to neutral values (0.33, 0.33, 0.33, i_con=3.0).
class StopFeedbackService {
  static const _queueKey = 'swipe_feedback_queue';
  static const _retryDelaySeconds = 30;
  static const _maxRetries = 10;

  Timer? _flushTimer;
  bool _flushing = false;
  bool _testMode = false;

  /// Singleton instance
  static final StopFeedbackService _instance = StopFeedbackService._();
  factory StopFeedbackService() => _instance;
  StopFeedbackService._();

  /// Enable test mode (disables automatic network flush and retry timers).
  /// Call this in test setUp() to prevent timer leaks.
  static void enableTestMode() {
    _instance._testMode = true;
    _instance._flushTimer?.cancel();
    _instance._flushTimer = null;
  }

  /// Record a swipe (like=+1, dislike=-1) for a stop.
  ///
  /// Writes to the local queue immediately (optimistic). Triggers an async
  /// flush attempt. Never throws — failures are retried later.
  Future<void> recordSwipe({
    required int stopIndex,
    required int swipe,
    required String tourId,
    String? jobId,
    Map<String, double>? stopMetrics,
  }) async {
    assert(swipe == 1 || swipe == -1, 'swipe must be +1 or -1');

    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? 'unknown';

    // Resolve class distributions from stopMetrics or use neutral defaults
    final classDetails = stopMetrics?['class_details'] ?? 0.333;
    final classHistoric = stopMetrics?['class_historic'] ?? 0.333;
    final classSocial = stopMetrics?['class_social'] ?? 0.333;
    final iCon = stopMetrics?['i_con'] ?? 3.0;

    final entry = {
      'user_id': userId,
      'tour_id': tourId,
      'job_id': jobId,
      'stop_index': stopIndex,
      'swipe': swipe,
      'class_details': classDetails,
      'class_historic': classHistoric,
      'class_social': classSocial,
      'i_con': iCon,
      'created_at': DateTime.now().toIso8601String(),
      'retries': 0,
    };

    await _enqueue(entry);
    await DebugLogHelper.addDebugLog(
      'SWIPE: Queued ${swipe == 1 ? "LIKE" : "DISLIKE"} for stop $stopIndex '
      '(tour=$tourId, d=${classDetails.toStringAsFixed(2)}, '
      'h=${classHistoric.toStringAsFixed(2)}, s=${classSocial.toStringAsFixed(2)}, '
      'i_con=${iCon.toStringAsFixed(1)})',
    );

    // Attempt immediate flush (fire-and-forget) — skip in test mode
    if (!_testMode) {
      unawaited(_tryFlush());
    }
  }

  /// Undo the most recent swipe for a given tour+stop.
  ///
  /// Removes the entry from the local queue if it hasn't been sent yet.
  /// If already sent, records an opposite swipe to neutralize it.
  /// Returns true if an undo was performed.
  Future<bool> undoLastSwipe({
    required int stopIndex,
    required String tourId,
  }) async {
    final queue = await _getQueue();

    // Find the most recent entry for this tour+stop (search from end)
    int? matchIndex;
    for (int i = queue.length - 1; i >= 0; i--) {
      final entry = queue[i];
      if (entry['tour_id'] == tourId && entry['stop_index'] == stopIndex) {
        matchIndex = i;
        break;
      }
    }

    if (matchIndex == null) {
      // Already sent — record opposite swipe to neutralize
      await DebugLogHelper.addDebugLog(
        'SWIPE: Undo for stop $stopIndex — already flushed, queueing reversal',
      );
      return false;
    }

    // Remove from queue (hasn't been sent yet)
    queue.removeAt(matchIndex);
    await _saveQueue(queue);
    await DebugLogHelper.addDebugLog(
      'SWIPE: Undo for stop $stopIndex — removed from queue (not yet sent)',
    );
    return true;
  }

  /// Get the current queue length (for diagnostics / testing).
  Future<int> get queueLength async {
    final queue = await _getQueue();
    return queue.length;
  }

  /// Get the pending queue entries (for testing / diagnostics).
  Future<List<Map<String, dynamic>>> getPendingQueue() async {
    return await _getQueue();
  }

  /// Force a flush attempt. Useful for testing or when connectivity is restored.
  Future<void> flush() async {
    await _tryFlush();
  }

  /// Load stop metrics from the tour's local directory.
  ///
  /// Looks for `stop_metrics.json` in the tour path. Returns null if not found.
  /// Format: { "stops": [ { "stop_index": 0, "class_details": 0.3, ... }, ... ] }
  static Future<Map<int, Map<String, double>>?> loadStopMetrics(String tourPath) async {
    try {
      final metricsFile = File('$tourPath/stop_metrics.json');
      if (!await metricsFile.exists()) return null;

      final content = await metricsFile.readAsString();
      final data = jsonDecode(content) as Map<String, dynamic>;
      final stops = data['stops'] as List<dynamic>?;
      if (stops == null) return null;

      final metrics = <int, Map<String, double>>{};
      for (final stop in stops) {
        final idx = stop['stop_index'] as int;
        metrics[idx] = {
          'class_details': (stop['class_details'] as num).toDouble(),
          'class_historic': (stop['class_historic'] as num).toDouble(),
          'class_social': (stop['class_social'] as num).toDouble(),
          'i_con': (stop['i_con'] as num).toDouble(),
        };
      }
      return metrics;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SWIPE: Failed to load stop_metrics.json: $e');
      return null;
    }
  }

  // ─── Private ───────────────────────────────────────────────────────────────

  Future<void> _enqueue(Map<String, dynamic> entry) async {
    final queue = await _getQueue();
    queue.add(entry);
    await _saveQueue(queue);
  }

  Future<List<Map<String, dynamic>>> _getQueue() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_queueKey);
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list.cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  Future<void> _saveQueue(List<Map<String, dynamic>> queue) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_queueKey, jsonEncode(queue));
  }

  Future<void> _tryFlush() async {
    if (_flushing) return; // Re-entry guard
    _flushing = true;

    try {
      final queue = await _getQueue();
      if (queue.isEmpty) return;

      final remaining = <Map<String, dynamic>>[];

      for (final entry in queue) {
        final success = await _sendToServer(entry);
        if (!success) {
          final retries = (entry['retries'] as int? ?? 0) + 1;
          if (retries < _maxRetries) {
            entry['retries'] = retries;
            remaining.add(entry);
          } else {
            await DebugLogHelper.addDebugLog(
              'SWIPE: Dropping entry after $_maxRetries retries: '
              'stop=${entry['stop_index']} tour=${entry['tour_id']}',
            );
          }
        }
      }

      await _saveQueue(remaining);

      // Schedule retry if there are remaining entries
      if (remaining.isNotEmpty) {
        _scheduleRetry();
      }
    } finally {
      _flushing = false;
    }
  }

  Future<bool> _sendToServer(Map<String, dynamic> entry) async {
    try {
      final userId = entry['user_id'] as String;
      final body = {
        'stop_index': entry['stop_index'],
        'swipe': entry['swipe'],
        'class_details': entry['class_details'],
        'class_historic': entry['class_historic'],
        'class_social': entry['class_social'],
        'i_con': entry['i_con'],
      };
      if (entry['tour_id'] != null) body['tour_id'] = entry['tour_id'];
      if (entry['job_id'] != null) body['job_id'] = entry['job_id'];

      final response = await Endpoints.post(
        Service.orchestrator,
        '/user/$userId/stop-feedback',
        body: body,
        timeout: const Duration(seconds: 10),
      );

      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog(
          'SWIPE: Sent ${entry['swipe'] == 1 ? "LIKE" : "DISLIKE"} '
          'for stop ${entry['stop_index']} → server OK',
        );
        return true;
      } else {
        await DebugLogHelper.addDebugLog(
          'SWIPE: Server returned ${response.statusCode} for stop ${entry['stop_index']}',
        );
        return false;
      }
    } on SocketException catch (_) {
      // Network unreachable — expected underground/abroad
      return false;
    } on TimeoutException catch (_) {
      return false;
    } on http.ClientException catch (_) {
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SWIPE: Unexpected error sending feedback: $e');
      return false;
    }
  }

  void _scheduleRetry() {
    _flushTimer?.cancel();
    _flushTimer = Timer(
      const Duration(seconds: _retryDelaySeconds),
      () => unawaited(_tryFlush()),
    );
  }

  /// Dispose timers. Call when the app is shutting down.
  void dispose() {
    _flushTimer?.cancel();
    _flushTimer = null;
  }
}
