import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'server_api.dart';
import 'direct_db_update.dart';
import 'direct_update_api.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Service for tracking tour requests and updating their status in the database
class TourStatusService {
  /// Creates a tour request and stores the tour_id for later status updates
  static Future<String> trackTourRequest(String tourRequest, String jobId, {int stopCount = 10}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      if (userId != null) {
        // Generate a tour_id explicitly
        final timestamp = DateTime.now().millisecondsSinceEpoch.toRadixString(16);
        final tourId = 'tour_$timestamp';
        
        // Create the tour request with explicit tour_id
        final trackingData = {
          'tour_request': {
            'request_string': tourRequest,
            'tour_id': tourId,
            'total_stops': stopCount,
          }
        };
        
        print('Creating tour request with explicit tour_id: $tourId');
        
        // Send the request to create a tour
        final response = await http.put(
          Uri.parse('http://$serverIp:5003/user/$userId'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(trackingData),
        );
        
        print('Tour creation response: ${response.statusCode}');
        
        // Store the mapping between job_id and tour_id for later status updates
        await prefs.setString('tour_id_$jobId', tourId);
        await prefs.setString('request_$jobId', tourRequest);
        
        // Log the SQL that would be executed
        final sql = "INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at) VALUES ('$userId', '$tourId', '$tourRequest', 'started', '${DateTime.now().toIso8601String()}')";
        await DebugLogHelper.addDebugLog('WOULD EXECUTE SQL: $sql');
        
        print('Created tour request with tour_id: $tourId for job_id: $jobId');
        return tourId;
      }
    } catch (e) {
      print('Error tracking tour request: $e');
    }
    return '';
  }

  /// Updates the status of a tour request in the database using direct SQL
  static Future<void> updateTourStatus(String jobId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      
      if (userId != null) {
        // Get the tour_id from our stored mapping
        String tourId = prefs.getString('tour_id_$jobId') ?? '';
        String requestString = prefs.getString('request_$jobId') ?? '';
        
        await DebugLogHelper.addDebugLog('Looking for tour_id for job: $jobId, found: $tourId');
        
        // If we couldn't find the tour_id but we have the request string, use it to find the tour
        if (tourId.isEmpty && requestString.isNotEmpty) {
          await DebugLogHelper.addDebugLog('No tour_id found, using request string to find tour: "$requestString"');
          
          // Use DirectDbUpdate to find or create the tour and update its status
          final success = await DirectDbUpdate.updateTourStatus(requestString, status);
          
          if (success) {
            await DebugLogHelper.addDebugLog('Successfully updated tour status via request string: $jobId to $status');
          } else {
            await DebugLogHelper.addDebugLog('Failed to update status via request string');
          }
          
          return;
        }
        
        // If we have a tour_id, update its status using direct SQL
        if (tourId.isNotEmpty) {
          await DebugLogHelper.addDebugLog('Updating status for tour_id: $tourId to $status using direct SQL');
          
          // Use UTC time for consistency
          final timestamp = DateTime.now().toUtc().toIso8601String();
          
          // Try direct update API first
          final success = await DirectUpdateApi.updateTourStatus(tourId, status, timestamp);
          
          if (success) {
            await DebugLogHelper.addDebugLog('Successfully updated tour status via direct update API: $jobId to $status with tour_id: $tourId');
          } else {
            await DebugLogHelper.addDebugLog('Failed to update status via direct update API, trying SQL...');
            
            // Fall back to SQL update
            final sqlSuccess = await ServerApi.updateTourStatus(tourId, status, timestamp);
            
            if (sqlSuccess) {
              await DebugLogHelper.addDebugLog('Successfully updated tour status via SQL: $jobId to $status with tour_id: $tourId');
            } else {
              await DebugLogHelper.addDebugLog('Failed to update status via all methods');
            }
          }
        } else {
          await DebugLogHelper.addDebugLog('Could not find or create tour_id for job_id: $jobId');
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('Error updating tour status: $e');
    }
  }
}