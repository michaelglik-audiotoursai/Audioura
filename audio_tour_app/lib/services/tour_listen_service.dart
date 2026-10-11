import 'dart:async';
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'outbox_service.dart';

/// Records that the listener has GENUINELY listened to a stop and gates the
/// per-TOUR rating behind "heard at least 2 stops" (LOCAL-670B, now verified
/// locally and offline per LOCAL-670C).
///
/// Michael (2026-10-10): tours play fully offline, so the "listened" fact and
/// the rating gate must both work with NO server. A stop is marked listened by
/// the player once [PlaybackAccumulator] confirms ≥ 80% of its audio was really
/// PLAYED (seeking/scrubbing does not count) or the end was reached after ≥ 80%
/// was played. We persist that fact LOCALLY, per (tour, stop), WITH A TIMESTAMP,
/// in the same shared storage the app already uses — so the rating prompt gates
/// instantly and offline — and we enqueue a `listened` item in the [OutboxService]
/// so the server learns of it (idempotently) when a connection returns.
///
/// Storage format (per tour, key `listened_stops_v2_<tourId>`): a JSON object
/// mapping the stop index (as a string) to the ISO-8601 UTC timestamp it was
/// first verified listened:  {"0":"2026-10-11T01:02:03.000Z","3":"..."}.
/// A legacy 670B list under `listened_stops_<tourId>` (just the indices) is read
/// and migrated forward on first access so an app UPDATE never loses a record.
///
/// This is deliberately separate from the per-STOP thumbs
/// ([StopFeedbackService]); this only governs the whole-TOUR 1–10 rating.
class TourListenService {
  /// How many DISTINCT stops must be heard before a tour can be rated. Mirrors
  /// the server's REQUIRED_LISTENED_STOPS. A tour with fewer stops than this
  /// requires ALL of its stops instead (see [hasListenedEnough]).
  static const int requiredListenedStops = 2;

  /// Fraction of a stop's audio that counts as "listened" (≥ 80%).
  static const double listenedThreshold = 0.80;

  static String _keyV2(String tourId) => 'listened_stops_v2_$tourId';
  static String _keyLegacy(String tourId) => 'listened_stops_$tourId';

  /// Record that [stopIndex] of [tourId] has been genuinely listened to.
  ///
  /// Stores it locally with a timestamp (deduplicated per stop — the first time
  /// wins) and enqueues an idempotent `listened` item in the outbox. Never
  /// throws — a storage or queue hiccup still leaves the UI gate working.
  /// Returns the new local distinct-listened count.
  static Future<int> recordListened({
    required String tourId,
    required int stopIndex,
    DateTime? at,
  }) async {
    if (stopIndex < 0) return 0;
    final prefs = await SharedPreferences.getInstance();
    final records = await _load(prefs, tourId);
    final token = stopIndex.toString();
    final isNew = !records.containsKey(token);
    if (isNew) {
      final ts = (at ?? DateTime.now()).toUtc().toIso8601String();
      records[token] = ts;
      await prefs.setString(_keyV2(tourId), jsonEncode(records));

      // Enqueue for sync only for server-known (numeric) tour ids; a
      // local-path-only tour is tracked locally and simply not synced. The
      // outbox owns all network I/O, backoff and ordering (listens before the
      // rating that depends on them).
      if (int.tryParse(tourId) != null) {
        final userId = prefs.getString('user_id') ?? 'unknown';
        await OutboxService.instance.enqueueListened(
          userId: userId,
          tourId: tourId,
          stopIndex: stopIndex,
          createdAt: at,
        );
      }
    }
    return records.length;
  }

  /// The number of DISTINCT stops heard on [tourId] (local record).
  static Future<int> listenedCount(String tourId) async {
    final prefs = await SharedPreferences.getInstance();
    final records = await _load(prefs, tourId);
    return records.length;
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

  /// Load the per-stop listen records for [tourId], migrating any legacy 670B
  /// index-only list forward into the v2 timestamped map on first access.
  static Future<Map<String, String>> _load(
    SharedPreferences prefs,
    String tourId,
  ) async {
    final rawV2 = prefs.getString(_keyV2(tourId));
    if (rawV2 != null && rawV2.isNotEmpty) {
      try {
        final decoded = jsonDecode(rawV2);
        if (decoded is Map) {
          return decoded.map((k, v) => MapEntry('$k', '$v'));
        }
      } catch (_) {
        // fall through to legacy / empty
      }
    }

    // Legacy 670B record: a StringList of stop indices, no timestamps. Migrate
    // it forward so an app update preserves the listened facts. We stamp the
    // migration time (the original listen time is unknown) — good enough for
    // the gate, which only counts distinct stops.
    final legacy = prefs.getStringList(_keyLegacy(tourId));
    if (legacy != null && legacy.isNotEmpty) {
      final now = DateTime.now().toUtc().toIso8601String();
      final migrated = <String, String>{};
      for (final s in legacy) {
        final n = int.tryParse(s);
        if (n != null && n >= 0) migrated['$n'] = now;
      }
      if (migrated.isNotEmpty) {
        await prefs.setString(_keyV2(tourId), jsonEncode(migrated));
      }
      return migrated;
    }

    return <String, String>{};
  }
}
