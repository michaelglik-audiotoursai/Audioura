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

class VoiceControlServiceNews {
  static final VoiceControlServiceNews _instance = VoiceControlServiceNews._internal();
  factory VoiceControlServiceNews() => _instance;
  VoiceControlServiceNews._internal();

  bool _isListening = false;
  bool _isInitialized = false;
  Timer? _listeningTimer;
  int _buttonPressCount = 0;
  Timer? _buttonTimer;
  StreamSubscription? _volumeSubscription;
  
  SpeechToText _speechToText = SpeechToText();
  bool _speechEnabled = false;
  
  Function(String action, int? value, String message)? onVoiceCommand;

  Future<void> initialize() async {
    if (_isInitialized) return;
    
    try {
      final micPermission = await Permission.microphone.status;
      if (!micPermission.isGranted) {
        await Permission.microphone.request();
      }
      
      _speechEnabled = await _speechToText.initialize();
      
      FlutterVolumeController.addListener((volume) async {
        _handleVolumeButtonPress();
      });

      _isInitialized = true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: Error initializing: $e');
    }
  }

  void _handleVolumeButtonPress() async {
    _buttonPressCount++;
    
    _buttonTimer?.cancel();
    _buttonTimer = Timer(Duration(milliseconds: 500), () async {
      _buttonPressCount = 0;
    });

    if (_buttonPressCount >= 3) {
      _buttonPressCount = 0;
      _buttonTimer?.cancel();
      startVoiceListening();
    }
  }

  void startVoiceListening() async {
    if (!_speechEnabled || _isListening) {
      onVoiceCommand?.call('play', null, 'Playing audio (fallback)');
      return;
    }
    
    try {
      _isListening = true;
      onVoiceCommand?.call('pause_for_listening', null, 'Listening...');
      
      await _speechToText.listen(
        onResult: (result) async {
          if (result.finalResult) {
            _isListening = false;
            await _processNewsCommand(result.recognizedWords);
          }
        },
        listenFor: Duration(seconds: 5),
        partialResults: true,
        localeId: 'en_US',
      );
      
      Timer(Duration(seconds: 6), () async {
        if (_isListening) {
          _isListening = false;
          onVoiceCommand?.call('play', null, 'Voice recognition timed out');
        }
      });
    } catch (e) {
      _isListening = false;
      onVoiceCommand?.call('play', null, 'Speech recognition error');
    }
  }
  
