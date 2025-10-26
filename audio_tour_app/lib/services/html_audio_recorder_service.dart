import 'dart:io';
import 'dart:convert';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../screens/debug_log_viewer_screen.dart';

class HtmlAudioRecorderService {
  InAppWebViewController? _webViewController;
  bool _isRecording = false;
  bool _isPaused = false;
  String? _recordedAudioBase64;
  int _recordingDuration = 0;

  Future<String> _createRecorderHtml() async {
    return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            margin: 0; 
            padding: 20px; 
            font-family: Arial, sans-serif; 
            background: #f5f5f5;
        }
        .recorder-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }
        .controls {
            display: flex;
            gap: 10px;
            margin: 20px 0;
            justify-content: center;
            flex-wrap: wrap;
        }
        button {
            padding: 12px 20px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
        }
        .record-btn {
            background: #e74c3c;
            color: white;
        }
        .record-btn:hover {
            background: #c0392b;
        }
        .pause-btn {
            background: #f39c12;
            color: white;
        }
        .pause-btn:hover {
            background: #d68910;
        }
        .stop-btn {
            background: #95a5a6;
            color: white;
        }
        .stop-btn:hover {
            background: #7f8c8d;
        }
        .status {
            margin: 15px 0;
            font-size: 18px;
            font-weight: bold;
        }
        .recording {
            color: #e74c3c;
        }
        .paused {
            color: #f39c12;
        }
        .stopped {
            color: #27ae60;
        }
        .error {
            color: #e74c3c;
            background: #fdf2f2;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <div class="recorder-container">
        <h3>HTML5 Audio Recorder</h3>
        
        <div class="controls">
            <button id="recordBtn" class="record-btn" onclick="toggleRecording()">🎤 Start Recording</button>
            <button id="pauseBtn" class="pause-btn" onclick="pauseRecording()" disabled>⏸️ Pause</button>
            <button id="stopBtn" class="stop-btn" onclick="stopRecording()" disabled>⏹️ Stop</button>
        </div>
        
        <div id="status" class="status stopped">Ready to record</div>
        <div id="duration">Duration: 0s</div>
        <div id="error" class="error" style="display: none;"></div>
    </div>
    
    <script>
        let mediaRecorder = null;
        let audioChunks = [];
        let stream = null;
        let startTime = null;
        let pausedTime = 0;
        let durationInterval = null;
        
        const recordBtn = document.getElementById('recordBtn');
        const pauseBtn = document.getElementById('pauseBtn');
        const stopBtn = document.getElementById('stopBtn');
        const status = document.getElementById('status');
        const duration = document.getElementById('duration');
        const error = document.getElementById('error');
        
        function showError(message) {
            console.error('Recorder error:', message);
            error.textContent = message;
            error.style.display = 'block';
            if (window.flutter_inappwebview) {
                window.flutter_inappwebview.callHandler('onError', message);
            }
        }
        
        function hideError() {
            error.style.display = 'none';
        }
        
        function updateDuration() {
            if (startTime && mediaRecorder && mediaRecorder.state === 'recording') {
                const elapsed = Math.floor((Date.now() - startTime - pausedTime) / 1000);
                duration.textContent = 'Duration: ' + elapsed + 's';
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('onDurationUpdate', elapsed);
                }
            }
        }
        
        async function toggleRecording() {
            if (!mediaRecorder || mediaRecorder.state === 'inactive') {
                await startRecording();
            } else if (mediaRecorder.state === 'recording') {
                pauseRecording();
            } else if (mediaRecorder.state === 'paused') {
                resumeRecording();
            }
        }
        
        async function startRecording() {
            try {
                hideError();
                console.log('Requesting microphone access...');
                
                stream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: false,  // Disable AGC to prevent volume spikes
                        sampleRate: 44100,
                        channelCount: 1,  // Mono recording
                        volume: 0.8  // Slightly reduce input volume
                    } 
                });
                
                console.log('Microphone access granted');
                
                // Reset recording data
                audioChunks = [];
                startTime = Date.now();
                pausedTime = 0;
                
                // Create MediaRecorder with optimized settings for quality
                const options = {
                    audioBitsPerSecond: 128000  // 128 kbps for good quality
                };
                
                // Try WebM with Opus (best quality/size), then WAV, then MP4
                if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
                    options.mimeType = 'audio/webm;codecs=opus';
                } else if (MediaRecorder.isTypeSupported('audio/webm')) {
                    options.mimeType = 'audio/webm';
                } else if (MediaRecorder.isTypeSupported('audio/wav')) {
                    options.mimeType = 'audio/wav';
                } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
                    options.mimeType = 'audio/mp4';
                }
                
                console.log('Selected mimeType:', options.mimeType || 'default');
                
                mediaRecorder = new MediaRecorder(stream, options);
                console.log('MediaRecorder created with mimeType:', options.mimeType || 'default');
                
                mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                        console.log('Audio chunk received:', event.data.size, 'bytes');
                    }
                };
                
                mediaRecorder.onstop = async () => {
                    console.log('Recording stopped, processing audio...');
                    
                    if (audioChunks.length === 0) {
                        showError('No audio data recorded');
                        return;
                    }
                    
                    const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                    console.log('Audio blob created:', audioBlob.size, 'bytes');
                    
                    // Convert to base64
                    const reader = new FileReader();
                    reader.onload = () => {
                        const base64 = reader.result.split(',')[1];
                        console.log('Audio converted to base64:', base64.length, 'characters');
                        
                        // Update UI with final duration
                        const finalDuration = Math.floor((Date.now() - startTime - pausedTime) / 1000);
                        status.textContent = 'Recording complete (' + finalDuration + 's)';
                        status.className = 'status stopped';
                        duration.textContent = 'Duration: ' + finalDuration + 's';
                        
                        if (window.flutter_inappwebview) {
                            window.flutter_inappwebview.callHandler('onRecordingComplete', {
                                audioBase64: base64,
                                mimeType: mediaRecorder.mimeType || 'audio/webm',
                                duration: Math.floor((Date.now() - startTime - pausedTime) / 1000),
                                size: audioBlob.size
                            });
                        }
                    };
                    reader.readAsDataURL(audioBlob);
                    
                    // Clean up
                    if (stream) {
                        stream.getTracks().forEach(track => track.stop());
                        stream = null;
                    }
                };
                
                mediaRecorder.onerror = (event) => {
                    console.error('MediaRecorder error:', event.error);
                    showError('Recording error: ' + event.error.message);
                };
                
                // Add a small delay before starting to prevent initial noise
                setTimeout(() => {
                    mediaRecorder.start(1000); // Collect data every second
                }, 100);
                console.log('Recording started');
                
                // Update UI
                recordBtn.textContent = '⏸️ Pause';
                pauseBtn.disabled = false;
                stopBtn.disabled = false;
                status.textContent = 'Recording...';
                status.className = 'status recording';
                
                // Start duration timer
                durationInterval = setInterval(updateDuration, 1000);
                
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('onRecordingStarted');
                }
                
            } catch (err) {
                console.error('Failed to start recording:', err);
                showError('Failed to access microphone: ' + err.message);
                
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('onRecordingFailed', err.message);
                }
            }
        }
        
        function pauseRecording() {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.pause();
                pausedTime += Date.now() - startTime;
                
                recordBtn.textContent = '▶️ Resume';
                status.textContent = 'Paused';
                status.className = 'status paused';
                
                clearInterval(durationInterval);
                
                console.log('Recording paused');
                
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('onRecordingPaused');
                }
            }
        }
        
        function resumeRecording() {
            if (mediaRecorder && mediaRecorder.state === 'paused') {
                mediaRecorder.resume();
                // Don't reset startTime - continue from where we paused
                
                recordBtn.textContent = '⏸️ Pause';
                status.textContent = 'Recording...';
                status.className = 'status recording';
                
                durationInterval = setInterval(updateDuration, 1000);
                
                console.log('Recording resumed');
                
                if (window.flutter_inappwebview) {
                    window.flutter_inappwebview.callHandler('onRecordingResumed');
                }
            }
        }
        
        function stopRecording() {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
                
                recordBtn.textContent = '🎤 Re-record';
                pauseBtn.disabled = true;
                stopBtn.disabled = true;
                status.textContent = 'Processing...';
                status.className = 'status stopped';
                
                clearInterval(durationInterval);
                
                console.log('Recording stop requested');
            }
        }
        
        // Initialize
        console.log('HTML5 Audio Recorder initialized');
        console.log('MediaRecorder supported:', typeof MediaRecorder !== 'undefined');
        console.log('getUserMedia supported:', navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
        
    </script>
</body>
</html>
    ''';
  }

  Future<bool> initialize(InAppWebViewController controller) async {
    try {
      _webViewController = controller;
      
      // Add JavaScript handlers for Flutter communication
      controller.addJavaScriptHandler(
        handlerName: 'onRecordingStarted',
        callback: (args) {
          _isRecording = true;
          _isPaused = false;
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onRecordingPaused',
        callback: (args) {
          _isPaused = true;
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onRecordingResumed',
        callback: (args) {
          _isPaused = false;
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onRecordingComplete',
        callback: (args) {
          final data = args[0] as Map<String, dynamic>;
          _recordedAudioBase64 = data['audioBase64'];
          _recordingDuration = data['duration'] ?? 0;
          _isRecording = false;
          _isPaused = false;
          
          DebugLogHelper.addDebugLog('HTML_RECORDER: Recording complete - ${data['size']} bytes, ${_recordingDuration}s');
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onRecordingFailed',
        callback: (args) {
          final error = args[0] as String;
          _isRecording = false;
          _isPaused = false;
          DebugLogHelper.addDebugLog('HTML_RECORDER: Recording failed - $error');
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onDurationUpdate',
        callback: (args) {
          _recordingDuration = args[0] as int;
        },
      );
      
      controller.addJavaScriptHandler(
        handlerName: 'onError',
        callback: (args) {
          final error = args[0] as String;
          DebugLogHelper.addDebugLog('HTML_RECORDER: Error - $error');
        },
      );
      
      final html = await _createRecorderHtml();
      await controller.loadData(data: html, baseUrl: WebUri('file://'));
      
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Initialized successfully');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Initialization error - $e');
      return false;
    }
  }

  Future<bool> startRecording() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'startRecording();');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Start recording error - $e');
      return false;
    }
  }

  Future<void> pauseRecording() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'pauseRecording();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Pause recording error - $e');
    }
  }

  Future<void> resumeRecording() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'resumeRecording();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Resume recording error - $e');
    }
  }

  Future<void> stopRecording() async {
    try {
      await _webViewController?.evaluateJavascript(source: 'stopRecording();');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Stop recording error - $e');
    }
  }

  Future<String?> saveRecordingToFile() async {
    if (_recordedAudioBase64 == null) return null;
    
    try {
      final bytes = base64Decode(_recordedAudioBase64!);
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final fileName = 'html5_recording_$timestamp.webm';
      final filePath = '/data/data/com.audiotours.dev/cache/$fileName';
      
      final file = File(filePath);
      await file.writeAsBytes(bytes);
      
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Saved recording to $filePath (${bytes.length} bytes)');
      return filePath;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HTML_RECORDER: Save file error - $e');
      return null;
    }
  }

  bool get isRecording => _isRecording;
  bool get isPaused => _isPaused;
  int get recordingDuration => _recordingDuration;
  String? get recordedAudioBase64 => _recordedAudioBase64;
  
  void dispose() {
    try {
      // Stop any active recording
      if (_webViewController != null && _isRecording) {
        _webViewController!.evaluateJavascript(source: """
          if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
          }
          if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
          }
          mediaRecorder = null;
          audioChunks = [];
        """);
      }
    } catch (e) {
      // Ignore errors during cleanup
    }
    
    _webViewController = null;
    _recordedAudioBase64 = null;
    _isRecording = false;
    _isPaused = false;
    _recordingDuration = 0;
  }
}