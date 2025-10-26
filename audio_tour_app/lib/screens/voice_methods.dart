import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import '../services/voice_control_service.dart';
import 'debug_log_viewer_screen.dart';
import 'tour_player_screen.dart';

mixin VoiceMethods<T extends StatefulWidget> on State<T> {
  final VoiceControlService voiceService = VoiceControlService();
  int currentStop = 0;
  int totalStops = 10;
  InAppWebViewController? webController;

  Future<void> initializeVoiceControl() async {
    await voiceService.initialize();
    voiceService.onVoiceCommand = handleVoiceCommand;
  }

  Future<void> getTourInfo() async {
    try {
      if (webController != null) {
        final result = await webController!.evaluateJavascript(
          source: 'document.querySelectorAll(".stop").length || 10'
        );
        totalStops = int.tryParse(result.toString()) ?? 10;
        
        final prefs = await SharedPreferences.getInstance();
        await prefs.setInt('total_stops', totalStops);
        
        // Check if we should auto-play (from Next/Previous Tour)
        final shouldAutoPlay = prefs.getBool('should_auto_play') ?? false;
        if (shouldAutoPlay) {
          await prefs.setBool('should_auto_play', false); // Clear flag
          await DebugLogHelper.addDebugLog('VOICE: Auto-playing first stop after tour navigation');
          
          // Wait for WebView to fully initialize
          await Future.delayed(Duration(milliseconds: 1500));
          
          try {
            await webController!.evaluateJavascript(source: 'currentStopIndex = 0;');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
            await DebugLogHelper.addDebugLog('VOICE: Successfully auto-played first stop');
          } catch (e) {
            await DebugLogHelper.addDebugLog('VOICE: Auto-play error: $e');
          }
        }
      }
    } catch (e) {
      print('Error getting tour info: $e');
    }
  }

  void handleVoiceCommand(String action, int? stopNumber, String message) async {
    await DebugLogHelper.addDebugLog('VOICE: Executing action: $action');
    
    // Test JavaScript execution and audio elements
    try {
      if (webController != null) {
        final testResult = await webController!.evaluateJavascript(source: '"JS_TEST_OK"');
        await DebugLogHelper.addDebugLog('VOICE: JavaScript test result: $testResult');
        
        final audioTest = await webController!.evaluateJavascript(source: 'document.querySelectorAll("audio").length');
        await DebugLogHelper.addDebugLog('VOICE: Audio elements found: $audioTest');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: JavaScript test failed: $e');
    }
    
    switch (action) {
      case 'next_and_play':
        await DebugLogHelper.addDebugLog('VOICE: Next stop and play');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: 'window.pauseAudio()');
            await webController!.evaluateJavascript(source: 'window.nextStop()');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Next and play error: $e');
        }
        break;
      case 'previous_and_play':
        await DebugLogHelper.addDebugLog('VOICE: Previous stop and play');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: 'window.pauseAudio()');
            await webController!.evaluateJavascript(source: 'window.previousStop()');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Previous and play error: $e');
        }
        break;
      case 'repeat_and_play':
        await DebugLogHelper.addDebugLog('VOICE: Repeat and play');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: 'window.pauseAudio()');
            await webController!.evaluateJavascript(source: 'window.repeatStop()');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Repeat and play error: $e');
        }
        break;
      case 'forward_and_play':
        await DebugLogHelper.addDebugLog('VOICE: Forward and play');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: 'window.seekForward($stopNumber)');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Forward and play error: $e');
        }
        break;
      case 'backward_and_play':
        await DebugLogHelper.addDebugLog('VOICE: Backward and play');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: 'window.seekBackward($stopNumber)');
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Backward and play error: $e');
        }
        break;
      case 'pause':
        await DebugLogHelper.addDebugLog('VOICE: Pausing audio');
        try {
          if (webController != null) {
            final result = await webController!.evaluateJavascript(source: 'window.pauseAudio()');
            await DebugLogHelper.addDebugLog('VOICE: Pause result: $result');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Pause error: $e');
        }
        break;
      case 'play':
        await DebugLogHelper.addDebugLog('VOICE: Playing audio');
        try {
          if (webController != null) {
            final result = await webController!.evaluateJavascript(source: 'window.playAudio()');
            await DebugLogHelper.addDebugLog('VOICE: Play result: $result');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Play error: $e');
        }
        break;
      case 'next_tour':
        await DebugLogHelper.addDebugLog('VOICE: Going to next tour');
        try {
          await _goToNextTour();
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Next tour error: $e');
        }
        break;
      case 'previous_tour':
        await DebugLogHelper.addDebugLog('VOICE: Going to previous tour');
        try {
          await _goToPreviousTour();
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Previous tour error: $e');
        }
        break;
      case 'go_to_stop':
        await DebugLogHelper.addDebugLog('VOICE: Going to stop $stopNumber');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: '''
              if (typeof window.goToStop === 'function') {
                window.goToStop($stopNumber);
                console.log('Voice: Used goToStop function for stop $stopNumber');
              } else {
                // Fallback to old method
                var audios = document.querySelectorAll('audio');
                if (audios[$stopNumber - 1]) {
                  audios[$stopNumber - 1].play();
                  console.log('Voice: Used fallback goToStop for stop $stopNumber');
                }
              }
            ''');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Go to stop error: $e');
        }
        break;
      case 'pause_for_listening':
        await DebugLogHelper.addDebugLog('VOICE: Pausing audio for voice recognition');
        try {
          if (webController != null) {
            await webController!.evaluateJavascript(source: '''
              if (typeof window.pauseAllAudio === 'function') {
                window.pauseAllAudio();
              } else {
                document.querySelectorAll('audio').forEach(a => a.pause());
              }
            ''');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Pause for listening error: $e');
        }
        break;
      case 'initialize':
        await DebugLogHelper.addDebugLog('VOICE: Initializing audio context');
        try {
          if (webController != null) {
            final result = await webController!.evaluateJavascript(source: 'window.initializeAudio()');
            await DebugLogHelper.addDebugLog('VOICE: Initialize result: $result');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('VOICE: Initialize error: $e');
        }
        break;

    }
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: Duration(seconds: 2)),
    );
  }

  Future<void> goToStop(int stopNumber) async {
    currentStop = stopNumber;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('current_stop', currentStop);
    
    try {
      await DebugLogHelper.addDebugLog('VOICE: Running JavaScript to go to stop $stopNumber');
      
      // Check what elements exist
      if (webController != null) {
        final stopElement = await webController!.evaluateJavascript(source: 'document.getElementById("stop-$stopNumber") ? "found" : "not found"');
        await DebugLogHelper.addDebugLog('VOICE: Stop element stop-$stopNumber: $stopElement');
      }
      

      
      // Try multiple navigation approaches and auto-play
      final approaches = [
        'var found = false; document.querySelectorAll("*").forEach(el => { if(!found && el.textContent && el.textContent.includes("Stop $stopNumber")) { el.scrollIntoView({behavior: "smooth"}); var playBtn = el.querySelector("button, [onclick]") || el.nextElementSibling?.querySelector("button, [onclick]") || el.parentElement?.querySelector("button, [onclick]"); if(playBtn) { setTimeout(() => playBtn.click(), 500); found = true; } } });',
        'var elements = document.querySelectorAll("*"); for(var i=0; i<elements.length; i++) { var el = elements[i]; if(el.textContent && el.textContent.includes("Audio $stopNumber")) { el.scrollIntoView({behavior: "smooth"}); var playBtn = el.querySelector("button, [onclick]") || el.nextElementSibling?.querySelector("button, [onclick]") || el.parentElement?.querySelector("button, [onclick]"); if(playBtn) { setTimeout(() => playBtn.click(), 500); } break; } }',
        'window.scrollTo(0, $stopNumber * 200); setTimeout(() => { var buttons = document.querySelectorAll("button, [onclick]"); if(buttons[$stopNumber-1]) buttons[$stopNumber-1].click(); }, 500);',
      ];
      
      if (webController != null) {
        for (String approach in approaches) {
          try {
            await webController!.evaluateJavascript(source: approach);
            await DebugLogHelper.addDebugLog('VOICE: Tried navigation with auto-play: $approach');
          } catch (e) {
            await DebugLogHelper.addDebugLog('VOICE: Navigation approach failed: $e');
          }
        }
      }
      
      await DebugLogHelper.addDebugLog('VOICE: JavaScript executed successfully');
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: JavaScript error: $e');
    }
  }

  Future<void> _goToNextTour() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Get current tour info
      final currentTourId = prefs.getString('current_tour_id') ?? '';
      final toursList = prefs.getStringList('available_tours') ?? [];
      
      await DebugLogHelper.addDebugLog('VOICE: Current tour: $currentTourId');
      await DebugLogHelper.addDebugLog('VOICE: Available tours: ${toursList.length}');
      
      if (toursList.isEmpty) {
        await DebugLogHelper.addDebugLog('VOICE: No tours available, going back to My Tours');
        Navigator.of(context).pop();
        return;
      }
      
      // Find current tour index
      int currentIndex = -1;
      for (int i = 0; i < toursList.length; i++) {
        if (toursList[i].contains(currentTourId)) {
          currentIndex = i;
          break;
        }
      }
      
      await DebugLogHelper.addDebugLog('VOICE: Current tour index: $currentIndex');
      
      // Get next tour (wraps to first if at last)
      int nextIndex = (currentIndex + 1) % toursList.length;
      if (toursList.length <= 1) {
        await DebugLogHelper.addDebugLog('VOICE: Only one tour available');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Only one tour available'), duration: Duration(seconds: 2)),
        );
        return;
      }
      
      final nextTourInfo = toursList[nextIndex];
      final nextTourParts = nextTourInfo.split('|');
      final nextTourTitle = nextTourParts[0];
      final nextTourPath = nextTourParts.length > 1 ? nextTourParts[1] : '';
      
      await DebugLogHelper.addDebugLog('VOICE: Next tour: $nextTourTitle at $nextTourPath');
      
      // Save next tour as current
      await prefs.setString('current_tour_id', nextTourTitle);
      await prefs.setString('current_tour_path', nextTourPath);
      await prefs.setInt('current_stop', 0); // Start at first stop
      
      // Navigate to next tour directly
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => TourPlayerScreen(
            tourPath: nextTourPath,
            tourTitle: nextTourTitle,
          ),
        ),
      );
      
      // Mark that we should auto-play when the new tour loads
      await prefs.setBool('should_auto_play', true);
      await DebugLogHelper.addDebugLog('VOICE: Marked for auto-play on new tour load');
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: Next tour error: $e');
      Navigator.of(context).pop(); // Fallback to My Tours
    }
  }

  Future<void> _goToPreviousTour() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Get current tour info
      final currentTourId = prefs.getString('current_tour_id') ?? '';
      final toursList = prefs.getStringList('available_tours') ?? [];
      
      await DebugLogHelper.addDebugLog('VOICE: Current tour: $currentTourId');
      await DebugLogHelper.addDebugLog('VOICE: Available tours: ${toursList.length}');
      
      if (toursList.isEmpty) {
        await DebugLogHelper.addDebugLog('VOICE: No tours available, going back to My Tours');
        Navigator.of(context).pop();
        return;
      }
      
      if (toursList.length <= 1) {
        await DebugLogHelper.addDebugLog('VOICE: Only one tour available');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Only one tour available'), duration: Duration(seconds: 2)),
        );
        return;
      }
      
      // Find current tour index
      int currentIndex = -1;
      for (int i = 0; i < toursList.length; i++) {
        if (toursList[i].contains(currentTourId)) {
          currentIndex = i;
          break;
        }
      }
      
      await DebugLogHelper.addDebugLog('VOICE: Current tour index: $currentIndex');
      
      // Get previous tour (wraps to last if at first)
      int previousIndex = currentIndex <= 0 ? toursList.length - 1 : currentIndex - 1;
      
      final previousTourInfo = toursList[previousIndex];
      final previousTourParts = previousTourInfo.split('|');
      final previousTourTitle = previousTourParts[0];
      final previousTourPath = previousTourParts.length > 1 ? previousTourParts[1] : '';
      
      await DebugLogHelper.addDebugLog('VOICE: Previous tour: $previousTourTitle at $previousTourPath');
      
      // Save previous tour as current
      await prefs.setString('current_tour_id', previousTourTitle);
      await prefs.setString('current_tour_path', previousTourPath);
      await prefs.setInt('current_stop', 0); // Start at first stop
      
      // Navigate to previous tour directly
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (context) => TourPlayerScreen(
            tourPath: previousTourPath,
            tourTitle: previousTourTitle,
          ),
        ),
      );
      
      // Mark that we should auto-play when the new tour loads
      await prefs.setBool('should_auto_play', true);
      await DebugLogHelper.addDebugLog('VOICE: Marked for auto-play on new tour load');
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('VOICE: Previous tour error: $e');
      Navigator.of(context).pop(); // Fallback to My Tours
    }
  }

  void disposeVoice() {
    voiceService.dispose();
  }
}