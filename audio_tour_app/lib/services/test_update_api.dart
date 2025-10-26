import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';
import 'direct_jdbc_update.dart';
import 'postgres_direct.dart';
import 'direct_postgres_connection.dart';

/// Test API for updating tour status
class TestUpdateApi {
  /// Update a specific tour record for testing
  static Future<bool> updateSpecificTour(String tourId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final timestamp = DateTime.now().toIso8601String();
      
      // Log the attempt
      await DebugLogHelper.addDebugLog('TEST UPDATE: Attempting to update tour_id=$tourId to completed');
      
      // Use only the dedicated tour update service
      try {
        final updateData = {
          'tour_id': tourId,
          'status': 'completed',
          'finished_at': timestamp
        };
        
        await DebugLogHelper.addDebugLog('Using dedicated tour update service');
        final updateResponse = await http.post(
          Uri.parse('http://$serverIp:5004/update'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(updateData),
        );
        
        await DebugLogHelper.addDebugLog('TOUR UPDATE RESPONSE: ${updateResponse.statusCode} - ${updateResponse.body}');
        
        if (updateResponse.statusCode == 200) {
          await DebugLogHelper.addDebugLog('Successfully updated tour status via tour update service');
          return true;
        } else {
          await DebugLogHelper.addDebugLog('Failed to update tour status: ${updateResponse.statusCode} - ${updateResponse.body}');
          return false;
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('TOUR UPDATE ERROR: $e');
        return false;
      }
      
      // If all methods failed, return false
      await DebugLogHelper.addDebugLog('Update tour failed, no more methods to try');
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('TEST UPDATE ERROR: $e');
      return false;
    }
  }
}