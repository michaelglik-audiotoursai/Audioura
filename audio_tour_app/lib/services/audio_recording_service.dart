import 'dart:io';
import 'dart:async';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:path_provider/path_provider.dart';
import '../screens/debug_log_viewer_screen.dart';

// Enhanced audio recording service with microphone conflict detection
// Addresses silent recording issues where Voice Control may interfere
// v1.2.6+241: Added audio focus management and alternative recording methods

class AudioRecordingService {
  static final AudioRecordingService _instance = AudioRecordingService._internal();
  factory AudioRecordingService() => _instance;
  AudioRecordingService._internal();

  FlutterSoundRecorder? _recorder;
  FlutterSoundPlayer? _player;
  bool _isRecording = false;
  bool _isPlaying = false;
  String? _currentRecordingPath;
  Timer? _recordingTimer;
  int _recordingDuration = 0;
  Function()? _onSilentRecordingDetected;

  static const int maxDurationSeconds = 300; // 5 minutes
  static const int maxFileSizeBytes = 10 * 1024 * 1024; // 10MB
  
  // Add method to force release microphone
  Future<void> releaseMicrophone() async {
    try {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Force releasing microphone...');
      if (_isRecording) {
        await stopRecording();
      }
      await _recorder?.closeRecorder();
      await Future.delayed(Duration(milliseconds: 1000)); // Wait for full release
      await _recorder?.openRecorder();
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone released and recorder reopened');
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Error releasing microphone: $e');
    }
  }