  Future<void> _processNewsCommand(String command) async {
    String cmd = command.toLowerCase().trim();
    
    await DebugLogHelper.addDebugLog('VOICE NEWS: Processing: "$cmd"');
    
    RegExp numberRegex = RegExp(r'\d+');
    Match? numberMatch = numberRegex.firstMatch(cmd);
    int? seconds = numberMatch != null ? int.tryParse(numberMatch.group(0)!) : 10;
    
    // Check for article navigation FIRST (before other patterns)
    if (cmd.contains('skip this article') || cmd.contains('skip the article') || 
        cmd.contains('play next article') || cmd.contains('next article')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: NEXT ARTICLE command detected');
      onVoiceCommand?.call('next_article', null, 'Next article');
    } else if (cmd.contains('play previous article') || cmd.contains('previous article')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: PREVIOUS ARTICLE command detected');
      onVoiceCommand?.call('previous_article', null, 'Previous article');
    } else if (cmd.contains('next topic') || cmd.contains('next') || cmd.contains('skip')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: NEXT TOPIC command detected');
      onVoiceCommand?.call('next_and_play', null, 'Going to next topic');
    } else if (cmd.contains('previous topic') || cmd.contains('previous')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: PREVIOUS TOPIC command detected');
      onVoiceCommand?.call('previous_and_play', null, 'Going to previous topic');
    } else if (cmd.contains('play full article') || cmd.contains('full article')) {
      onVoiceCommand?.call('play_full_article', null, 'Playing full article');
    } else if (cmd.contains('play summary') || cmd.contains('summary')) {
      onVoiceCommand?.call('play_summary', null, 'Playing summary');
    } else if (cmd.contains('list major topics') || cmd.contains('list major points') || 
               cmd.contains('list the points') || cmd.contains('list points') ||
               cmd.contains('list major points of this article') || cmd.contains('least major topics') ||
               cmd.contains('least major points')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: LIST MAJOR TOPICS command detected');
      onVoiceCommand?.call('list_major_topics', null, 'Listing major topics');
    } else if (cmd.contains('go to listen page') || cmd.contains('listen page') || 
               cmd.contains('back to listen page') || cmd.contains('return to listen') ||
               cmd.contains('return to listen page') || cmd.contains('back to article list') ||
               cmd.contains('article list') || cmd.contains('show all articles') ||
               cmd.contains('all articles')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: NAVIGATE TO LISTEN PAGE command detected');
      onVoiceCommand?.call('navigate_to_listen_page', null, 'Going to Listen Page');
    } else if (cmd.contains('what are my options') || cmd.contains('what are my commands') || 
               cmd.contains('list commands') || cmd.contains('list options') || 
               cmd.contains('what can i say') || cmd.contains('what can i ask') ||
               cmd.contains('help') || cmd.contains('commands') || cmd.contains('at least my options')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: HELP COMMANDS detected');
      onVoiceCommand?.call('show_help', null, 'Showing help commands');
    } else if (cmd.contains('play topic') || cmd.contains('play point') || 
               cmd.contains('play one') || cmd.contains('play two') || cmd.contains('play three') ||
               cmd.contains('play four') || cmd.contains('play five') || cmd.contains('play this one')) {
      await DebugLogHelper.addDebugLog('VOICE NEWS: PLAY TOPIC command detected');
      int topicNumber = 1;
      if (cmd.contains('one') || cmd.contains('1')) topicNumber = 1;
      else if (cmd.contains('two') || cmd.contains('2')) topicNumber = 2;
      else if (cmd.contains('three') || cmd.contains('3')) topicNumber = 3;
      else if (cmd.contains('four') || cmd.contains('4')) topicNumber = 4;
      else if (cmd.contains('five') || cmd.contains('5')) topicNumber = 5;
      else if (numberMatch != null) topicNumber = int.tryParse(numberMatch.group(0)!) ?? 1;
      onVoiceCommand?.call('play_topic', topicNumber, 'Playing topic $topicNumber');
    } else if (cmd.contains('repeat')) {
      onVoiceCommand?.call('repeat_and_play', null, 'Repeating from beginning');
    } else if (cmd.contains('forward')) {
      onVoiceCommand?.call('forward', seconds, 'Forward $seconds seconds');
    } else if (cmd.contains('backward') || cmd.contains('return backward')) {
      onVoiceCommand?.call('backward', seconds, 'Backward $seconds seconds');
    } else if (cmd.contains('play') && !cmd.contains('play next') && !cmd.contains('play previous') && 
               !cmd.contains('play full') && !cmd.contains('play summary') && !cmd.contains('play topic') && !cmd.contains('play point')) {
      // Try fuzzy topic name matching for commands like "play weight loss" or "play financial"
      await DebugLogHelper.addDebugLog('VOICE NEWS: Attempting fuzzy topic name matching for: "$cmd"');
      onVoiceCommand?.call('play_topic_by_name', null, cmd);
    } else if (cmd.contains('listen') || cmd.contains('read') || cmd.contains('play')) {
      onVoiceCommand?.call('play', null, 'Playing audio');
    } else if (cmd.contains('pause') || cmd.contains('stop')) {
      onVoiceCommand?.call('pause', null, 'Pausing audio');
    } else {
      await DebugLogHelper.addDebugLog('VOICE NEWS: UNRECOGNIZED command: "$cmd"');
      onVoiceCommand?.call('play', null, 'Command not recognized, playing audio');
    }
  }

  void dispose() {
    _listeningTimer?.cancel();
    _buttonTimer?.cancel();
    _volumeSubscription?.cancel();
  }
}