import 'dart:convert';

import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// [LOCAL-579] Result of a share request.
///
/// Exactly one of [code] / [errorMessage] is non-null:
///  - success  → [code] (and [shareUrl] when the server returned one)
///  - failure  → [errorMessage], a short line safe to show the user as-is.
class ShareResult {
  final String? code;
  final String? shareUrl;
  final String? errorMessage;

  const ShareResult._({this.code, this.shareUrl, this.errorMessage});

  factory ShareResult.success(String code, String? shareUrl) =>
      ShareResult._(code: code, shareUrl: shareUrl);

  factory ShareResult.failure(String message) =>
      ShareResult._(errorMessage: message);

  bool get ok => code != null;
}

/// Calls `POST /tour/share` on the tour-generator service and returns a
/// [ShareResult]. The server (sharing_endpoints.py) takes a single
/// `audio_tour_id` and derives everything else from the audio_tours row, so the
/// app sends one integer and never re-uploads the tour text. Idempotent: the
/// same tour always yields the same 8-char code.
///
/// [audioTourId] is the tour's numeric id (My Tours stores it as `tour_id`).
/// Non-numeric or empty ids are rejected locally — the server keys on the
/// numeric audio_tours.id, so a job-id string could never resolve.
class TourShareService {
  /// Shares the tour with the given id. Never throws — offline, timeouts and
  /// 5xx all come back as [ShareResult.failure] with a plain message.
  static Future<ShareResult> share(dynamic audioTourId) async {
    final idStr = audioTourId?.toString().trim() ?? '';
    final numericId = int.tryParse(idStr);
    if (numericId == null) {
      // Translations and freshly-generated tours whose id is still a job-id
      // string cannot be shared yet: the server keys on the numeric row id.
      return ShareResult.failure(
          "This tour can't be shared yet — it has no numeric tour ID.");
    }

    try {
      final response = await Endpoints.post(
        Service.generator,
        '/tour/share',
        body: {'audio_tour_id': numericId},
        timeout: const Duration(seconds: 15),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        final code = (data['share_id'] ?? '').toString();
        final url = data['share_url']?.toString();
        if (code.isEmpty) {
          return ShareResult.failure(
              'The server did not return a share code. Please try again.');
        }
        await DebugLogHelper.addDebugLog('SHARE: tour $numericId → code $code');
        return ShareResult.success(code, url);
      }

      // Surface the server's own message when it gives one (e.g. "tour not
      // found", "could not read tour"), otherwise a status-based fallback.
      final serverMsg = _serverMessage(response.body);
      await DebugLogHelper.addDebugLog(
          'SHARE: tour $numericId failed ${response.statusCode}: ${response.body}');
      switch (response.statusCode) {
        case 404:
          return ShareResult.failure(
              serverMsg ?? 'That tour was not found on the server.');
        case 401:
        case 503:
          return ShareResult.failure(
              serverMsg ?? 'Sharing is not available right now.');
        default:
          return ShareResult.failure(serverMsg ??
              'Sharing failed (${response.statusCode}). Please try again.');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SHARE: request error: $e');
      return ShareResult.failure(
          'Could not reach the server. Check your connection and try again.');
    }
  }

  /// Pulls a human-readable message out of a JSON error body, or null.
  static String? _serverMessage(String body) {
    try {
      final data = json.decode(body);
      if (data is Map && data['error'] != null) {
        final msg = data['error'].toString().trim();
        if (msg.isNotEmpty) {
          // Capitalise the first letter so terse server strings read as a
          // sentence ("tour not found" → "Tour not found").
          return msg[0].toUpperCase() + msg.substring(1);
        }
      }
    } catch (_) {
      // Not JSON — ignore and let the caller use a status-based fallback.
    }
    return null;
  }
}
