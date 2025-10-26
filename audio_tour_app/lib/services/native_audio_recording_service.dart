import 'dart:io';
import 'dart:async';
import 'package:permission_handler/permission_handler.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';
import '../screens/debug_log_viewer_screen.dart';

// Cross-platform native audio recording service
// Android: MediaRecorder, iOS: AVAudioRecorder

class NativeAudioRecordingService {
  static const MethodChannel _channel = MethodChannel('native_audio_recorder');
  
  bool _isRecording = false;
  String? _currentRecordingPath;
  Timer? _recordingTimer;
  int _recordingDuration = 0;

  Future<bool> initialize() async {
    try {
      final platform = Platform.isAndroid ? 'Android' : 'iOS';
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Initializing $platform native recorder');
      final result = await _channel.invokeMethod('initialize');
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: $platform initialize result: $result');
      return result == true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Initialize error: $e');
      return false;
    }
  }

  Future<bool> checkPermissions() async {
    try {
      final micPermission = await Permission.microphone.status;
      
      if (micPermission.isGranted) {
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Microphone permission granted');
        return true;
      }
      
      if (micPermission.isDenied) {
        final result = await Permission.microphone.request();
        if (result.isGranted) {
          await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Microphone permission granted after request');
          return true;
        }
      }
      
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Microphone permission denied');
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Permission error: $e');
      return false;
    }
  }

  Future<String?> startRecording() async {
    try {
      if (_isRecording) {
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Already recording');
        return null;
      }

      final hasPermission = await checkPermissions();
      if (!hasPermission) {
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Permission check failed');
        return null;
      }

      final directory = await getTemporaryDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final platform = Platform.isAndroid ? 'android' : 'ios';
      // Use flutter_sound for actual WAV creation on Android
      if (Platform.isAndroid) {
        // flutter_sound can create actual WAV files
        final extension = 'wav';
        _currentRecordingPath = '${directory.path}/flutter_sound_$timestamp.$extension';
        
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Using flutter_sound for WAV recording to $_currentRecordingPath');
        
        // Set recording state for Android flutter_sound usage
        _isRecording = true;
        _recordingDuration = 0;
        
        _recordingTimer = Timer.periodic(Duration(seconds: 1), (timer) {
          _recordingDuration++;
          _checkRecordingProgress();
        });
        
        // This will be handled by flutter_sound in the calling code
        return _currentRecordingPath;
      } else {
        // iOS: use native AAC
        final extension = 'aac';
        _currentRecordingPath = '${directory.path}/native_${platform}_$timestamp.$extension';

        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Starting $platform $extension recording to $_currentRecordingPath');
        
        final result = await _channel.invokeMethod('startRecording', {
          'filePath': _currentRecordingPath,
          'sampleRate': 44100.0,
          'channels': 1,
        });
        
        if (result == true) {
          _isRecording = true;
          _recordingDuration = 0;
          
          _recordingTimer = Timer.periodic(Duration(seconds: 1), (timer) {
            _recordingDuration++;
            _checkRecordingProgress();
          });

          await DebugLogHelper.addDebugLog('NATIVE_AUDIO: $platform recording started successfully');
          return _currentRecordingPath;
        }
      }

      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Failed to start recording');
      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Start recording error: $e');
      return null;
    }
  }

  Future<void> _checkRecordingProgress() async {
    if (_currentRecordingPath != null) {
      final file = File(_currentRecordingPath!);
      if (await file.exists()) {
        final size = await file.length();
        final platform = Platform.isAndroid ? 'Android' : 'iOS';
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: $platform recording progress - ${_recordingDuration}s, ${size} bytes');
        
        if (_recordingDuration > 3 && size <= 44) {
          await DebugLogHelper.addDebugLog('NATIVE_AUDIO: WARNING - $platform native recorder also producing silent recording');
        }
      }
    }
  }

  Future<String?> stopRecording() async {
    try {
      if (!_isRecording) {
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Not recording');
        return null;
      }

      // Stop recording state and timer first
      _isRecording = false;
      _recordingTimer?.cancel();

      if (Platform.isAndroid) {
        // For Android flutter_sound, just return the path - actual stopping handled by flutter_sound
        await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Android flutter_sound recording stopped - ${_recordingDuration}s');
        
        if (_currentRecordingPath != null) {
          final file = File(_currentRecordingPath!);
          if (await file.exists()) {
            final fileSize = await file.length();
            await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Android WAV file size: ${fileSize} bytes');
            
            if (fileSize <= 44) {
              await DebugLogHelper.addDebugLog('NATIVE_AUDIO: CRITICAL - Android flutter_sound also failed to capture audio');
              return null;
            }
            
            return _currentRecordingPath;
          }
        }
        
        return _currentRecordingPath; // Return path even if file check fails
      } else {
        // iOS: use native method
        final result = await _channel.invokeMethod('stopRecording');
        
        if (result == true && _currentRecordingPath != null) {
          final file = File(_currentRecordingPath!);
          if (await file.exists()) {
            final fileSize = await file.length();
            await DebugLogHelper.addDebugLog('NATIVE_AUDIO: iOS recording stopped - ${fileSize} bytes, ${_recordingDuration}s');
            
            if (fileSize <= 44) {
              await DebugLogHelper.addDebugLog('NATIVE_AUDIO: CRITICAL - iOS native recorder failed to capture audio');
              return null;
            }
            
            return _currentRecordingPath;
          }
        }
      }

      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Stop recording failed');
      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Stop recording error: $e');
      return null;
    }
  }

  bool get isRecording => _isRecording;
  int get currentRecordingDuration => _recordingDuration;

  Future<void> dispose() async {
    try {
      _recordingTimer?.cancel();
      if (_isRecording) {
        await stopRecording();
      }
      await _channel.invokeMethod('dispose');
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Service disposed');
    } catch (e) {
      await DebugLogHelper.addDebugLog('NATIVE_AUDIO: Dispose error: $e');
    }
  }
}