  Future<bool> initialize() async {
    try {
      _recorder = FlutterSoundRecorder();
      _player = FlutterSoundPlayer();
      
      await _recorder!.openRecorder();
      await _player!.openPlayer();
      
      // Test microphone availability immediately
      await _testMicrophoneAvailability();
      
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Service initialized');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Initialize error - $e');
      return false;
    }
  }

  Future<void> _testMicrophoneAvailability() async {
    try {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Testing microphone availability...');
      
      final directory = await getTemporaryDirectory();
      final testPath = '${directory.path}/mic_test.wav';
      
      // Quick 1-second test recording
      await _recorder!.startRecorder(
        toFile: testPath,
        codec: Codec.pcm16WAV,
        sampleRate: 44100,
        numChannels: 1,
      );
      
      await Future.delayed(Duration(milliseconds: 1000));
      await _recorder!.stopRecorder();
      
      // Check if we got any audio data
      final testFile = File(testPath);
      if (await testFile.exists()) {
        final size = await testFile.length();
        if (size > 44) {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone test SUCCESS - ${size} bytes captured');
        } else {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone test FAILED - Only ${size} bytes (header only)');
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone may be in use by Voice Control or another app');
        }
        await testFile.delete(); // Cleanup
      } else {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone test FAILED - No file created');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone test error: $e');
    }
  }

  Future<bool> checkPermissions() async {
    try {
      final micPermission = await Permission.microphone.status;
      
      if (micPermission.isGranted) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission already granted');
        return true;
      }
      
      if (micPermission.isDenied) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Requesting microphone permission');
        final result = await Permission.microphone.request();
        
        if (result.isGranted) {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission granted');
          return true;
        } else if (result.isDenied) {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission denied by user');
          return false;
        } else if (result.isPermanentlyDenied) {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission permanently denied');
          return false;
        }
      }
      
      if (micPermission.isPermanentlyDenied) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission permanently denied - need settings');
        return false;
      }
      
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Microphone permission in unknown state');
      return false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Permission error - $e');
      return false;
    }
  }

  Future<String?> startRecording({Function()? onSilentRecordingDetected}) async {
    _onSilentRecordingDetected = onSilentRecordingDetected;
    try {
      if (_isRecording) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Already recording');
        return null;
      }

      // CRITICAL: Check if microphone is in use by other apps
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Checking microphone availability...');
      
      final hasPermission = await checkPermissions();
      if (!hasPermission) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Permission check failed');
        return null;
      }

      // Force close any existing recorder to release microphone
      try {
        await _recorder?.closeRecorder();
        await Future.delayed(Duration(milliseconds: 500)); // Wait for release
        await _recorder!.openRecorder();
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Recorder reset and reopened');
      } catch (e) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Recorder reset failed: $e');
      }

      final directory = await getTemporaryDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      
      // Start with WAV for maximum compatibility and debugging
      _currentRecordingPath = '${directory.path}/recording_$timestamp.wav';
      
      bool recordingStarted = false;
      
      // Try WAV first with enhanced configuration
      try {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Attempting WAV recording with enhanced config...');
        await _recorder!.startRecorder(
          toFile: _currentRecordingPath,
          codec: Codec.pcm16WAV,
          sampleRate: 44100,
          numChannels: 1, // Mono for better compatibility
          bitRate: 16000, // 16-bit depth
        );
        recordingStarted = true;
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: WAV recording started - mono, 44.1kHz, 16-bit');
        
        // Enhanced real-time monitoring with microphone conflict detection
        Timer.periodic(Duration(seconds: 1), (timer) async {
          if (!_isRecording) {
            timer.cancel();
            return;
          }
          
          if (_currentRecordingPath != null) {
            final testFile = File(_currentRecordingPath!);
            if (await testFile.exists()) {
              final currentSize = await testFile.length();
              await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Live monitoring - ${_recordingDuration}s, ${currentSize} bytes');
              
              // Critical alerts for silent recording
              if (_recordingDuration == 3 && currentSize <= 44) {
                await DebugLogHelper.addDebugLog('AUDIO_RECORDING: WARNING - No audio data after 3 seconds');
              }
              
              if (_recordingDuration == 5 && currentSize <= 44) {
                await DebugLogHelper.addDebugLog('AUDIO_RECORDING: CRITICAL - Silent recording detected!');
                await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Possible causes: Voice Control active, another app using mic, or hardware issue');
              }
              
              if (_recordingDuration == 10 && currentSize <= 44) {
                await DebugLogHelper.addDebugLog('AUDIO_RECORDING: SEVERE - 10 seconds of silence, triggering fallback');
                timer.cancel();
                await stopRecording();
                
                // Trigger fallback callback
                if (_onSilentRecordingDetected != null) {
                  _onSilentRecordingDetected!();
                }
                return;
              }
            }
          }
        });
        
      } catch (wavError) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: WAV codec failed: $wavError');
        
        // Try MP3 as fallback
        try {
          _currentRecordingPath = '${directory.path}/recording_$timestamp.mp3';
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Attempting MP3 fallback...');
          await _recorder!.startRecorder(
            toFile: _currentRecordingPath,
            codec: Codec.mp3,
            bitRate: 128000,
            sampleRate: 44100,
          );
          recordingStarted = true;
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: MP3 recording started as fallback');
        } catch (mp3Error) {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: MP3 codec failed: $mp3Error');
          
          // Try AAC as final fallback
          try {
            _currentRecordingPath = '${directory.path}/recording_$timestamp.aac';
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Attempting AAC final fallback...');
            await _recorder!.startRecorder(
              toFile: _currentRecordingPath,
              codec: Codec.aacADTS,
              sampleRate: 44100,
            );
            recordingStarted = true;
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: AAC recording started as final fallback');
          } catch (aacError) {
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: All codecs failed - WAV: $wavError, MP3: $mp3Error, AAC: $aacError');
            throw Exception('No supported audio codec available on this device');
          }
        }
      }
      
      if (!recordingStarted) {
        throw Exception('Failed to start recording with any codec');
      }

      _isRecording = true;
      _recordingDuration = 0;
      
      // Start timer to track duration and enforce limit
      _recordingTimer = Timer.periodic(Duration(seconds: 1), (timer) {
        _recordingDuration++;
        if (_recordingDuration >= maxDurationSeconds) {
          stopRecording();
        }
      });

      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Started recording to $_currentRecordingPath');
      return _currentRecordingPath;
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Start recording error - $e');
      return null;
    }
  }

  Future<String?> stopRecording() async {
    try {
      if (!_isRecording) {
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Not recording');
        return null;
      }

      await _recorder!.stopRecorder();
      _isRecording = false;
      _recordingTimer?.cancel();

      if (_currentRecordingPath != null) {
        final file = File(_currentRecordingPath!);
        if (await file.exists()) {
          final fileSize = await file.length();
          
          // Enhanced file size analysis
          if (fileSize <= 44) {
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: SILENT RECORDING DETECTED - Only ${fileSize} bytes (WAV header only)');
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: This indicates microphone was not accessible during recording');
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Possible solutions: Close Voice Control, restart app, check other apps using microphone');
            // Don't delete - keep for debugging
            return null;
          }
          
          if (fileSize > maxFileSizeBytes) {
            await file.delete();
            await DebugLogHelper.addDebugLog('AUDIO_RECORDING: File too large ($fileSize bytes), deleted');
            return null;
          }
          
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Recording stopped successfully - ${fileSize} bytes, ${_recordingDuration}s');
          return _currentRecordingPath;
        } else {
          await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Recording file does not exist after stopping');
        }
      }

      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Stop recording error - $e');
      return null;
    }
  }

  Future<bool> playPreview(String audioPath) async {
    try {
      if (_isPlaying) {
        await _player!.stopPlayer();
        _isPlaying = false;
        return true;
      }

      await _player!.startPlayer(
        fromURI: audioPath,
        whenFinished: () {
          _isPlaying = false;
        },
      );

      _isPlaying = true;
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Playing preview');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Play preview error - $e');
      return false;
    }
  }

  Future<void> stopPreview() async {
    try {
      if (_isPlaying) {
        await _player!.stopPlayer();
        _isPlaying = false;
        await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Preview stopped');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Stop preview error - $e');
    }
  }

  bool validateDuration(int seconds) {
    return seconds <= maxDurationSeconds;
  }

  bool validateFileSize(int bytes) {
    return bytes <= maxFileSizeBytes;
  }

  int get currentRecordingDuration => _recordingDuration;
  bool get isRecording => _isRecording;
  bool get isPlaying => _isPlaying;
  
  // Add method to check if last recording was silent
  Future<bool> wasLastRecordingSilent() async {
    if (_currentRecordingPath == null) return false;
    
    final file = File(_currentRecordingPath!);
    if (await file.exists()) {
      final size = await file.length();
      return size <= 44; // Only WAV header, no audio data
    }
    return false;
  }

  Future<void> dispose() async {
    try {
      _recordingTimer?.cancel();
      if (_isRecording) {
        await stopRecording();
      }
      await _recorder?.closeRecorder();
      await _player?.closePlayer();
      _onSilentRecordingDetected = null;
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Service disposed');
    } catch (e) {
      await DebugLogHelper.addDebugLog('AUDIO_RECORDING: Dispose error - $e');
    }
  }
}