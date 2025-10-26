import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../screens/debug_log_viewer_screen.dart';

class CustomAudioService {
  static final CustomAudioService _instance = CustomAudioService._internal();
  factory CustomAudioService() => _instance;
  CustomAudioService._internal();

  Future<String> _getServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
    return 'http://$serverIp:5023';
  }

  Future<String> _getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id') ?? 'default_user';
  }

  Future<Map<String, dynamic>> uploadCustomAudio({
    required String tourId,
    required int stopNumber,
    required String audioPath,
  }) async {
    try {
      final serverUrl = await _getServerUrl();
      final userId = await _getUserId();
      
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Uploading audio for tour $tourId, stop $stopNumber');
      
      // Read audio file and convert to base64
      final audioFile = File(audioPath);
      final audioBytes = await audioFile.readAsBytes();
      final base64Audio = base64Encode(audioBytes);
      
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Audio file size: ${audioBytes.length} bytes');
      
      var response = await http.post(
        Uri.parse('$serverUrl/tour/$tourId/stop/$stopNumber/custom-audio'),
        headers: {
          'Content-Type': 'application/json',
          'X-User-ID': userId,
        },
        body: json.encode({
          'custom_audio_data': base64Audio,
        }),
      );
      
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Upload response: ${response.statusCode} - ${response.body}');
      
      if (response.statusCode == 200) {
        final responseData = json.decode(response.body);
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Upload successful');
        return {'success': true, 'message': responseData['message'] ?? 'Upload successful'};
      } else {
        // Parse structured error response
        try {
          final errorData = json.decode(response.body);
          await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Structured error: ${errorData['error']} - ${errorData['message']}');
          return {
            'success': false,
            'error': errorData['error'],
            'message': errorData['message'],
            'details': errorData['details'],
          };
        } catch (parseError) {
          await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Upload failed - ${response.statusCode}');
          return {
            'success': false,
            'error': 'HTTP_ERROR',
            'message': 'Upload failed with status ${response.statusCode}',
          };
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Upload error - $e');
      return {
        'success': false,
        'error': 'NETWORK_ERROR',
        'message': 'Network error: $e',
      };
    }
  }

  Future<bool> removeCustomAudio({
    required String tourId,
    required int stopNumber,
    int? version,
  }) async {
    try {
      final serverUrl = await _getServerUrl();
      final userId = await _getUserId();
      
      String url = '$serverUrl/tour/$tourId/stop/$stopNumber/custom-audio';
      if (version != null) {
        url += '?version=$version';
      }
      
      var response = await http.delete(
        Uri.parse(url),
        headers: {'X-User-ID': userId},
      );
      
      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Remove successful');
        return true;
      } else {
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Remove failed - ${response.statusCode}');
        return false;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Remove error - $e');
      return false;
    }
  }

  Future<List<AudioVersion>> getAudioVersions({
    required String tourId,
    required int stopNumber,
  }) async {
    try {
      final serverUrl = await _getServerUrl();
      
      var response = await http.get(
        Uri.parse('$serverUrl/tour/$tourId/stop/$stopNumber/audio-versions'),
      );
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final versions = (data['versions'] as List)
            .map((v) => AudioVersion.fromJson(v))
            .toList();
        
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Found ${versions.length} versions');
        return versions;
      } else {
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Get versions failed - ${response.statusCode}');
        return [];
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Get versions error - $e');
      return [];
    }
  }

  Future<Map<String, dynamic>> getTourAudioMetadata(String tourId) async {
    try {
      final serverUrl = await _getServerUrl();
      
      var response = await http.get(
        Uri.parse('$serverUrl/tour/$tourId/audio-metadata'),
      );
      
      if (response.statusCode == 200) {
        return json.decode(response.body);
      } else {
        await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Get metadata failed - ${response.statusCode}');
        return {};
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CUSTOM_AUDIO: Get metadata error - $e');
      return {};
    }
  }
}

class AudioVersion {
  final String userId;
  final int version;
  final int fileSize;
  final String uploadDate;
  final int likes;
  final int downloads;
  final int duration;

  AudioVersion({
    required this.userId,
    required this.version,
    required this.fileSize,
    required this.uploadDate,
    required this.likes,
    required this.downloads,
    required this.duration,
  });

  factory AudioVersion.fromJson(Map<String, dynamic> json) {
    return AudioVersion(
      userId: json['user_id'] ?? '',
      version: json['version'] ?? 1,
      fileSize: json['file_size'] ?? 0,
      uploadDate: json['upload_date'] ?? '',
      likes: json['likes'] ?? 0,
      downloads: json['downloads'] ?? 0,
      duration: json['duration'] ?? 0,
    );
  }
}