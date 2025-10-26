import 'dart:io';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../screens/debug_log_viewer_screen.dart';

class HtmlAudioPlayerService {
  InAppWebViewController? _webViewController;
  bool _isPlaying = false;
  String? _currentAudioPath;

  Future<String> _createAudioHtml(String audioPath) async {
    return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            margin: 0; 
            padding: 15px; 
            font-family: Arial, sans-serif; 
            background: #f5f5f5;
        }
        audio { 
            width: 100%; 
            margin-bottom: 15px;
        }
        .controls { 
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }
        button { 
            flex: 1;
            min-width: 80px;
            padding: 12px 8px;
            border: none;
            border-radius: 6px;
            background: #3498db;
            color: white;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #2980b9;
        }
        button:active {
            background: #1f5f8b;
            transform: scale(0.98);
        }
        .position {
            text-align: center;
            font-size: 14px;
            color: #666;
            background: white;
            padding: 8px;
            border-radius: 4px;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <audio id="audioPlayer" controls preload="metadata">
        <source src="file://$audioPath" type="audio/mp3">
        <source src="file://$audioPath" type="audio/wav">
        <source src="file://$audioPath" type="audio/webm">
        <source src="file://$audioPath" type="audio/ogg">
        Your browser does not support the audio element.
    </audio>
    
    <div class="controls">
        <button id="backwardBtn" onclick="seekBackward()" title="Go back 10 seconds">⏪ -10s</button>
        <button id="restartBtn" onclick="restart()" title="Restart from beginning">⏮️ Restart</button>
        <button id="forwardBtn" onclick="seekForward()" title="Skip forward 10 seconds">⏩ +10s</button>
    </div>
    
    <div id="position" class="position">Position: 0s / 0s</div>
    
    <script>
        console.log('HTML Audio Player initialized');
        const audio = document.getElementById('audioPlayer');
        
        // Ensure audio is loaded before enabling controls
        audio.addEventListener('loadedmetadata', function() {
            console.log('Audio metadata loaded, duration:', audio.duration, 'path:', '$audioPath');
            updatePosition();
            enableControls();
            // Force additional update after short delay
            setTimeout(updatePosition, 100);
            setTimeout(updatePosition, 500);
        });
        
        audio.addEventListener('canplay', function() {
            console.log('Audio can play, path:', '$audioPath');
            enableControls();
        });
        
        audio.addEventListener('loadstart', function() {
            console.log('Audio load started for:', '$audioPath');
        });
        
        audio.addEventListener('loadeddata', function() {
            console.log('Audio data loaded for:', '$audioPath');
            updatePosition();
        });
        
        function enableControls() {
            document.getElementById('backwardBtn').disabled = false;
            document.getElementById('restartBtn').disabled = false;
            document.getElementById('forwardBtn').disabled = false;
        }
        
        function seekBackward() {
            console.log('Seek backward clicked, current time:', audio.currentTime);
            if (audio.duration && !isNaN(audio.duration)) {
                const newTime = Math.max(0, audio.currentTime - 10);
                audio.currentTime = newTime;
                console.log('Seeked to:', newTime);
                updatePosition();
            } else {
                console.log('Audio not ready for seeking');
            }
        }
        
        function seekForward() {
            console.log('Seek forward clicked, current time:', audio.currentTime);
            if (audio.duration && !isNaN(audio.duration)) {
                const newTime = Math.min(audio.duration, audio.currentTime + 10);
                audio.currentTime = newTime;
                console.log('Seeked to:', newTime);
                updatePosition();
            } else {
                console.log('Audio not ready for seeking');
            }
        }
        
        function restart() {
            console.log('Restart clicked');
            audio.currentTime = 0;
            console.log('Restarted to beginning');
            updatePosition();
        }
        
        function updatePosition() {
            const pos = Math.floor(audio.currentTime) || 0;
            const dur = Math.floor(audio.duration) || 0;
            const positionText = 'Position: ' + pos + 's / ' + dur + 's';
            document.getElementById('position').textContent = positionText;
        }
        
        // Update position every second
        audio.addEventListener('timeupdate', updatePosition);
        audio.addEventListener('loadedmetadata', updatePosition);
        audio.addEventListener('durationchange', updatePosition);
        
        // Notify Flutter about playback state
        audio.addEventListener('play', () => {
            console.log('Audio started playing');
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('onPlay');
            }
        });
        
