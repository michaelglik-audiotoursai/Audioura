import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_volume_controller/flutter_volume_controller.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_to_text.dart';
import '../screens/debug_log_viewer_screen.dart';

class VoiceControlService {
  static final VoiceControlService _instance = VoiceControlService._internal();
  factory VoiceControlService() => _instance;
  VoiceControlService._internal();


  bool _isListening = false;
  bool _isInitialized = false;
  Timer? _listeningTimer;
  int _buttonPressCount = 0;
  Timer? _buttonTimer;
  StreamSubscription? _volumeSubscription;
  
  SpeechToText _speechToText = SpeechToText();
  bool _speechEnabled = false;
  
  Function(String action, int? stopNumber, String message)? onVoiceCommand;

  Future<void> initialize() async {
    if (_isInitialized) return;
    
    try {
      // Check microphone permission
      try {
        final micPermission = await Permission.microphone.status;
        await DebugLogHelper.addDebugLog('VOICE: Microphone permission: $micPermission');
        
        if (!micPermission.isGranted) {
          final result = await Permission.microphone.request();
          await DebugLogHelper.addDebugLog('VOICE: Microphone permission request result: $result');
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('VOICE: Permission check error: $e');
      }
      
      try {
        _speechEnabled = await _speechToText.initialize();
        await DebugLogHelper.addDebugLog('VOICE: Speech-to-text initialized: $_speechEnabled');
      } catch (e) {
        await DebugLogHelper.addDebugLog('VOICE: Speech-to-text init error: $e');
      }

      // Listen for volume button events
      try {
        FlutterVolumeController.addListener((volume) async {
          await DebugLogHelper.addDebugLog('VOICE: Volume changed to $volume');
          _handleVolumeButtonPress();
        });
        await DebugLogHelper.addDebugLog('VOICE: Volume button listener added');
      } catch (e) {
        await DebugLogHelper.addDebugLog('VOICE: Volume listener error: $e');
      }

      _isInitialized = true;
      await DebugLogHelper.addDebugLog('VOICE: Voice control service initialized successfully');
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: Error initializing voice control: $e');
    }
  }

  void _handleVolumeButtonPress() async {
    _buttonPressCount++;
    await DebugLogHelper.addDebugLog('VOICE: Volume button press $_buttonPressCount/3 at ${DateTime.now()}');
    
    // Reset counter after 500ms (very short window for rapid presses)
    _buttonTimer?.cancel();
    _buttonTimer = Timer(Duration(milliseconds: 500), () async {
      await DebugLogHelper.addDebugLog('VOICE: Button press counter reset');
      _buttonPressCount = 0;
    });

    // Triple press detected
    if (_buttonPressCount >= 3) {
      _buttonPressCount = 0;
      _buttonTimer?.cancel();
      await DebugLogHelper.addDebugLog('VOICE: Triple press detected - opening voice dialog');
      startVoiceListening(); // This will trigger show_dialog
    }
  }

  void startVoiceListening() async {
    if (!_speechEnabled || _isListening) {
      onVoiceCommand?.call('play', null, 'Playing audio (fallback)');
      return;
    }
    
    try {
      _isListening = true;
      await DebugLogHelper.addDebugLog('VOICE: Starting ML Kit speech recognition');
      
      // Pause all audio during recognition
      onVoiceCommand?.call('pause_for_listening', null, 'Listening...');
      
      await _speechToText.listen(
        onResult: (result) async {
          await DebugLogHelper.addDebugLog('VOICE: Speech result received - Final: ${result.finalResult}, Words: "${result.recognizedWords}"');
          if (result.finalResult) {
            _isListening = false;
            await DebugLogHelper.addDebugLog('VOICE: Processing final result: ${result.recognizedWords}');
            await _processAdvancedCommand(result.recognizedWords);
          }
        },
        listenFor: Duration(seconds: 5),
        partialResults: true,
        localeId: 'en_US',
      );
      
      // Add timeout fallback
      Timer(Duration(seconds: 6), () async {
        if (_isListening) {
          _isListening = false;
          await DebugLogHelper.addDebugLog('VOICE: Speech recognition timed out - no result received');
          onVoiceCommand?.call('play', null, 'Voice recognition timed out, playing audio');
        }
      });
    } catch (e) {
      _isListening = false;
      await DebugLogHelper.addDebugLog('VOICE: ML Kit listen error: $e');
      await DebugLogHelper.addDebugLog('VOICE: Speech-to-text available: $_speechEnabled');
      onVoiceCommand?.call('play', null, 'Speech recognition error, playing audio');
    }
  }
  
  Future<void> _processVoiceResult(String result) async {
    _isListening = false;
    String command = result.toLowerCase();
    await DebugLogHelper.addDebugLog('VOICE: Recognized: $command');
    
    if (command.contains('next tour')) {
      onVoiceCommand?.call('next_tour', null, 'Command "$result" recognized. Going to next tour');
    } else if (command.contains('next stop') || command.contains('play next stop') || command.contains('next') || command.contains('play next')) {
      onVoiceCommand?.call('next_stop', null, 'Command "$result" recognized. Playing next audio');
    } else if (command.contains('previous stop') || command.contains('play previous stop') || command.contains('previous') || command.contains('back') || command.contains('play previous')) {
      onVoiceCommand?.call('previous_stop', null, 'Command "$result" recognized. Playing previous audio');
    } else if (command.contains('repeat')) {
      onVoiceCommand?.call('repeat_stop', null, 'Command "$result" recognized. Repeating current audio');
    } else if (command.contains('pause') || command.contains('stop')) {
      onVoiceCommand?.call('pause', null, 'Command "$result" recognized. Pausing audio');
    } else {
      onVoiceCommand?.call('play', null, 'Command "$result" recognized. Playing audio');
    }
  }



  Future<void> processVoiceCommand(String voiceText) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      // Get current tour state (you'll need to pass this from the audio player)
      final currentStop = prefs.getInt('current_stop') ?? 0;
      final totalStops = prefs.getInt('total_stops') ?? 10;

      final response = await http.post(
        Uri.parse('http://$serverIp:5008/process-voice-command'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'text': voiceText,
          'current_stop': currentStop,
          'total_stops': totalStops,
        }),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final action = data['action'];
        final stopNumber = data['stop_number'];
        final message = data['message'];

        await DebugLogHelper.addDebugLog('VOICE: Command processed - Action: $action, Message: $message');
        
        // Callback to audio player
        onVoiceCommand?.call(action, stopNumber, message);
      } else {
        await DebugLogHelper.addDebugLog('VOICE: Server error: ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: Error processing voice command: $e');
    }
  }


  
  Future<void> _processAdvancedCommand(String command) async {
    String cmd = command.toLowerCase().trim();
    // Remove "play" prefix if present
    if (cmd.startsWith('play ')) {
      cmd = cmd.substring(5).trim();
    }
    
    await DebugLogHelper.addDebugLog('VOICE: Processing command: "$cmd"');
    
    // Extract numbers from command
    RegExp numberRegex = RegExp(r'\d+');
    Match? numberMatch = numberRegex.firstMatch(cmd);
    int? seconds = numberMatch != null ? int.tryParse(numberMatch.group(0)!) : 10; // Default 10 seconds
    
    if (cmd.contains('next tour') || cmd.contains('nexttour') || cmd.contains('next door')) {
      await DebugLogHelper.addDebugLog('VOICE: NEXT TOUR command');
      onVoiceCommand?.call('next_tour', null, 'Next tour');
    } else if (cmd.contains('next stop') || cmd.contains('next step') || (cmd.contains('next') && !cmd.contains('tour'))) {
      await DebugLogHelper.addDebugLog('VOICE: NEXT command - move pointer and play');
      onVoiceCommand?.call('next_and_play', null, 'Next step');
    } else if (cmd.contains('previous tour') || cmd.contains('previoustour')) {
      await DebugLogHelper.addDebugLog('VOICE: PREVIOUS TOUR command');
      onVoiceCommand?.call('previous_tour', null, 'Previous tour');
    } else if (cmd.contains('forward') || (cmd.contains('move') && cmd.contains('forward'))) {
      await DebugLogHelper.addDebugLog('VOICE: FORWARD command - seek and play');
      onVoiceCommand?.call('forward_and_play', seconds, 'Forward $seconds seconds');
    } else if (cmd.contains('backward') || (cmd.contains('move') && cmd.contains('backward'))) {
      await DebugLogHelper.addDebugLog('VOICE: BACKWARD command - seek and play');
      onVoiceCommand?.call('backward_and_play', seconds, 'Backward $seconds seconds');
    } else if (cmd.contains('previous stop') || cmd.contains('previous step') || (cmd.contains('previous') && !cmd.contains('tour')) || (cmd.contains('back') && !cmd.contains('backward'))) {
      await DebugLogHelper.addDebugLog('VOICE: PREVIOUS command - move pointer and play');
      onVoiceCommand?.call('previous_and_play', null, 'Previous step');
    } else if (cmd.contains('repeat')) {
      await DebugLogHelper.addDebugLog('VOICE: REPEAT command - reset to beginning and play');
      onVoiceCommand?.call('repeat_and_play', null, 'Repeating from beginning');
    } else if (cmd.contains('pause') || cmd.contains('stop')) {
      await DebugLogHelper.addDebugLog('VOICE: PAUSE command');
      onVoiceCommand?.call('pause', null, 'Pausing audio');
    } else if (cmd.isEmpty || cmd.contains('play')) {
      await DebugLogHelper.addDebugLog('VOICE: PLAY command - resume current audio');
      onVoiceCommand?.call('play', null, 'Playing audio');
    } else {
      await DebugLogHelper.addDebugLog('VOICE: UNRECOGNIZED - resume current audio');
      onVoiceCommand?.call('play', null, 'Command not recognized, playing audio');
    }
  }

  void dispose() {
    _listeningTimer?.cancel();
    _buttonTimer?.cancel();
    _volumeSubscription?.cancel();
    // Speech-to-text cleanup handled automatically
  }
}