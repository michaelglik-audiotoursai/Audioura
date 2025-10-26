import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// Direct server API for updating tour status
class ServerApi {
  /// Update tour status directly on the server
  static Future<bool> updateTourStatus(String tourId, String status, [String? timestamp]) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final utcTimestamp = timestamp ?? DateTime.now().toUtc().toIso8601String();
      
      // Create a direct SQL update request
      final sql = "UPDATE tour_requests SET status = '$status', finished_at = '$utcTimestamp' WHERE tour_id = '$tourId'";
      final updateSql = {
        'sql': sql
      };
      
      // Log the SQL query
      await DebugLogHelper.addDebugLog('EXECUTING SQL: $sql');
      
      // Send the request to the server
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(updateSql),
      );
      
      // Log the response
      await DebugLogHelper.addDebugLog('SQL RESPONSE: ${response.statusCode} - ${response.body}');
      
      return response.statusCode == 200;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SQL ERROR: $e');
      return false;
    }
  }
  
  /// Check tour status in the database
  static Future<void> checkTourStatus(String tourId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      // Create a SQL query
      final sql = "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id = '$tourId'";
      final querySql = {
        'sql': sql
      };
      
      // Log the SQL query
      await DebugLogHelper.addDebugLog('EXECUTING SQL: $sql');
      
      // Send the request to the server
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(querySql),
      );
      
      // Log the response
      await DebugLogHelper.addDebugLog('SQL RESPONSE: ${response.statusCode} - ${response.body}');
    } catch (e) {
      await DebugLogHelper.addDebugLog('SQL ERROR: $e');
    }
  }
}