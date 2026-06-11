import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../config/endpoints.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Service for tracking tour requests and updating their status via REST.
class TourStatusService {
  /// Creates a tour request entry and stores the tour_id → job_id mapping.
  static Future<String> trackTourRequest(String tourRequest, String jobId, {int stopCount = 10}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');

      if (userId != null) {
        final timestamp = DateTime.now().millisecondsSinceEpoch.toRadixString(16);
        final tourId = 'tour_$timestamp';

        final trackingData = {
          'tour_request': {
            'request_string': tourRequest,
            'tour_id': tourId,
            'total_stops': stopCount,
          }
        };

        final response = await http.put(
          await Endpoints.url(Service.userDb, '/user/$userId'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(trackingData),
        );

        await DebugLogHelper.addDebugLog('TOUR_TRACK: Created tour_id $tourId for job $jobId — HTTP ${response.statusCode}');

        // Store mapping for status updates
        await prefs.setString('tour_id_$jobId', tourId);
        await prefs.setString('request_$jobId', tourRequest);

        return tourId;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('TOUR_TRACK: Error: $e');
    }
    return '';
  }

  /// Updates tour status via POST /tour-status on the orchestrator.
  static Future<void> updateTourStatus(String jobId, String status) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final tourId = prefs.getString('tour_id_$jobId') ?? '';

      if (tourId.isEmpty) {
        await DebugLogHelper.addDebugLog('TOUR_STATUS: No tour_id found for job $jobId — skipping update');
        return;
      }

      final statusBody = {'tour_id': tourId, 'status': status};
      final response = await http.post(
        await Endpoints.url(Service.orchestrator, '/tour-status'),
        headers: await Endpoints.apiHeaders(Service.orchestrator),
        body: jsonEncode(statusBody),
      );

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body);
        final rowsAffected = body['rows_affected'] ?? 0;
        await DebugLogHelper.addDebugLog(
          'TOUR_STATUS: $tourId → $status — rows_affected: $rowsAffected'
        );
        if (rowsAffected == 0) {
          await DebugLogHelper.addDebugLog('TOUR_STATUS: ⚠️ rows_affected=0 — tour_id may not match any row');
        }
      } else {
        await DebugLogHelper.addDebugLog('TOUR_STATUS: HTTP ${response.statusCode} — ${response.body}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('TOUR_STATUS: Error updating $jobId → $status: $e');
    }
  }
}
