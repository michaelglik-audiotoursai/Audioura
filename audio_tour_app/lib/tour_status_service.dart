import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';

/// Service for tracking tour requests and updating their status in the database
class TourStatusService {
  /// Creates a tour request and stores the tour_id for later status updates
  static Future<String> trackTourRequest(String tourRequest, String jobId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      if (userId != null) {
        // First, create the tour request in the database
        final trackingData = {
          'tour_request': {
            'request_string': tourRequest,
          }
        };
        
        // Send the request to create a tour
        final response = await http.put(
          Uri.parse('http://$serverIp:5003/user/$userId'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(trackingData),
        );
        
        // Query for the latest tour
        final latestResponse = await http.get(
          Uri.parse('http://$serverIp:5003/user/$userId/latest_tour'),
          headers: {'Content-Type': 'application/json'},
        );
        
        String tourId = '';
        if (latestResponse.statusCode == 200) {
          try {
            final latestTour = jsonDecode(latestResponse.body);
            if (latestTour != null && latestTour['tour_id'] != null) {
              tourId = latestTour['tour_id'];
            }
          } catch (e) {
            print('Error parsing latest tour: $e');
          }
        }
        
        // Store the mapping between job_id and tour_id for later status updates
        if (tourId.isNotEmpty) {
          // Store as individual key-value pair for reliability
          await prefs.setString('tour_id_$jobId', tourId);
          
          print('Created tour request with tour_id: $tourId for job_id: $jobId');
          return tourId;
        }
      }
    } catch (e) {
      print('Error tracking tour request: $e');
    }
    return '';
  }

  /// Updates the status of a tour request in the database
  static Future<void> updateTourStatus(String jobId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      if (userId != null) {
        // Get the tour_id from our stored mapping
        String tourId = prefs.getString('tour_id_$jobId') ?? '';
        
        // If we couldn't find the tour_id, get the latest one from the database
        if (tourId.isEmpty) {
          final response = await http.get(
            Uri.parse('http://$serverIp:5003/user/$userId/latest_tour'),
            headers: {'Content-Type': 'application/json'},
          );
          
          if (response.statusCode == 200) {
            try {
              final latestTour = jsonDecode(response.body);
              if (latestTour != null && latestTour['tour_id'] != null) {
                tourId = latestTour['tour_id'];
              }
            } catch (e) {
              print('Error parsing latest tour: $e');
            }
          }
        }
        
        // If we have a tour_id, update its status
        if (tourId.isNotEmpty) {
          final updateData = {
            'tour_status_update': {
              'tour_id': tourId,
              'status': status,
              'finished_at': DateTime.now().toIso8601String(),
            }
          };
          
          final response = await http.put(
            Uri.parse('http://$serverIp:5003/user/$userId'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(updateData),
          );
          
          print('Status update response: ${response.statusCode} - ${response.body}');
          print('Updated tour status: $jobId to $status with tour_id: $tourId');
        } else {
          print('Could not find tour_id for job_id: $jobId');
        }
      }
    } catch (e) {
      print('Error updating tour status: $e');
    }
  }
}