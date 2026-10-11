import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';

/// Verified reviews (LOCAL-672).
///
/// Backend (orchestrator, port 5002 — alongside the LOCAL-670 ratings):
///   GET  /tour/<id>/reviews?sort=&band=     → approved reviews (newest/verified first)
///   POST /tour/<id>/review  {user_id, review_text}        → submit/replace (<=500)
///   GET  /tour/<id>/distribution            → five-band rating distribution
///   POST /review/<id>/helpful {user_id}     → one helpful vote (not your own)
///   POST /review/<id>/reply   {user_id, reply_text}       → one curator reply (<=300)
///
/// A review is attached to the user's rating. The auto-check (profanity / URL /
/// contact info) holds a flagged review as "pending" with a reason, so a freshly
/// submitted review may not appear in the approved list immediately — the UI
/// tells the user it is "being checked".
class TourReview {
  final int id;
  final int rating;
  final bool verified; // "Verified listener"
  final String text;
  final String? date; // YYYY-MM-DD
  final int helpfulCount;
  final String? band; // '9-10' | '7-8' | '5-6' | '3-4' | '1-2'
  final String? replyText;
  final String? replyDate;

  const TourReview({
    required this.id,
    required this.rating,
    required this.verified,
    required this.text,
    this.date,
    this.helpfulCount = 0,
    this.band,
    this.replyText,
    this.replyDate,
  });

  factory TourReview.fromJson(Map<String, dynamic> json) {
    final reply = json['reply'] as Map<String, dynamic>?;
    return TourReview(
      id: (json['id'] as num).toInt(),
      rating: (json['rating'] as num?)?.toInt() ?? 0,
      verified: json['verified'] == true || json['verified_listener'] == true,
      text: json['review_text']?.toString() ?? '',
      date: json['date']?.toString(),
      helpfulCount: (json['helpful_count'] as num?)?.toInt() ?? 0,
      band: json['band']?.toString(),
      replyText: reply?['text']?.toString(),
      replyDate: reply?['date']?.toString(),
    );
  }
}

/// One band of the rating distribution (item 8).
class RatingBand {
  final String band; // e.g. '9-10'
  final int count;
  final int percent;

  const RatingBand({required this.band, required this.count, required this.percent});

  factory RatingBand.fromJson(Map<String, dynamic> json) => RatingBand(
        band: json['band']?.toString() ?? '',
        count: (json['count'] as num?)?.toInt() ?? 0,
        percent: (json['percent'] as num?)?.toInt() ?? 0,
      );
}

class RatingDistribution {
  final int total;
  final List<RatingBand> bands;

  const RatingDistribution({required this.total, required this.bands});

  static const empty = RatingDistribution(total: 0, bands: []);

  factory RatingDistribution.fromJson(Map<String, dynamic> json) {
    final raw = (json['bands'] as List?) ?? const [];
    return RatingDistribution(
      total: (json['total'] as num?)?.toInt() ?? 0,
      bands: raw
          .map((b) => RatingBand.fromJson(b as Map<String, dynamic>))
          .toList(growable: false),
    );
  }
}

/// Review sort orders (item 10). Values match the server's ?sort= param.
enum ReviewSort { top, recent, critical }

extension ReviewSortParam on ReviewSort {
  String get param {
    switch (this) {
      case ReviewSort.recent:
        return 'recent';
      case ReviewSort.critical:
        return 'critical';
      case ReviewSort.top:
        return 'top';
    }
  }

  String get label {
    switch (this) {
      case ReviewSort.recent:
        return 'Most recent';
      case ReviewSort.critical:
        return 'Critical';
      case ReviewSort.top:
        return 'Top';
    }
  }
}

class TourReviewsService {
  /// Fetch approved reviews for [tourId]. Returns an empty list on any failure
  /// so the UI degrades to "no reviews yet" rather than erroring.
  static Future<List<TourReview>> fetchReviews(
    String tourId, {
    ReviewSort sort = ReviewSort.top,
    String? band,
  }) async {
    try {
      var path = '/tour/$tourId/reviews?sort=${sort.param}';
      if (band != null && band.isNotEmpty) path += '&band=$band';
      final response = await Endpoints.get(
        Service.orchestrator,
        path,
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        final raw = (body['reviews'] as List?) ?? const [];
        return raw
            .map((r) => TourReview.fromJson(r as Map<String, dynamic>))
            .toList(growable: false);
      }
      return const [];
    } on SocketException catch (_) {
      return const [];
    } on TimeoutException catch (_) {
      return const [];
    } on http.ClientException catch (_) {
      return const [];
    } catch (_) {
      return const [];
    }
  }

  /// Fetch the five-band distribution for [tourId]. Empty on failure.
  static Future<RatingDistribution> fetchDistribution(String tourId) async {
    try {
      final response = await Endpoints.get(
        Service.orchestrator,
        '/tour/$tourId/distribution',
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        return RatingDistribution.fromJson(
            jsonDecode(response.body) as Map<String, dynamic>);
      }
      return RatingDistribution.empty;
    } catch (_) {
      return RatingDistribution.empty;
    }
  }

  /// Submit (or replace) the current user's short text review of [tourId].
  ///
  /// Returns the server's status string ('pending' | 'approved' | 'rejected')
  /// on success, or null on failure. A 'pending' means the auto-check held it
  /// for review — the UI should say it is being checked before it appears.
  static Future<String?> submitReview({
    required String tourId,
    required String reviewText,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? 'unknown';
      final response = await Endpoints.post(
        Service.orchestrator,
        '/tour/$tourId/review',
        body: {'user_id': userId, 'review_text': reviewText},
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        return body['review_status']?.toString() ?? 'pending';
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Record a "helpful" vote on [reviewId]. Returns the new count, or null on
  /// failure (including the "cannot vote on your own review" 400).
  static Future<int?> voteHelpful(int reviewId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? 'unknown';
      final response = await Endpoints.post(
        Service.orchestrator,
        '/review/$reviewId/helpful',
        body: {'user_id': userId},
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        return (body['helpful_count'] as num?)?.toInt();
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Add the single curator reply to [reviewId]. Returns the reply status on
  /// success, or null on failure (not-creator / already-replied are 400s).
  static Future<String?> replyToReview({
    required int reviewId,
    required String replyText,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? 'unknown';
      final response = await Endpoints.post(
        Service.orchestrator,
        '/review/$reviewId/reply',
        body: {'user_id': userId, 'reply_text': replyText},
        timeout: const Duration(seconds: 10),
      );
      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        return body['reply_status']?.toString() ?? 'pending';
      }
      return null;
    } catch (_) {
      return null;
    }
  }
}
