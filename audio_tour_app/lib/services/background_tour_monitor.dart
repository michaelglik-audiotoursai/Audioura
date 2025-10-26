import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'tour_status_service.dart';
import 'notification_service.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Service to monitor background tours and update their status
class BackgroundTourMonitor {
  static const int MAX_TOUR_AGE_MINUTES = 15; // 15 minute timeout
  
  /// Check for stalled background tours and mark them as failed
  static Future<void> checkStalledTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
      
      if (pendingTours.isEmpty) return;
      
      final now = DateTime.now();
      List<String> updatedPendingTours = [];
      bool hasChanges = false;
      
      for (String tourJson in pendingTours) {
        final tour = jsonDecode(tourJson);
        final startTimeStr = tour['startTime'] as String;
        final jobId = tour['jobId'] as String;
        
        // Parse the start time
        final startTime = DateTime.parse(startTimeStr);
        final ageMinutes = now.difference(startTime).inMinutes;
        
        // If tour is older than MAX_TOUR_AGE_MINUTES, mark as failed
        if (ageMinutes > MAX_TOUR_AGE_MINUTES) {
          await DebugLogHelper.addDebugLog('Background tour timed out: $jobId (age: $ageMinutes min)');
          
          // Update the tour status in the database
          await TourStatusService.updateTourStatus(jobId, 'failed');
          
          hasChanges = true;
        } else {
          // Keep this tour in the pending list
          updatedPendingTours.add(tourJson);
        }
      }
      
      // Update the pending tours list if we removed any
      if (hasChanges) {
        await prefs.setStringList('pending_background_tours', updatedPendingTours);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('Error checking stalled tours: $e');
    }
  }
  
  /// Check the status of all pending background tours
  static Future<void> checkBackgroundTourStatus() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
      
      if (pendingTours.isEmpty) return;
      
      List<String> updatedPendingTours = [];
      bool hasChanges = false;
      
      for (String tourJson in pendingTours) {
        final tour = jsonDecode(tourJson);
        final jobId = tour['jobId'] as String;
        final location = tour['location'] as String;
        final apiBaseUrl = tour['apiBaseUrl'] as String;
        final notificationsEnabled = tour['notificationsEnabled'] as bool? ?? false;
        
        try {
          // Check the status of this tour
          final response = await http.get(
            Uri.parse('$apiBaseUrl/status/$jobId'),
          );
          
          if (response.statusCode == 200) {
            final status = jsonDecode(response.body);
            
            if (status['status'] == 'completed') {
              // Tour is complete
              await DebugLogHelper.addDebugLog('Background tour completed: $jobId');
              
              // Update the tour status in the database
              await TourStatusService.updateTourStatus(jobId, 'completed');
              
              // Auto-download the tour instead of adding to completed list
              await _autoDownloadCompletedTour(jobId, location, status, notificationsEnabled);
              
              hasChanges = true;
            } else if (status['status'] == 'error') {
              // Tour failed, update status
              await DebugLogHelper.addDebugLog('Background tour failed: $jobId');
              
              // Update the tour status in the database
              await TourStatusService.updateTourStatus(jobId, 'failed');
              
              hasChanges = true;
            } else {
              // Tour still in progress, keep in pending list
              updatedPendingTours.add(tourJson);
            }
          } else {
            // Error checking status, keep in pending list
            updatedPendingTours.add(tourJson);
          }
        } catch (e) {
          // Error checking this tour, keep in pending list
          await DebugLogHelper.addDebugLog('Error checking tour $jobId: $e');
          updatedPendingTours.add(tourJson);
        }
      }
      
      // Update the pending list if we had changes
      if (hasChanges) {
        await prefs.setStringList('pending_background_tours', updatedPendingTours);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('Error checking background tours: $e');
    }
  }
  
  // Helper method to auto-download completed tours
  static Future<void> _autoDownloadCompletedTour(String jobId, String location, Map<String, dynamic> status, bool notificationsEnabled) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await DebugLogHelper.addDebugLog('Auto-downloading completed tour: $jobId');
      
      // Show notification if enabled
      if (notificationsEnabled) {
        await DebugLogHelper.addDebugLog('Showing notification for completed tour');
        await NotificationService.showTourReadyNotification(location);
      }
      
      try {
        // Download the tour
        final response = await http.get(Uri.parse('http://$serverIp:5002/download/$jobId'));
        
        if (response.statusCode == 200) {
          // Save and extract the tour
          final directory = await getApplicationDocumentsDirectory();
          final toursDir = Directory('${directory.path}/tours');
          if (!await toursDir.exists()) {
            await toursDir.create(recursive: true);
          }
          
          final zipPath = '${toursDir.path}/$jobId.zip';
          final zipFile = File(zipPath);
          await zipFile.writeAsBytes(response.bodyBytes);
          
          final bytes = await zipFile.readAsBytes();
          final archive = ZipDecoder().decodeBytes(bytes);
          
          final extractPath = '${toursDir.path}/$jobId';
          final extractDir = Directory(extractPath);
          if (await extractDir.exists()) {
            await extractDir.delete(recursive: true);
          }
          await extractDir.create(recursive: true);
          
          for (final file in archive) {
            final filename = file.name;
            if (file.isFile) {
              final data = file.content as List<int>;
              final extractedFile = File('${extractDir.path}/$filename');
              await extractedFile.create(recursive: true);
              await extractedFile.writeAsBytes(data);
            }
          }
          
          await zipFile.delete();
          
          // Get coordinates from status
          double? lat;
          double? lng;
          if (status.containsKey('coordinates') && 
              status['coordinates'] != null && 
              status['coordinates'] is List && 
              status['coordinates'].length >= 2) {
            lat = status['coordinates'][0]?.toDouble();
            lng = status['coordinates'][1]?.toDouble();
            await DebugLogHelper.addDebugLog('Using coordinates: $lat, $lng');
          }
          
          // Get stop count
          final stopCount = prefs.getString('stop_count_$jobId') ?? '10';
          
          // Add to saved tours
          final tours = prefs.getStringList('saved_tours') ?? [];
          final uniqueTitle = _generateUniqueTitle(location, tours);
          
          tours.add(jsonEncode({
            'id': jobId,
            'title': uniqueTitle,
            'original_request': location,
            'path': extractPath,
            'created': DateTime.now().toIso8601String(),
            'stops': stopCount,
            'lat': lat,
            'lng': lng,
          }));
          await prefs.setStringList('saved_tours', tours);
          
          await DebugLogHelper.addDebugLog('Tour auto-downloaded and added to My Tours: $location');
        } else {
          await DebugLogHelper.addDebugLog('Failed to download tour: HTTP ${response.statusCode}');
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('Error auto-downloading tour: $e');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('Error in _autoDownloadCompletedTour: $e');
    }
  }
  
  // Helper method to generate unique title
  static String _generateUniqueTitle(String originalTitle, List<String> existingTours) {
    // Count existing tours with similar titles
    int count = 0;
    String baseTitle = originalTitle.length > 50 ? '${originalTitle.substring(0, 50)}...' : originalTitle;
    
    for (String tourJson in existingTours) {
      final tour = jsonDecode(tourJson);
      String existingOriginal = tour['original_request'] ?? tour['title'] ?? '';
      
      if (existingOriginal.toLowerCase().contains(originalTitle.toLowerCase().substring(0, originalTitle.length > 20 ? 20 : originalTitle.length))) {
        count++;
      }
    }
    
    return count > 0 ? '$baseTitle (v${count + 1})' : baseTitle;
  }
}