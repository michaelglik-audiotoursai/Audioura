import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

import '../screens/debug_log_viewer_screen.dart';

/// Direct database update for tour status
/// This is a last resort approach when other methods fail
class DirectDbUpdate {
  /// Update tour status directly in the database using SQL
  static Future<bool> updateTourStatus(String requestString, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final userId = prefs.getString('user_id');
      
      if (userId == null) {
        await _logOperation('No user ID found, cannot update tour status');
        return false;
      }
      
      await _logOperation('Attempting to update status for request: "$requestString"');
      
      // First, find the tour_id by request string using SQL
      final findSql = "SELECT id, tour_id, request_string, status FROM tour_requests WHERE request_string = '$requestString' ORDER BY id DESC LIMIT 1";
      
      await _logOperation('EXECUTING SQL: $findSql');
      
      final findQuery = {
        'sql': findSql
      };
      
      final findResponse = await http.post(
        Uri.parse('http://$serverIp:5003/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(findQuery),
      );
      
      await _logOperation('SQL RESPONSE: ${findResponse.statusCode} - ${findResponse.body}');
      
      String tourId = '';
      if (findResponse.statusCode == 200) {
        try {
          final result = jsonDecode(findResponse.body);
          if (result != null && result.isNotEmpty && result[0]['tour_id'] != null) {
            tourId = result[0]['tour_id'];
            await _logOperation('Found tour_id: $tourId');
          }
        } catch (e) {
          await _logOperation('Error parsing SQL result: $e');
        }
      }
      
      // If we couldn't find a tour_id, create a new one
      if (tourId.isEmpty) {
        // Generate a new tour_id
        final timestamp = DateTime.now().millisecondsSinceEpoch.toRadixString(16);
        tourId = 'tour_$timestamp';
        final currentTime = DateTime.now().toIso8601String();
        
        // Create a new tour request with direct SQL
        final createSql = "INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at) VALUES ('$userId', '$tourId', '$requestString', 'started', '$currentTime')";
        
        await _logOperation('EXECUTING SQL: $createSql');
        
        final createQuery = {
          'sql': createSql
        };
        
        final createResponse = await http.post(
          Uri.parse('http://$serverIp:5003/sql'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(createQuery),
        );
        
        await _logOperation('SQL RESPONSE: ${createResponse.statusCode} - ${createResponse.body}');
        
        if (createResponse.statusCode != 200) {
          await _logOperation('Failed to create tour request');
          return false;
        }
      }
      
      // Now update the status with the dedicated tour update service
      final currentTime = DateTime.now().toUtc().toIso8601String();
      
      await _logOperation('Using dedicated tour update service for tour_id: $tourId');
      
      final updateData = {
        'tour_id': tourId,
        'status': status,
        'finished_at': currentTime
      };
      
      final updateResponse = await http.post(
        Uri.parse('http://$serverIp:5004/update'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(updateData),
      );
      
      await _logOperation('SQL RESPONSE: ${updateResponse.statusCode} - ${updateResponse.body}');
      
      // Verify the update worked
      final verifySql = "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id = '$tourId'";
      await executeAndLogQuery(verifySql);
      
      return updateResponse.statusCode == 200;
    } catch (e) {
      await _logOperation('SQL ERROR: $e');
      return false;
    }
  }
  
  /// Log operation to debug logs
  static Future<void> _logOperation(String message) async {
    await DebugLogHelper.addDebugLog('DB_UPDATE: $message');
  }
  
  /// Execute a direct SQL query and log the results
  static Future<void> executeAndLogQuery(String sql) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await _logOperation('EXECUTING SQL: $sql');
      
      // Use direct SQL query
      final sqlQuery = {
        'sql': sql
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(sqlQuery),
      );
      
      await _logOperation('SQL RESPONSE: ${response.statusCode} - ${response.body}');
    } catch (e) {
      await _logOperation('SQL ERROR: $e');
    }
  }
  
  /// Fix empty tour_id in database using direct SQL
  static Future<bool> fixEmptyTourId(String userId, String requestString) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await _logOperation('Attempting to fix empty tour_id for request: "$requestString"');
      
      // Generate a new tour_id
      final timestamp = DateTime.now().millisecondsSinceEpoch.toRadixString(16);
      final newTourId = 'tour_$timestamp';
      final currentTime = DateTime.now().toIso8601String();
      
      // Create a new tour request with direct SQL
      final createSql = "INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at) VALUES ('$userId', '$newTourId', '$requestString', 'started', '$currentTime')";
      
      await _logOperation('EXECUTING SQL: $createSql');
      
      final createQuery = {
        'sql': createSql
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(createQuery),
      );
      
      await _logOperation('SQL RESPONSE: ${response.statusCode} - ${response.body}');
      
      // Now update the status
      if (response.statusCode == 200) {
        final updateSql = "UPDATE tour_requests SET status = 'completed', finished_at = '$currentTime' WHERE tour_id = '$newTourId'";
        
        await _logOperation('EXECUTING SQL: $updateSql');
        
        final updateQuery = {
          'sql': updateSql
        };
        
        final statusResponse = await http.post(
          Uri.parse('http://$serverIp:5003/sql'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(updateQuery),
        );
        
        await _logOperation('SQL RESPONSE: ${statusResponse.statusCode} - ${statusResponse.body}');
        
        // Verify the update worked
        final verifySql = "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id = '$newTourId'";
        await executeAndLogQuery(verifySql);
        
        return statusResponse.statusCode == 200;
      }
      
      return false;
    } catch (e) {
      await _logOperation('SQL ERROR: $e');
      return false;
    }
  }
}