        audio.addEventListener('pause', () => {
            console.log('Audio paused');
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('onPause');
            }
        });
        
        audio.addEventListener('ended', () => {
            console.log('Audio ended');
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('onEnded');
            }
        });
        
        // Error handling
        audio.addEventListener('error', function(e) {
            console.error('Audio error for path:', '$audioPath', 'Error:', e);
            console.error('Audio error details:', audio.error);
            document.getElementById('position').textContent = 'Error loading audio: ' + (audio.error ? audio.error.message : 'Unknown error');
        });
        
        // Force reload if needed
        window.reloadAudio = function() {
            console.log('Forcing audio reload for:', '$audioPath');
            audio.load();
        };
        
        // Enhanced setup with aggressive duration loading
        let retryCount = 0;
        function tryLoadAudio() {
            console.log('Attempting to load audio, retry:', retryCount, 'readyState:', audio.readyState, 'duration:', audio.duration);
            if (audio.readyState >= 1 && audio.duration && !isNaN(audio.duration)) {
                enableControls();
                updatePosition();
                console.log('Audio loaded successfully on retry:', retryCount, 'duration:', audio.duration);
            } else if (retryCount < 5) {
                retryCount++;
                audio.load();
                // Force duration check
                setTimeout(() => {
                    if (audio.duration && !isNaN(audio.duration)) {
                        updatePosition();
                        console.log('Duration found on retry:', retryCount, 'duration:', audio.duration);
                    }
                }, 200);
                setTimeout(tryLoadAudio, 800);
            } else {
                console.error('Failed to load audio after 5 retries');
                document.getElementById('position').textContent = 'Failed to load audio';
            }
        }
        
        // Multiple initialization attempts
        setTimeout(tryLoadAudio, 300);
        setTimeout(() => {
            if (audio.duration && !isNaN(audio.duration)) {
                updatePosition();
                console.log('Duration loaded on delayed check:', audio.duration);
            }
        }, 1000);
        setTimeout(() => {
            if (audio.duration && !isNaN(audio.duration)) {
                updatePosition();
                console.log('Duration loaded on final check:', audio.duration);
            }
        }, 2000);
    </script>
</body>
</html>
    ''';
  }

  Future<bool> loadAudio(String audioPath, InAppWebViewController controller) async {
    try {
      _webViewController = controller;
      _currentAudioPath = audioPath;
      
      final file = File(audioPath);
      if (!await file.exists()) {
        await DebugLogHelper.addDebugLog('HTML_AUDIO: File does not exist: $audioPath');
        return false;
      }
      
      // Add JavaScript handlers for Flutter communication
      controller.addJavaScriptHandler(
        handlerName: 'onPlay',
        callback: (args) {
          onPlay();
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onPause', 
        callback: (args) {
          onPause();
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onEnded',
        callback: (args) {
          onEnded();
        },
      );
      
      final html = await _createAudioHtml(audioPath);
      await controller.loadData(data: html, baseUrl: WebUri('file://'));
      
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Loaded audio player for $audioPath');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Error loading audio: $e');
      return false;
    }
  }

  Future<void> play() async {
    try {
      await _webViewController?.evaluateJavascript(source: '''
        const audio = document.getElementById("audioPlayer");
        if (audio) {
          audio.play().then(() => {
            console.log('Audio play started successfully');
          }).catch(e => {
            console.error('Audio play failed:', e);
          });
        }
      ''');
      _isPlaying = true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Play error: $e');
    }
  }

  Future<void> pause() async {
    try {
      await _webViewController?.evaluateJavascript(source: '''
        const audio = document.getElementById("audioPlayer");
        if (audio) {
          audio.pause();
          console.log('Audio paused');
        }
      ''');
      _isPlaying = false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Pause error: $e');
    }
  }

  Future<void> stop() async {
    try {
      await _webViewController?.evaluateJavascript(source: '''
        const audio = document.getElementById("audioPlayer");
        if (audio) {
          audio.pause();
          audio.currentTime = 0;
          console.log('Audio stopped and reset');
        }
      ''');
      _isPlaying = false;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Stop error: $e');
    }
  }
  
  Future<void> seekForward() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'seekForward();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Seek forward error: $e');
    }
  }
  
  Future<void> seekBackward() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'seekBackward();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Seek backward error: $e');
    }
  }
  
  Future<void> restart() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'restart();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Restart error: $e');
    }
  }

  Future<int> getCurrentPosition() async {
    try {
      final result = await _webViewController?.evaluateJavascript(
        source: '''
          const audio = document.getElementById("audioPlayer");
          Math.floor(audio ? audio.currentTime : 0);
        '''
      );
      return result ?? 0;
    } catch (e) {
      return 0;
    }
  }
  
  Future<int> getDuration() async {
    try {
      final result = await _webViewController?.evaluateJavascript(
        source: '''
          const audio = document.getElementById("audioPlayer");
          Math.floor(audio && audio.duration ? audio.duration : 0);
        '''
      );
      return result ?? 0;
    } catch (e) {
      return 0;
    }
  }

  bool get isPlaying => _isPlaying;
  String? get currentAudioPath => _currentAudioPath;
  
  void onPlay() {
    _isPlaying = true;
  }
  
  void onPause() {
    _isPlaying = false;
  }
  
  void onEnded() {
    _isPlaying = false;
  }
}