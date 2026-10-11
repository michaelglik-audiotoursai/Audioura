import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';
import 'outbox_service.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Offline-first per-STOP thumbs (swipe) service.
///
/// LOCAL-670C: these per-stop thumbs used to live in their own queue and POST
/// to `/user/<id>/stop-feedback`, which failed offline (Michael: "today's
/// stop-feedback already fails offline. Move it into the outbox too."). They
/// now go through the single [OutboxService] as `thumb` items, so they share
/// the one durable queue, the connectivity/lifecycle sync triggers, the
/// exponential backoff and the 90-day expiry — and reach the server batched via
/// `POST /sync` when a connection returns.
///
/// D650 (Michael): a per-stop thumb is an INTERNAL signal — personalization and
/// stop-quality only, NEVER part of the tour's 1–10 score. The server keeps it
/// out of the tour score; this client only records the signal.
///
/// The public surface (recordSwipe/undoLastSwipe/queueLength/getPendingQueue/
/// flush/loadStopMetrics) is unchanged so [SwipeFeedbackWidget] and existing
/// callers keep working; only the storage/transport moved under the hood.
class StopFeedbackService {
  bool _testMode = false;

  /// Singleton instance
  static final StopFeedbackService _instance = StopFeedbackService._();
  factory StopFeedbackService() => _instance;
  StopFeedbackService._();

  /// Enable test mode (disables automatic network flush on the shared outbox).
  static void enableTestMode() {
    _instance._testMode = true;
    OutboxService.instance.enableTestMode();
  }

  /// Record a swipe (like=+1, dislike=-1) for a stop.
  ///
  /// Enqueues a `thumb` item in the shared outbox immediately (optimistic,
  /// durable). The outbox owns the flush. Never throws.
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

    // Resolve class distributions from stopMetrics or use neutral defaults.
    final classDetails = stopMetrics?['class_details'] ?? 0.333;
    final classHistoric = stopMetrics?['class_historic'] ?? 0.333;
    final classSocial = stopMetrics?['class_social'] ?? 0.333;
    final iCon = stopMetrics?['i_con'] ?? 3.0;

    await OutboxService.instance.enqueueThumb(
      userId: userId,
      tourId: tourId,
      stopIndex: stopIndex,
      swipe: swipe,
      extra: {
        if (jobId != null) 'job_id': jobId,
        'class_details': classDetails,
        'class_historic': classHistoric,
        'class_social': classSocial,
        'i_con': iCon,
      },
    );

    await DebugLogHelper.addDebugLog(
      'SWIPE: Queued ${swipe == 1 ? "LIKE" : "DISLIKE"} for stop $stopIndex '
      '(tour=$tourId) → outbox',
    );
  }

  /// Undo the most recent still-unsent swipe for a given tour+stop.
  ///
  /// Removes the matching `thumb` item from the outbox if it hasn't been sent
  /// yet. Returns true if an undo was performed.
  Future<bool> undoLastSwipe({
    required int stopIndex,
    required String tourId,
  }) async {
    final removed = await _removeMatchingThumb(stopIndex: stopIndex, tourId: tourId);
    await DebugLogHelper.addDebugLog(
      removed
          ? 'SWIPE: Undo for stop $stopIndex — removed from outbox (not yet sent)'
          : 'SWIPE: Undo for stop $stopIndex — already flushed, nothing to remove',
    );
    return removed;
  }

  /// Current count of pending thumbs in the outbox (diagnostics / testing).
  Future<int> get queueLength async {
    final items = await OutboxService.instance.pendingItems();
    return items.where((i) => i.type == 'thumb').length;
  }

  /// Pending thumbs as flat maps shaped like the legacy queue entries
  /// (stop_index/swipe/tour_id/…), for diagnostics / testing.
  Future<List<Map<String, dynamic>>> getPendingQueue() async {
    final items = await OutboxService.instance.pendingItems();
    return items
        .where((i) => i.type == 'thumb')
        .map((i) => {
              'client_uuid': i.clientUuid,
              'created_at': i.createdAt,
              ...i.payload,
            })
        .toList();
  }

  /// Force a flush of the shared outbox.
  Future<void> flush() async {
    if (_testMode) return;
    await OutboxService.instance.flush();
  }

  /// Load stop metrics from the tour's local directory.
  ///
  /// Looks for `stop_metrics.json` in the tour path. Returns null if not found.
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

  /// No-op kept for API compatibility (the shared outbox owns its own timers).
  void dispose() {}

  // ─── Private ───────────────────────────────────────────────────────────────

  /// Remove the most-recent still-pending thumb for (tour, stop) from the
  /// outbox storage directly. Returns true if one was removed.
  Future<bool> _removeMatchingThumb({
    required int stopIndex,
    required String tourId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('outbox_v1');
    if (raw == null || raw.isEmpty) return false;
    List<dynamic> list;
    try {
      list = jsonDecode(raw) as List<dynamic>;
    } catch (_) {
      return false;
    }
    for (int i = list.length - 1; i >= 0; i--) {
      final item = list[i];
      if (item is Map &&
          item['type'] == 'thumb' &&
          item['payload'] is Map &&
          item['payload']['tour_id'] == tourId &&
          item['payload']['stop_index'] == stopIndex) {
        list.removeAt(i);
        await prefs.setString('outbox_v1', jsonEncode(list));
        return true;
      }
    }
    return false;
  }
}
