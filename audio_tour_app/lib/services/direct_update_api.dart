import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// Direct API for updating tour status
class DirectUpdateApi {
  /// Update tour status directly using the update API
  static Future<bool> updateTourStatus(String tourId, String status, [String? timestamp]) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final utcTimestamp = timestamp ?? DateTime.now().toUtc().toIso8601String();
      
      // Create a direct update request
      final updateData = {
        'tour_id': tourId,
        'status': status,
        'finished_at': utcTimestamp
      };
      
      // Log the update request
      await DebugLogHelper.addDebugLog('DIRECT UPDATE: Updating tour_id=$tourId to status=$status');
      
      // Send the request to the dedicated tour update service
      final response = await http.post(
        Uri.parse('http://$serverIp:5004/update'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(updateData),
      );
      
      // Log the response
      await DebugLogHelper.addDebugLog('DIRECT UPDATE RESPONSE: ${response.statusCode} - ${response.body}');
      
      return response.statusCode == 200;
    } catch (e) {
      await DebugLogHelper.addDebugLog('DIRECT UPDATE ERROR: $e');
      return false;
    }
  }
}