import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:archive/archive.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../screens/edit_tour_screen.dart';

class TourEditingService {
  static Future<String> _getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
    return 'http://$serverIp:5022';
  }
  
  static Future<Map<String, dynamic>> updateStop({
    required String tourId,
    required int stopNumber,
    required String newText,
  }) async {
    try {
      await DebugLogHelper.addDebugLog('EDIT API: Updating stop $stopNumber for tour $tourId');
      
      final baseUrl = await _getBaseUrl();
      
      final response = await http.post(
        Uri.parse('$baseUrl/tour/$tourId/update-stop'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'stop_number': stopNumber,
          'new_text': newText,
        }),
      );
      
      await DebugLogHelper.addDebugLog('EDIT API: Response status ${response.statusCode}');
      await DebugLogHelper.addDebugLog('EDIT API: Response body: ${response.body}');
      
      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        await DebugLogHelper.addDebugLog('EDIT API: Success - ${result['message']}');
        return result;
      } else {
        final error = jsonDecode(response.body);
        throw Exception(error['error'] ?? 'Update failed');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT API: Error updating stop: $e');
      rethrow;
    }
  }
  
  static Future<Map<String, dynamic>> checkJobStatus({
    required String tourId,
    required String jobId,
  }) async {
    try {
      final baseUrl = await _getBaseUrl();
      
      final response = await http.get(
        Uri.parse('$baseUrl/tour/$tourId/job-status/$jobId'),
      );
      
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      } else {
        throw Exception('Failed to check job status');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT API: Error checking job status: $e');
      rethrow;
    }
  }
  
  static Future<bool> downloadUpdatedTour({
    required String newTourId,
    required String downloadUrl,
    required String localTourPath,
  }) async {
    try {
      await DebugLogHelper.addDebugLog('EDIT API: Downloading updated tour $newTourId');
      
      final baseUrl = await _getBaseUrl();
      final fullUrl = '$baseUrl$downloadUrl';
      
      final response = await http.get(Uri.parse(fullUrl));
      
      if (response.statusCode == 200) {
        // Save and extract updated tour
        final zipFile = File('$localTourPath.zip');
        await zipFile.writeAsBytes(response.bodyBytes);
        await DebugLogHelper.addDebugLog('EDIT API: Downloaded ${response.bodyBytes.length} bytes');
        
        // Extract tour files
        await _extractTourFiles(zipFile, localTourPath);
        
        await DebugLogHelper.addDebugLog('EDIT API: Tour download and extraction completed');
        return true;
      } else {
        await DebugLogHelper.addDebugLog('EDIT API: Download failed with status ${response.statusCode}');
        return false;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT API: Download error: $e');
      return false;
    }
  }
  
  static Future<void> _extractTourFiles(File zipFile, String tourPath) async {
    try {
      final bytes = await zipFile.readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      
      // Extract files to tour directory
      for (final file in archive) {
        final filename = file.name;
        if (file.isFile && filename != null && filename.isNotEmpty) {
          final data = file.content as List<int>?;
          if (data != null && data.isNotEmpty) {
            final extractedFile = File('$tourPath/$filename');
            await extractedFile.writeAsBytes(data);
          }
        }
      }
      
      // Clean up ZIP file
      if (await zipFile.exists()) {
        await zipFile.delete();
      }
      
      await DebugLogHelper.addDebugLog('EDIT API: Extracted ${archive.length} files');
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT API: Error extracting files: $e');
      rethrow;
    }
  }
  
  static Future<Map<String, dynamic>> updateMultipleStops({
    required String tourId,
    required List<Map<String, dynamic>> allStops,
  }) async {
    try {
      // Direct logging test
      await DebugLogHelper.addDebugLog('SERVICE_DIRECT: updateMultipleStops method called with tourId: $tourId');
      await DebugLogHelper.addDebugLog('SERVICE_DIRECT: ===== TourEditingService.updateMultipleStops CALLED =====');
      await DebugLogHelper.addDebugLog('EDIT API: Tour ID: $tourId');
      await DebugLogHelper.addDebugLog('EDIT API: Received ${allStops.length} stops to process');
      
      // Debug log ALL stops being sent
      for (int i = 0; i < allStops.length; i++) {
        final stop = allStops[i];
        await DebugLogHelper.addDebugLog('EDIT API: Stop $i - Number: ${stop['stop_number']}, Action: ${stop['action']}, Modified: ${stop['modified']}');
        await DebugLogHelper.addDebugLog('EDIT API: Stop $i - Has custom audio: ${stop['has_custom_audio']}, Audio path: ${stop['custom_audio_path']}');
      }
      
      final baseUrl = await _getBaseUrl();
      
      // Prepare ALL stops with change detection and flag support (REQ-020)
      final stopsData = <Map<String, dynamic>>[];
      
      for (final stop in allStops) {
        final stopData = {
          'stop_number': stop['stop_number'],
          'text': stop['text'],
          'original_text': stop['original_text'],
          'action': stop['action'] ?? (stop['modified'] == true ? 'modify' : 'unchanged'),
          'generate_audio_from_text': stop['generate_audio_from_text'] ?? true,
          'has_custom_audio': stop['has_custom_audio'] ?? false,
          'audio_source': stop['audio_source'] ?? 'tts_generated',
        };
        
        // Clean logic - conflicts prevented in UI
        final hasCustomAudio = stop['has_custom_audio'] ?? false;
        
        if (hasCustomAudio && stop['custom_audio_path'] != null) {
          // Custom audio mode
          try {
            final audioFile = File(stop['custom_audio_path']);
            if (await audioFile.exists()) {
              final audioBytes = await audioFile.readAsBytes();
              
              // Debug: Check actual file format
              final first20Bytes = audioBytes.take(20).toList();
              await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - First 20 bytes: $first20Bytes');
              
              if (audioBytes.length >= 12) {
                final riffHeader = String.fromCharCodes(audioBytes.take(4));
                final waveHeader = String.fromCharCodes(audioBytes.skip(8).take(4));
                await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - Headers: "$riffHeader" + "$waveHeader"');
                
                if (riffHeader == 'RIFF' && waveHeader == 'WAVE') {
                  await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - Confirmed WAV format');
                } else {
                  await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - WARNING: Not WAV format! Headers: $riffHeader/$waveHeader');
                }
              }
              
              final base64Audio = base64Encode(audioBytes);
              stopData['custom_audio_data'] = base64Audio;
              await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - Using custom audio (${audioBytes.length} bytes)');
            } else {
              await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - Custom audio file not found: ${stop['custom_audio_path']}');
            }
          } catch (e) {
            await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - Error encoding custom audio: $e');
          }
        } else {
          // TTS mode - generate based on flag (already determined by mobile app)
          await DebugLogHelper.addDebugLog('EDIT API: Stop ${stop['stop_number']} - TTS mode, generate: ${stopData['generate_audio_from_text']}');
        }
        
        stopsData.add(stopData);
      }
      
      await DebugLogHelper.addDebugLog('EDIT API: ===== MAKING HTTP POST REQUEST =====');
      await DebugLogHelper.addDebugLog('EDIT API: URL: $baseUrl/tour/$tourId/update-multiple-stops');
      await DebugLogHelper.addDebugLog('EDIT API: Payload stops count: ${stopsData.length}');
      
      final response = await http.post(
        Uri.parse('$baseUrl/tour/$tourId/update-multiple-stops'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'stops': stopsData,
        }),
      );
      
      await DebugLogHelper.addDebugLog('EDIT API: ===== HTTP RESPONSE RECEIVED =====');
      await DebugLogHelper.addDebugLog('EDIT API: Response status: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('EDIT API: Response body: ${response.body}');
      
      if (response.statusCode == 200) {
        final result = jsonDecode(response.body);
        await DebugLogHelper.addDebugLog('EDIT API: Save success - ${result['message']}');
        return result;
      } else if (response.statusCode == 400) {
        final error = jsonDecode(response.body);
        if (error['error_code'] == 'MISSING_AUDIO_DATA') {
          await DebugLogHelper.addDebugLog('EDIT API: Missing audio data error - ${error['message']}');
          throw Exception('Custom audio error: ${error['message']}');
        }
        throw Exception(error['message'] ?? error['error'] ?? 'Save failed');
      } else {
        final error = jsonDecode(response.body);
        throw Exception(error['error'] ?? 'Save failed');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('EDIT API: Error in save: $e');
      rethrow;
    }
  }
}