import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../config.dart';

class TranslationService {
  static Future<Map<String, dynamic>> translateTour({
    required int tourId,
    required List<String> languages,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
      final baseUrl = 'http://$serverIp:5030';

      await DebugLogHelper.addDebugLog('Translation: POST $baseUrl/translate-with-audio tourId=$tourId languages=${languages.join(", ")}');

      final response = await http.post(
        Uri.parse('$baseUrl/translate-with-audio'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'content_id': tourId,
          'content_type': 'tour',
          'languages': languages,
        }),
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