import 'dart:convert';
import '../config/endpoints.dart';

/// [LOCAL-688] "Why this score" — the editor's evaluation behind a tour's
/// Audioura score (5.0–8.0, LOCAL-685). Public and free; no auth.
///
/// map-delivery (port 5005):
///   GET  /tour/<id>/score-explanation
///       → { score, label, criteria:[{name,label,grade,evidence}], summary,
///           scored_at, rubric_version }   (a translation returns its
///           original's; 404 when the tour has no evaluated score yet)
///   POST /tour/<id>/rescore-request { user_id }
///       → 200 {status:'queued', version} | 403 not owner | 409 already this
///         version
///
/// The public page "How Audioura scores tours" lives at GET /how-we-score.

/// One rubric criterion: a 1–10 grade and the editor's one-sentence evidence.
class ScoreCriterion {
  final String name;   // 'story', 'specificity', 'place', 'flow', 'accuracy'
  final String label;  // human label, e.g. 'Sense of place'
  final double? grade; // 1–10, null if the server omitted it
  final String evidence;

  const ScoreCriterion({
    required this.name,
    required this.label,
    required this.grade,
    required this.evidence,
  });

  factory ScoreCriterion.fromJson(Map<String, dynamic> j) => ScoreCriterion(
        name: (j['name'] ?? '').toString(),
        label: (j['label'] ?? j['name'] ?? '').toString(),
        grade: (j['grade'] as num?)?.toDouble(),
        evidence: (j['evidence'] ?? '').toString(),
      );
}

/// The full Why-this-score payload for one tour.
class ScoreExplanation {
  final double score;          // the Audioura score, 5.0–8.0
  final String label;          // 'Audioura score'
  final List<ScoreCriterion> criteria;
  final String summary;        // the editor's one-line verdict
  final String? scoredAt;      // YYYY-MM-DD, or null
  final int? rubricVersion;

  const ScoreExplanation({
    required this.score,
    required this.label,
    required this.criteria,
    required this.summary,
    required this.scoredAt,
    required this.rubricVersion,
  });

  factory ScoreExplanation.fromJson(Map<String, dynamic> j) => ScoreExplanation(
        score: (j['score'] as num?)?.toDouble() ?? 0,
        label: (j['label'] ?? 'Audioura score').toString(),
        criteria: ((j['criteria'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ScoreCriterion.fromJson)
            .toList(),
        summary: (j['summary'] ?? '').toString(),
        scoredAt: j['scored_at']?.toString(),
        rubricVersion: (j['rubric_version'] as num?)?.toInt(),
      );
}

class ScoreExplanationService {
  /// Fetch the Why-this-score explanation for [tourId]. Returns null when the
  /// tour has no evaluated score yet (404) or the request fails — the caller
  /// shows a gentle "not available yet" message rather than an error.
  static Future<ScoreExplanation?> fetch(String tourId) async {
    try {
      final resp = await Endpoints.get(
        Service.mapDelivery,
        '/tour/$tourId/score-explanation',
        timeout: const Duration(seconds: 10),
      );
      if (resp.statusCode != 200) return null;
      final body = jsonDecode(resp.body);
      if (body is! Map<String, dynamic>) return null;
      return ScoreExplanation.fromJson(body);
    } catch (_) {
      return null;
    }
  }

  /// Request the ONE free re-score of a guide's own tour after an edit.
  /// Returns a [RescoreResult] carrying the outcome so the UI can show the
  /// right message (queued / already requested this version / not your tour).
  static Future<RescoreResult> requestRescore(String tourId, String userId) async {
    try {
      final resp = await Endpoints.post(
        Service.mapDelivery,
        '/tour/$tourId/rescore-request',
        body: {'user_id': userId},
        timeout: const Duration(seconds: 10),
      );
      Map<String, dynamic> body = const {};
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map<String, dynamic>) body = decoded;
      } catch (_) {}
      switch (resp.statusCode) {
        case 200:
          return const RescoreResult(
            status: RescoreStatus.queued,
            message: 'Thanks — we\'ll re-score this tour shortly.',
          );
        case 409:
          return RescoreResult(
            status: RescoreStatus.alreadyRequested,
            message: (body['message'] ?? 'A re-score was already requested for '
                    'this version. Edit the tour again for another free re-score.')
                .toString(),
          );
        case 403:
          return const RescoreResult(
            status: RescoreStatus.notOwner,
            message: 'Only the tour\'s guide can request a re-score.',
          );
        default:
          return const RescoreResult(
            status: RescoreStatus.failed,
            message: 'Could not request a re-score. Please try again.',
          );
      }
    } catch (_) {
      return const RescoreResult(
        status: RescoreStatus.failed,
        message: 'Could not request a re-score. Please check your connection.',
      );
    }
  }

  /// The public "How Audioura scores tours" page URL (map-delivery /how-we-score).
  static Future<Uri> howWeScoreUrl() =>
      Endpoints.url(Service.mapDelivery, '/how-we-score');
}

enum RescoreStatus { queued, alreadyRequested, notOwner, failed }

class RescoreResult {
  final RescoreStatus status;
  final String message;
  const RescoreResult({required this.status, required this.message});
}
