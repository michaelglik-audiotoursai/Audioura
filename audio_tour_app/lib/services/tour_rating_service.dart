import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';

/// Per-TOUR 1–10 rating (LOCAL-670).
///
/// Backend (orchestrator, port 5002):
///   POST /tour/<tour_id>/rating  { user_id, rating }  → { score, count, label }
///   GET  /tour/<tour_id>/rating                       → { score, count, label }
///
/// One rating per (user, tour); a later rating replaces the earlier one
/// (server-side UPSERT). The shown score follows D647: 0 ratings → 7.5 "New",
/// 1–3 → average of (7.5 + ratings), ≥4 → median of the real ratings only.
///
/// This is the per-TOUR judgement, distinct from the per-STOP thumbs handled by
/// [StopFeedbackService]. It is deliberately simple: a tour rating is a single
/// deliberate action from a menu or the end-of-tour prompt, not a high-volume
/// offline-queued signal, so we POST directly and surface failures to the UI.
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

class TourRatingService {
  /// Submit (or replace) the current user's rating for [tourId].
  ///
  /// Returns the recomputed [TourRating] on success, or null on failure (no
  /// network, server error). Never throws — the caller shows a toast.
  static Future<TourRating?> submitRating({
    required String tourId,
    required int rating,
  }) async {
    assert(rating >= 1 && rating <= 10, 'rating must be 1..10');
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? 'unknown';

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

  /// Fetch the current shown rating for [tourId].
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
