import 'dart:async';
import 'package:flutter/services.dart';
import '../screens/debug_log_viewer_screen.dart';

class NativeVoiceService {
  static final NativeVoiceService _instance = NativeVoiceService._internal();
  factory NativeVoiceService() => _instance;
  NativeVoiceService._internal();

  static const MethodChannel _channel = MethodChannel('native_speech');
  bool _isListening = false;
  
  Function(String action, int? number, String message)? onVoiceCommand;

  Future<void> initialize() async {
    try {
      await _channel.invokeMethod('initialize');
      await DebugLogHelper.addDebugLog('VOICE: Native speech initialized');
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: Native speech init error: $e');
    }
  }

  Future<void> startListening() async {
    if (_isListening) return;
    
    try {
      _isListening = true;
      await DebugLogHelper.addDebugLog('VOICE: Starting native speech recognition');
      
      final result = await _channel.invokeMethod('startListening');
      _isListening = false;
      
      if (result != null) {
        await _processCommand(result.toString());
      }
    } catch (e) {
      _isListening = false;
      await DebugLogHelper.addDebugLog('VOICE: Native speech error: $e');
      onVoiceCommand?.call('play', null, 'Playing audio (fallback)');
    }
  }

  Future<void> _processCommand(String command) async {
    String cmd = command.toLowerCase().trim();
    await DebugLogHelper.addDebugLog('VOICE: Recognized: $cmd');
    
    // Extract numbers
    RegExp numberRegex = RegExp(r'\\d+');
    Match? numberMatch = numberRegex.firstMatch(cmd);
    int? number = numberMatch != null ? int.tryParse(numberMatch.group(0)!) : null;
    
    if (cmd.contains('play')) {
      onVoiceCommand?.call('play', null, 'Playing audio');
    } else if (cmd.contains('pause')) {
      onVoiceCommand?.call('pause', null, 'Pausing audio');
    } else if (cmd.contains('next')) {
      onVoiceCommand?.call('next_stop', null, 'Next step');
    } else if (cmd.contains('previous')) {
      onVoiceCommand?.call('previous_stop', null, 'Previous step');
    } else if (cmd.contains('repeat')) {
      onVoiceCommand?.call('repeat_stop', null, 'Repeating step');
    } else if (cmd.contains('stop') && number != null) {
      onVoiceCommand?.call('go_to_stop', number, 'Going to stop $number');
    } else {
      onVoiceCommand?.call('play', null, 'Command not recognized, playing audio');
    }
  }
}