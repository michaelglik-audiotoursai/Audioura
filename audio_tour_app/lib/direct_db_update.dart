import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// Direct database update for tour status
/// This is a last resort approach when other methods fail
class DirectDbUpdate {
  /// Update tour status directly in the database
  static Future<bool> updateTourStatus(String requestString, String status) async {
    try {
      // Use the direct SQL endpoint to update the status
      const serverIp = '192.168.0.217';
      
      // Log the operation
      await _logOperation('Attempting direct DB update for request: "$requestString"');
      
      // First, find the tour_id by request string
      final findSql = {
        'sql': "SELECT id, tour_id, request_string, status FROM tour_requests WHERE request_string = '$requestString' ORDER BY id DESC LIMIT 1"
      };
      
      await _logOperation('Executing SQL: ${findSql['sql']}');
      
      final findResponse = await http.post(
        Uri.parse('http://$serverIp:5003/execute_sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(findSql),
      );
      
      await _logOperation('Find response: ${findResponse.statusCode} - ${findResponse.body}');
      
      if (findResponse.statusCode == 200) {
        final result = jsonDecode(findResponse.body);
        if (result != null && result.isNotEmpty) {
          await _logOperation('Found record: ${result[0]}');
          
          if (result[0]['tour_id'] != null && result[0]['tour_id'].toString().isNotEmpty) {
            final tourId = result[0]['tour_id'];
            
            // Now update the status
            final updateSql = {
              'sql': "UPDATE tour_requests SET status = '$status', finished_at = '${DateTime.now().toIso8601String()}' WHERE tour_id = '$tourId'"
            };
            
            await _logOperation('Executing update SQL: ${updateSql['sql']}');
            
            final updateResponse = await http.post(
              Uri.parse('http://$serverIp:5003/execute_sql'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(updateSql),
            );
            
            await _logOperation('Update response: ${updateResponse.statusCode} - ${updateResponse.body}');
            return updateResponse.statusCode == 200;
          } else {
            // The tour_id is null or empty, try updating by request string
            final updateByRequestSql = {
              'sql': "UPDATE tour_requests SET status = '$status', finished_at = '${DateTime.now().toIso8601String()}' WHERE request_string = '$requestString'"
            };
            
            await _logOperation('Executing update by request string: ${updateByRequestSql['sql']}');
            
            final updateResponse = await http.post(
              Uri.parse('http://$serverIp:5003/execute_sql'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode(updateByRequestSql),
            );
            
            await _logOperation('Update by request response: ${updateResponse.statusCode} - ${updateResponse.body}');
            return updateResponse.statusCode == 200;
          }
        } else {
          await _logOperation('No records found for request: "$requestString"');
        }
      }
      
      return false;
    } catch (e) {
      await _logOperation('Error in direct DB update: $e');
      return false;
    }
  }
  
  /// Log operation to debug logs
  static Future<void> _logOperation(String message) async {
    print('DB_UPDATE: $message');
    try {
      final prefs = await SharedPreferences.getInstance();
      final logs = prefs.getStringList('debug_logs') ?? [];
      final timestamp = DateTime.now().toString().substring(11, 19);
      logs.add('[$timestamp] SQL: $message');
      
      // Keep only last 100 logs
      if (logs.length > 100) {
        logs.removeAt(0);
      }
      
      await prefs.setStringList('debug_logs', logs);
    } catch (e) {
      print('Error logging operation: $e');
    }
  }
  
  /// Execute a direct SQL query and log the results
  static Future<void> executeAndLogQuery(String sql) async {
    try {
      const serverIp = '192.168.0.217';
      
      await _logOperation('Executing diagnostic query: $sql');
      
      final sqlQuery = {
        'sql': sql
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/execute_sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(sqlQuery),
      );
      
      await _logOperation('Query response: ${response.statusCode} - ${response.body}');
    } catch (e) {
      await _logOperation('Error executing query: $e');
    }
  }
  
  /// Fix empty tour_id in database
  static Future<bool> fixEmptyTourId(String userId, String requestString) async {
    try {
      const serverIp = '192.168.0.217';
      
      await _logOperation('Attempting to fix empty tour_id for request: "$requestString"');
      
      // Generate a new tour_id
      final timestamp = DateTime.now().millisecondsSinceEpoch.toRadixString(16);
      final newTourId = 'tour_$timestamp';
      
      // Update the record with empty tour_id
      final updateSql = {
        'sql': "UPDATE tour_requests SET tour_id = '$newTourId' WHERE secret_id = '$userId' AND request_string = '$requestString' AND (tour_id IS NULL OR tour_id = '')"
      };
      
      await _logOperation('Executing fix SQL: ${updateSql['sql']}');
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/execute_sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(updateSql),
      );
      
      await _logOperation('Fix response: ${response.statusCode} - ${response.body}');
      
      // Now update the status
      if (response.statusCode == 200) {
        final statusUpdateSql = {
          'sql': "UPDATE tour_requests SET status = 'completed', finished_at = '${DateTime.now().toIso8601String()}' WHERE tour_id = '$newTourId'"
        };
        
        await _logOperation('Updating status for fixed tour_id: $newTourId');
        
        final statusResponse = await http.post(
          Uri.parse('http://$serverIp:5003/execute_sql'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(statusUpdateSql),
        );
        
        await _logOperation('Status update response: ${statusResponse.statusCode} - ${statusResponse.body}');
        return statusResponse.statusCode == 200;
      }
      
      return false;
    } catch (e) {
      await _logOperation('Error fixing empty tour_id: $e');
      return false;
    }
  }
}