import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';

/// Records that the listener has FINISHED a stop and gates the per-TOUR rating
/// behind "heard at least 2 stops" (LOCAL-670B).
///
/// Michael (2026-10-10): "Can we not allow rating if people did not listen to
/// at least 2 stops, similar to Audible, where they politely say that the user
/// did not hear enough to rate the tour?"
///
/// A stop counts as LISTENED when its audio plays to ≥ 80% or to the end — the
/// player decides that and calls [recordListened]. We remember it LOCALLY, per
/// (tour, stop), so the UI can gate the rating prompt instantly and offline,
/// and we also POST it to the server (idempotent) so the server-side gate on
/// `POST /tour/<id>/rating` agrees:
///
///   POST /tour/<tour_id>/listened  { user_id, stop_index }  (idempotent)
///
/// This is deliberately separate from the per-STOP thumbs ([StopFeedbackService]
/// / swipe feedback), which are UNAFFECTED — you can always rate a stop you
/// heard. This only governs the whole-TOUR 1–10 rating.
class TourListenService {
  /// How many DISTINCT stops must be heard before a tour can be rated. Mirrors
  /// the server's REQUIRED_LISTENED_STOPS. A tour with fewer stops than this
  /// requires ALL of its stops instead (see [hasListenedEnough]).
  static const int requiredListenedStops = 2;

  /// Fraction of a stop's audio that counts as "listened" (≥ 80%).
  static const double listenedThreshold = 0.80;

  static String _key(String tourId) => 'listened_stops_$tourId';

  /// Record that [stopIndex] of [tourId] has been heard to the end.
  ///
  /// Stores it locally (deduplicated per stop) and best-effort POSTs it to the
  /// server. Never throws — a network failure still leaves the local record,
  /// so the UI gate works offline and the POST can be retried on a later stop.
  /// Returns the new local distinct-listened count.
  static Future<int> recordListened({
    required String tourId,
    required int stopIndex,
  }) async {
    if (stopIndex < 0) return listenedCountSyncFallback;
    final prefs = await SharedPreferences.getInstance();
    final key = _key(tourId);
    final current = prefs.getStringList(key) ?? <String>[];
    final token = stopIndex.toString();
    final alreadyKnown = current.contains(token);
    if (!alreadyKnown) {
      current.add(token);
      await prefs.setStringList(key, current);
    }

    // Best-effort server sync (idempotent server-side). Only numeric tour ids
    // reach the rating/listened endpoints; a local-path-only tour is tracked
    // locally and simply not synced.
    if (int.tryParse(tourId) != null) {
      unawaited(_postListened(prefs, tourId, stopIndex));
    }
    return current.length;
  }

  static Future<void> _postListened(
    SharedPreferences prefs,
    String tourId,
    int stopIndex,
  ) async {
    try {
      final userId = prefs.getString('user_id') ?? 'unknown';
      await Endpoints.post(
        Service.orchestrator,
        '/tour/$tourId/listened',
        body: {'user_id': userId, 'stop_index': stopIndex},
        timeout: const Duration(seconds: 10),
      );
    } on SocketException catch (_) {
      // offline — local record stands, gate still works
    } on TimeoutException catch (_) {
      // ignore
    } on http.ClientException catch (_) {
      // ignore
    } catch (_) {
      // never let a sync failure surface to the listener
    }
  }

  /// The number of DISTINCT stops heard on [tourId] (local record).
  static Future<int> listenedCount(String tourId) async {
    final prefs = await SharedPreferences.getInstance();
    return (prefs.getStringList(_key(tourId)) ?? const <String>[]).length;
  }

  /// Whether the per-TOUR rating is unlocked for [tourId].
  ///
  /// Needs [requiredListenedStops] distinct stops normally, but a tour with
  /// fewer stops than that needs ALL of them (so a 1-stop tour unlocks after
  /// its single stop). [totalStops] may be null/unknown, in which case the full
  /// threshold applies.
  static Future<bool> hasListenedEnough(
    String tourId, {
    int? totalStops,
  }) async {
    final heard = await listenedCount(tourId);
    return heard >= requiredThreshold(totalStops);
  }

  /// The distinct-stop count required for [totalStops]: min(2, totalStops),
  /// never below 1, defaulting to the full 2 when the length is unknown.
  static int requiredThreshold(int? totalStops) {
    if (totalStops == null || totalStops >= requiredListenedStops) {
      return requiredListenedStops;
    }
    return totalStops < 1 ? requiredListenedStops : totalStops;
  }

  /// Fallback used only when a negative index is passed (defensive); zero is a
  /// safe "nothing recorded".
  static const int listenedCountSyncFallback = 0;
}
