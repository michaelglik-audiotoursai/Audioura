import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// Direct JDBC connection for database updates
class DirectJdbcUpdate {
  /// Update tour status using direct JDBC connection
  static Future<bool> updateTourStatus(String tourId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final timestamp = DateTime.now().toIso8601String();
      
      // Log the attempt
      await DebugLogHelper.addDebugLog('JDBC UPDATE: Attempting to update tour_id=$tourId to $status');
      
      // Create the JDBC update request
      final jdbcData = {
        'operation': 'update',
        'table': 'tour_requests',
        'updates': {
          'status': status,
          'finished_at': timestamp
        },
        'where': {
          'tour_id': tourId
        }
      };
      
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
      await DebugLogHelper.addDebugLog('JDBC RESPONSE: ${response.statusCode} - ${response.body}');
      
      if (response.statusCode == 200) {
        return true;
      }
      
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('JDBC ERROR: $e');
      return false;
    }
  }
  
  /// Verify that the update was successful
  static Future<void> verifyUpdate(String tourId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      final verifyData = {
        'operation': 'select',
        'table': 'tour_requests',
        'columns': ['id', 'tour_id', 'request_string', 'status', 'finished_at'],
        'where': {
          'tour_id': tourId
        }
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/jdbc'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(verifyData),
      );
      
      await DebugLogHelper.addDebugLog('VERIFY RESPONSE: ${response.statusCode} - ${response.body}');
    } catch (e) {
      await DebugLogHelper.addDebugLog('VERIFY ERROR: $e');
    }
  }
}