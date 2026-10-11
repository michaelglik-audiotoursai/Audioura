import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';
import 'outbox_service.dart';

/// Per-TOUR 1–10 rating (LOCAL-670), now offline-first (LOCAL-670C).
///
/// Backend (orchestrator, port 5002):
///   POST /tour/<tour_id>/rating  { user_id, rating }  → { score, count, label }
///   GET  /tour/<tour_id>/rating                       → { score, count, label }
///   (and, batched offline, via the outbox → POST /sync)
///
/// One rating per (user, tour); a later rating replaces the earlier one
/// (server-side UPSERT). The shown aggregate score follows D647.
///
/// Michael (2026-10-10): a listener may rate with NO connection. LOCAL-670C
/// therefore ALWAYS saves the listener's own rating LOCALLY first and shows it
/// at once ("Your rating: 8", pending sync), then enqueues it in the
/// [OutboxService] to reach the server when a connection returns. We also try
/// an immediate direct POST so that online the aggregate badge updates straight
/// away; offline that simply fails and the outbox carries the rating later.
class TourRating {
  final double score;
  final int count;
  final String label;

  const TourRating({required this.score, required this.count, required this.label});

  /// 0 ratings → 7.5 "New". Used as a safe default when the network is
  /// unavailable so the badge always has something sensible to show.
  static const TourRating unrated = TourRating(score: 7.5, count: 0, label: 'New');

  factory TourRating.fromJson(Map<String, dynamic> json) {
    final rawScore = json['score'] ?? json['rating_score'] ?? 7.5;
    final rawCount = json['count'] ?? json['rating_count'] ?? 0;
    final rawLabel = json['label'] ?? json['rating_label'] ?? 'New';
    return TourRating(
      score: (rawScore as num).toDouble(),
      count: (rawCount as num).toInt(),
      label: rawLabel.toString(),
    );
  }

  /// Badge text, e.g. "7.5 · New" or "8.3 · 2 ratings".
  String get badgeText => '${score.toStringAsFixed(1)} · $label';
}

/// The outcome of an offline-first rating submission: the listener's OWN rating
/// (always known, shown immediately), whether it has been confirmed by the
/// server yet, and the recomputed aggregate when the server answered online.
class RatingSubmission {
  /// The 1–10 value the listener chose. Always present — it is saved locally
  /// before any network call, so the UI can show "Your rating: N" at once.
  final int myRating;

  /// True once the server has accepted the rating directly. False means it is
  /// saved locally and queued in the outbox, pending sync.
  final bool synced;

  /// The recomputed aggregate from the server, when online. Null offline.
  final TourRating? aggregate;

  const RatingSubmission({
    required this.myRating,
    required this.synced,
    this.aggregate,
  });

  /// "Your rating: 8" or "Your rating: 8 (pending sync)".
  String get myRatingText =>
      synced ? 'Your rating: $myRating' : 'Your rating: $myRating (pending sync)';
}

class TourRatingService {
  static String _myRatingKey(String tourId) => 'my_tour_rating_$tourId';

  /// Submit (or replace) the current user's rating for [tourId], offline-first.
  ///
  /// ALWAYS: saves the rating locally, enqueues it in the outbox, and returns a
  /// [RatingSubmission] the UI shows immediately. ADDITIONALLY tries a direct
  /// POST so an online rating updates the aggregate badge right away; a failure
  /// there is fine — the outbox will deliver it. Never throws.
  static Future<RatingSubmission> submitRating({
    required String tourId,
    required int rating,
  }) async {
    assert(rating >= 1 && rating <= 10, 'rating must be 1..10');
    final prefs = await SharedPreferences.getInstance();
    final userId = prefs.getString('user_id') ?? 'unknown';

    // 1) Save the listener's own rating locally — shown at once, survives offline.
    await prefs.setInt(_myRatingKey(tourId), rating);

    // 2) Enqueue for durable, idempotent sync (only server-known numeric ids;
    //    a local-only tour cannot be rated server-side anyway).
    if (int.tryParse(tourId) != null) {
      await OutboxService.instance.enqueueRating(
        userId: userId,
        tourId: tourId,
        rating: rating,
      );
    }

    // 3) Best-effort immediate direct POST so the aggregate updates online.
    final aggregate = await _directPost(tourId, userId, rating);
    return RatingSubmission(
      myRating: rating,
      synced: aggregate != null,
      aggregate: aggregate,
    );
  }

  /// The listener's own locally-saved rating for [tourId], or null if none.
  static Future<int?> myRating(String tourId) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getInt(_myRatingKey(tourId));
  }

  static Future<TourRating?> _directPost(
    String tourId,
    String userId,
    int rating,
  ) async {
    try {
      final response = await Endpoints.post(
        Service.orchestrator,
        '/tour/$tourId/rating',
        body: {'user_id': userId, 'rating': rating},
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        return TourRating.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      return null;
    } on SocketException catch (_) {
      return null;
    } on TimeoutException catch (_) {
      return null;
    } on http.ClientException catch (_) {
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Fetch the current shown aggregate rating for [tourId].
  ///
  /// Returns null on failure so the caller can fall back to any rating already
  /// carried on the tour's map-delivery record (which uses the same rule).
  static Future<TourRating?> fetchRating({required String tourId}) async {
    try {
      final response = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/rating',
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        return TourRating.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      return null;
    } on SocketException catch (_) {
      return null;
    } on TimeoutException catch (_) {
      return null;
    } on http.ClientException catch (_) {
      return null;
    } catch (_) {
      return null;
    }
  }
}
