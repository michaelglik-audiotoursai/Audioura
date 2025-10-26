import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// Direct connection to PostgreSQL database
class DirectPostgresConnection {
  /// Update tour status using direct PostgreSQL connection
  static Future<bool> updateTourStatus(String tourId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final timestamp = DateTime.now().toIso8601String();
      
      // Log the attempt
      await DebugLogHelper.addDebugLog('DIRECT POSTGRES CONNECTION: Attempting to update tour_id=$tourId to $status');
      
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
      
      await DebugLogHelper.addDebugLog('TOUR UPDATE RESPONSE: ${response.statusCode} - ${response.body}');
      
      return response.statusCode == 200;
      
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('DIRECT POSTGRES CONNECTION ERROR: $e');
      return false;
    }
  }
}