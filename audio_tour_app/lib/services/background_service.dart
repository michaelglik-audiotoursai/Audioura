import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';

import '../screens/debug_log_viewer_screen.dart';
import 'notification_service.dart';
import 'tour_status_service.dart';

class BackgroundService {
  static Timer? _backgroundTimer;
  
  static void startBackgroundMonitoring() {
    _backgroundTimer?.cancel();
    _backgroundTimer = Timer.periodic(const Duration(minutes: 2), (timer) async {
      await checkBackgroundTours();
    });
  }
  
  static void stopBackgroundMonitoring() {
    _backgroundTimer?.cancel();
  }
  
  static Future<void> checkBackgroundTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
      
      // Process each tour independently to avoid interference
      for (String tourJson in List.from(pendingTours)) {
        try {
          final tour = jsonDecode(tourJson);
          final jobId = tour['jobId'];
          final location = tour['location'];
          final apiBaseUrl = tour['apiBaseUrl'];
          
          try {
            await DebugLogHelper.addDebugLog('Checking tour status: $apiBaseUrl/status/$jobId');
            final response = await http.get(Uri.parse('$apiBaseUrl/status/$jobId'));
            
            await DebugLogHelper.addDebugLog('Status response: ${response.statusCode}');
            if (response.statusCode == 200) {
              final status = jsonDecode(response.body);
              await DebugLogHelper.addDebugLog('Tour status: ${status['status']}');
              
              if (status['status'] == 'completed') {
                // Remove this specific tour from pending list
                final updatedPending = prefs.getStringList('pending_background_tours') ?? [];
                updatedPending.remove(tourJson);
                await prefs.setStringList('pending_background_tours', updatedPending);
                
                // Log completion
                await DebugLogHelper.addDebugLog('Background tour completed: $jobId');
                
                // Update database status to completed
                // Store the request string for this job ID
                await prefs.setString('request_$jobId', location);
                await _updateBackgroundTourStatus(jobId, 'completed');
                
                // Auto-download background tour to My Tours (notification is shown inside this method)
                await _autoDownloadBackgroundTour(jobId, location, status);
                
                print('Background tour ready: $location (Job: $jobId)');
                await DebugLogHelper.addDebugLog('Tour completed: $location');
                await DebugLogHelper.addDebugLog('Job ID: $jobId');
              }
            }
          } catch (e) {
            await DebugLogHelper.addDebugLog('Error connecting to server: $e');
            print('Error connecting to server: $e');
          }
        } catch (e) {
          final tourData = jsonDecode(tourJson);
          print('Error processing background tour ${tourData['jobId']} (${tourData['location']}): $e');
          // Continue with other tours even if one fails
        }
      }
    } catch (e) {
      print('Background check error: $e');
    }
  }
  
  static Future<void> _updateBackgroundTourStatus(String jobId, String status) async {
    try {
      // Use the TourStatusService to update the status
      // This ensures consistent behavior between foreground and background tours
      await DebugLogHelper.addDebugLog('Updating background tour status via TourStatusService: $jobId to $status');
      
      // Use the imported TourStatusService
      await TourStatusService.updateTourStatus(jobId, status);
      
    } catch (e) {
      print('Error updating background tour status: $e');
      await DebugLogHelper.addDebugLog('Error updating background tour status: $e');
    }
  }
  
  static Future<void> _autoDownloadBackgroundTour(String jobId, String location, [Map<String, dynamic>? statusData]) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      await DebugLogHelper.addDebugLog('Downloading tour from: http://$serverIp:5002/download/$jobId');
      
      // Show notification first to ensure user is notified even if download fails
      await NotificationService.showTourReadyNotification(location);
      
      try {
        final response = await http.get(Uri.parse('http://$serverIp:5002/download/$jobId'));
      
        if (response.statusCode == 200) {
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
          
          final tours = prefs.getStringList('saved_tours') ?? [];
          // Generate unique title for background tours too
          String uniqueTitle = _generateUniqueTitle(location, tours);
          
          // Get the stop count from preferences if available
          final stopCount = prefs.getString('stop_count_$jobId') ?? '10';
          
          // Extract coordinates if available in status data
          double? lat;
          double? lng;
          if (statusData != null && 
              statusData.containsKey('coordinates') && 
              statusData['coordinates'] != null && 
              statusData['coordinates'] is List && 
              statusData['coordinates'].length >= 2) {
            lat = statusData['coordinates'][0]?.toDouble();
            lng = statusData['coordinates'][1]?.toDouble();
            await DebugLogHelper.addDebugLog('Using coordinates: $lat, $lng');
          }
          
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
          
          // Remove from background tours list
          final backgroundTours = prefs.getStringList('background_tours') ?? [];
          backgroundTours.removeWhere((bgTour) {
            final bgTourData = jsonDecode(bgTour);
            return bgTourData['id'] == jobId;
          });
          await prefs.setStringList('background_tours', backgroundTours);
          
          print('Background tour auto-downloaded to My Tours: $location');
          await DebugLogHelper.addDebugLog('Auto-downloaded: $location');
          await DebugLogHelper.addDebugLog('Moved to My Tours tab');
          await DebugLogHelper.addDebugLog('Removed from Background tab');
        } else {
          await DebugLogHelper.addDebugLog('Download failed: HTTP ${response.statusCode}');
          await DebugLogHelper.addDebugLog('Response: ${response.body}');
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('Error downloading tour: $e');
        throw Exception('Failed to download tour: $e');
      }
    } catch (e) {
      print('Error auto-downloading background tour: $e');
      await DebugLogHelper.addDebugLog('Error auto-downloading tour: $e');
    }
  }
  
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