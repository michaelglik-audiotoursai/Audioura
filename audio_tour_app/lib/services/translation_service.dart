import 'dart:convert';
import 'package:http/http.dart' as http;
import '../screens/debug_log_viewer_screen.dart';

class TranslationService {
  static const String baseUrl = 'http://localhost:5030';

  static Future<Map<String, dynamic>> translateContent({
    required String contentId,
    required String contentType,
    required List<String> languages,
  }) async {
    try {
      DebugLogHelper.addDebugLog('Translation: Starting for $contentType $contentId to ${languages.join(", ")}');
      
      final response = await http.post(
        Uri.parse('$baseUrl/translate-with-audio'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'content_id': contentType == 'tour' ? int.parse(contentId) : contentId,
          'content_type': contentType,
          'languages': languages,
        }),
      );

      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        DebugLogHelper.addDebugLog('Translation: Success - ${result['translations']?.length ?? 0} translations');
        return result;
      } else {
        DebugLogHelper.addDebugLog('Translation: Error ${response.statusCode} - ${response.body}');
        return {'status': 'error', 'message': 'Translation failed'};
      }
    } catch (e) {
      DebugLogHelper.addDebugLog('Translation: Exception - $e');
      return {'status': 'error', 'message': e.toString()};
    }
  }
}