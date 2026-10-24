import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../config/endpoints.dart';

class TranslationService {
  static Future<Map<String, dynamic>> translateTour({
    required int tourId,
    required List<String> languages,
  }) async {
    try {
      final uri = await Endpoints.url(Service.translation, '/translate-with-audio');
      // [LOCAL-752 A3] Send the device user_id so the server can enforce the
      // organiser-only rule for a COMMUNITY tour (a member translating one is
      // refused 403). An ordinary tour is unaffected. Absent/empty user_id is
      // omitted (the server treats a community tour with no user_id as 401).
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? '';
      final requestBody = <String, dynamic>{
        'content_id': tourId,
        'content_type': 'tour',
        'languages': languages,
        if (userId.isNotEmpty) 'user_id': userId,
      };
      final headers = await Endpoints.apiHeaders(Service.translation, requestBody: requestBody);

      await DebugLogHelper.addDebugLog('Translation: POST $uri tourId=$tourId languages=${languages.join(", ")}');

      final response = await http.post(
        uri,
        headers: headers,
        body: jsonEncode(requestBody),
      ).timeout(Duration(minutes: 5));

      await DebugLogHelper.addDebugLog('Translation: HTTP ${response.statusCode} received');

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        final preview = response.body.length > 500
            ? '${response.body.substring(0, 500)}...(${response.body.length} bytes total)'
            : response.body;
        await DebugLogHelper.addDebugLog('Translation: Success - $preview');
        return result;
      } else {
        await DebugLogHelper.addDebugLog('Translation: Error ${response.statusCode} - ${response.body}');
        return {'status': 'error', 'message': 'Translation failed: ${response.statusCode}'};
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('Translation: Exception - $e');
      return {'status': 'error', 'message': e.toString()};
    }
  }
}