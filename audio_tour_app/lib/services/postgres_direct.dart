import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// Direct Postgres connection for database updates
class PostgresDirect {
  /// Update tour status using direct Postgres connection
  static Future<bool> updateTourStatus(String tourId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final timestamp = DateTime.now().toIso8601String();
      
      // Log the attempt
      await DebugLogHelper.addDebugLog('POSTGRES DIRECT: Attempting to update tour_id=$tourId to $status');
      
      // Send the request to the dedicated tour update service
      final updateData = {
        'tour_id': tourId,
        'status': status,
        'finished_at': timestamp
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5004/update'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(updateData),
      );
      
      // Log the response
      await DebugLogHelper.addDebugLog('POSTGRES RESPONSE: ${response.statusCode} - ${response.body}');
      
      return response.statusCode == 200;
    } catch (e) {
      await DebugLogHelper.addDebugLog('POSTGRES ERROR: $e');
      return false;
    }
  }
  
  /// Verify that the update was successful
  static Future<void> verifyUpdate(String tourId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      final verifyData = {
        'command': 'SELECT',
        'columns': ['id', 'tour_id', 'request_string', 'status', 'finished_at'],
        'table': 'tour_requests',
        'where': "tour_id = '$tourId'"
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/pg'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(verifyData),
      );
      
      await DebugLogHelper.addDebugLog('VERIFY RESPONSE: ${response.statusCode} - ${response.body}');
    } catch (e) {
      await DebugLogHelper.addDebugLog('VERIFY ERROR: $e');
    }
  }
}