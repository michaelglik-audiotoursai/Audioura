import 'dart:io';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../screens/debug_log_viewer_screen.dart';

/// LOCAL-482 — how the stop editor grants WKWebView read access to a stop's
/// original audio.
///
/// The old code did `loadData(baseUrl: file://)` with a `<source
/// src="file://$absolutePath">`. On iOS `loadData` maps to
/// `loadHTMLString(_:baseURL:)`, which grants the page read access ONLY to the
/// baseURL's own directory. A bare `file://` root grants access to *nothing*,
/// so the `<source>` into `.../Documents/tours/<tour>/audio_N.mp3` was blocked
/// by the sandbox — the `<audio>` element errored, the retry loop burned five
/// attempts, and the field showed "Failed to load audio".
///
/// The Listen tab and news player never hit this because they load
/// `file://<tourDir>/index.html` BY URL — the baseURL is then the tour
/// directory and the granted scope covers the audio beside it
/// (news_player_screen.dart:75, tour_player_screen.dart:71).
///
/// This value object mirrors that working model for the editor: write a scratch
/// HTML page INTO the audio's own directory and load it by URL, with a RELATIVE
/// `<source src="audio_N.mp3">` that resolves inside the granted scope.
///
/// It is a pure function of the audio path so the access model is unit-testable
/// without a WebView or platform channel. A test pins every field; restoring
/// the `file://` baseURL or an absolute `src` breaks it (AC #6).
class EditorAudioAccessModel {
  /// Absolute path to the audio file being played.
  final String audioPath;

  /// Directory the audio lives in — becomes the WKWebView read-access scope.
  final String directory;

  /// Relative `<source src>` — MUST be relative (just the filename) so it
  /// resolves inside [directory]. An absolute `file://` src escapes the grant.
  final String relativeSrc;

  /// Absolute path of the scratch HTML file, written beside the audio.
  final String scratchHtmlPath;

  /// The `file://` URL the WebView loads. Its directory equals [directory], so
  /// WKWebView grants read access to the audio next to it.
  final String loadUrl;

  const EditorAudioAccessModel({
    required this.audioPath,
    required this.directory,
    required this.relativeSrc,
    required this.scratchHtmlPath,
    required this.loadUrl,
  });

  /// Dot-prefixed so it is a hidden scratch file that existing tour parsers
  /// ignore: they count `*.mp3` (tour_generator_screen.dart:563,
  /// tour_translation_helper.dart:166) and never enumerate this HTML. The dot
  /// prefix also keeps it out of casual directory listings and re-zips.
  static const String scratchFileName = '.audioura_editor_scratch.html';

  /// Build the access model from an absolute audio file path.
  ///
  /// Splits off the directory, keeps only the filename for the relative
  /// `<source src>`, and places the scratch HTML in the same directory so the
  /// dir-scoped baseURL covers the audio.
  factory EditorAudioAccessModel.forAudioPath(String audioPath) {
    final sep = audioPath.lastIndexOf('/');
    // A path with no separator has no directory scope we can grant; fall back
    // to '.' so the model is still well-formed and the caller can decide.
    final directory = sep >= 0 ? audioPath.substring(0, sep) : '.';
    final fileName = sep >= 0 ? audioPath.substring(sep + 1) : audioPath;
    final scratchHtmlPath = '$directory/$scratchFileName';
    return EditorAudioAccessModel(
      audioPath: audioPath,
      directory: directory,
      relativeSrc: fileName,
      scratchHtmlPath: scratchHtmlPath,
      loadUrl: 'file://$scratchHtmlPath',
    );
  }
}

class HtmlAudioPlayerService {
  InAppWebViewController? _webViewController;
  bool _isPlaying = false;
  String? _currentAudioPath;

  /// LOCAL-482: path of the scratch HTML we wrote beside the audio, so we can
  /// delete it on the next load and when the editor closes.
  String? _scratchHtmlPath;

  Future<String> _createAudioHtml(String relativeSrc) async {
    final audioPath = relativeSrc;
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
        <source src="$audioPath" type="audio/mp3">
        <source src="$audioPath" type="audio/wav">
        <source src="$audioPath" type="audio/webm">
        <source src="$audioPath" type="audio/ogg">
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
      
      // LOCAL-482: Match the players' access model instead of loadData(file://).
      // Write a scratch HTML page INTO the audio's own directory and load it BY
      // URL, with a RELATIVE <source src>. WKWebView then grants the page read
      // access to that directory, so the audio beside it is readable — the same
      // grant the Listen tab / news player get from file://<dir>/index.html.
      final access = EditorAudioAccessModel.forAudioPath(audioPath);

      // Clean up any scratch file from a previous load before writing a fresh
      // one (also guards against a leftover from a crash).
      await _deleteScratchHtml();

      final html = await _createAudioHtml(access.relativeSrc);
      await File(access.scratchHtmlPath).writeAsString(html, flush: true);
      _scratchHtmlPath = access.scratchHtmlPath;

      await DebugLogHelper.addDebugLog(
        'HTML_AUDIO: Wrote scratch player ${access.scratchHtmlPath} '
        '(src="${access.relativeSrc}")');

      await controller.loadUrl(
        urlRequest: URLRequest(url: WebUri(access.loadUrl)));

      await DebugLogHelper.addDebugLog(
        'HTML_AUDIO: Loaded audio player by URL ${access.loadUrl} for $audioPath');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Error loading audio: $e');
      return false;
    }
  }

  /// LOCAL-482: delete the scratch HTML we wrote beside the audio. Safe to call
  /// repeatedly; no-op if nothing was written. Call when the editor closes so
  /// no scratch file is left in the tour directory (AC #5).
  Future<void> _deleteScratchHtml() async {
    final path = _scratchHtmlPath;
    if (path == null) return;
    try {
      final f = File(path);
      if (await f.exists()) {
        await f.delete();
        await DebugLogHelper.addDebugLog('HTML_AUDIO: Deleted scratch player $path');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_AUDIO: Failed to delete scratch player $path: $e');
    } finally {
      _scratchHtmlPath = null;
    }
  }

  /// Public cleanup hook for the editor's dispose(). Deletes the scratch HTML
  /// file so it never ends up in a re-zip, download, or sync (AC #5).
  Future<void> dispose() async {
    await _deleteScratchHtml();
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