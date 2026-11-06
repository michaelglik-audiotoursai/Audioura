// LOCAL-868 (D762, app side) — the free `POST /preview-stops` call.
//
// Resolves a pasted list of places into ordered stops with map pins on the
// generator service. No LLM and no tour generation happens here; the listener
// reviews the result and only then generates.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/endpoints.dart';
import '../utils/pasted_list.dart';

/// A preview failure with a message fit to show the listener.
class PreviewStopsException implements Exception {
  final String message;
  const PreviewStopsException(this.message);
  @override
  String toString() => message;
}

/// Sends the request. A seam so tests assert the payload without a network.
typedef PreviewPoster = Future<http.Response> Function(
    Map<String, dynamic> body);

class PreviewStopsService {
  const PreviewStopsService._();

  static Future<http.Response> _defaultPost(Map<String, dynamic> body) =>
      Endpoints.post(Service.generator, '/preview-stops',
          body: body, timeout: const Duration(seconds: 60));

  /// Preview [text] in [city]. Throws [PreviewStopsException].
  static Future<PreviewResult> preview(
    String text,
    String city, {
    PreviewPoster? post,
  }) async {
    final invalid = validatePasteInput(text, city);
    if (invalid != null) throw PreviewStopsException(invalid);

    http.Response resp;
    try {
      resp = await (post ?? _defaultPost)(buildPreviewBody(text, city));
    } on TimeoutException {
      throw const PreviewStopsException(
          'The preview took too long. Check your connection and try again.');
    } catch (_) {
      throw const PreviewStopsException(
          'Could not reach Audioura. Check your connection and try again.');
    }

    final map = Endpoints.tryDecodeMap(utf8.decode(resp.bodyBytes));
    if (resp.statusCode == 200 && map != null) {
      try {
        return parsePreviewResponse(map);
      } on FormatException catch (e) {
        throw PreviewStopsException(
            'We could not find any places in that list (${e.message}).');
      }
    }
    if (Endpoints.isRouteMissing(resp.statusCode, resp.body) ||
        (resp.statusCode == 404 && map?['error'] != null)) {
      // 404 from the service itself: USER_STOPS_ENABLED is off on this server.
      throw const PreviewStopsException(
          'Pasting a list is not available on this server yet. '
          'You can still name your stops one at a time.');
    }
    final err = map?['error']?.toString();
    if (resp.statusCode == 400 && err != null && err.isNotEmpty) {
      throw PreviewStopsException(_friendly400(err));
    }
    throw PreviewStopsException(
        'The preview failed (${resp.statusCode}). Please try again.');
  }

  /// Server 400 text → something a listener can act on.
  static String _friendly400(String err) {
    final e = err.toLowerCase();
    if (e.contains('city')) {
      return 'Which city is this list in? Add the city above and try again.';
    }
    if (e.contains('no stops')) {
      return 'We could not find any places in that text.';
    }
    return err;
  }
}
