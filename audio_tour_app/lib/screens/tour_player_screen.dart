import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter/foundation.dart';
import 'dart:io';
import 'dart:async';
import 'voice_methods.dart';
import 'debug_log_viewer_screen.dart';
import '../services/web_file_service.dart';

class TourPlayerScreen extends StatefulWidget {
  final String tourPath;
  final String tourTitle;

  const TourPlayerScreen({
    super.key,
    required this.tourPath,
    required this.tourTitle,
  });

  @override
  State<TourPlayerScreen> createState() => _TourPlayerScreenState();
}

class _TourPlayerScreenState extends State<TourPlayerScreen> with VoiceMethods {
  InAppWebViewController? _controller;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
    initializeVoiceControl();
  }

  @override
  void dispose() {
    disposeVoice();
    super.dispose();
  }

  void _initializeWebView() {
    // InAppWebView will be initialized in the build method
  }
  
  Future<String> _getIndexUrl() async {
    if (kIsWeb) {
      // Web platform: use blob URL
      final blobUrl = await WebFileService.getTourFilePath(widget.tourPath, 'index.html');
      await DebugLogHelper.addDebugLog('TOUR_PLAYER: Using web blob URL (${blobUrl.length} chars)');
      return blobUrl;
    } else {
      // Mobile platform: use file URL
      final fileUrl = 'file://${widget.tourPath}/index.html';
      await DebugLogHelper.addDebugLog('TOUR_PLAYER: Using mobile file URL: $fileUrl');
      return fileUrl;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.tourTitle),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: Icon(Icons.help_outline),
            onPressed: _showTourHelpDialog,
            tooltip: 'Voice Commands Help',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => _controller?.reload(),
          ),
        ],
      ),
      body: FutureBuilder<String>(
        future: _getIndexUrl(),
        builder: (context, snapshot) {
          if (snapshot.hasData) {
            return InAppWebView(
              initialUrlRequest: URLRequest(url: WebUri(snapshot.data!)),
              initialSettings: InAppWebViewSettings(
                javaScriptEnabled: true,
                mediaPlaybackRequiresUserGesture: false, // CRITICAL: Enable audio autoplay
                useShouldOverrideUrlLoading: false,
                useOnLoadResource: false,
                useHybridComposition: true,
                allowContentAccess: true,
                allowFileAccess: true,
                allowsInlineMediaPlayback: true,
                allowsAirPlayForMediaPlayback: true,
              ),
              onWebViewCreated: (InAppWebViewController controller) async {
                _controller = controller;
                webController = controller;
                await DebugLogHelper.addDebugLog('VOICE: InAppWebView created, controller set');
              },
              onLoadStop: (InAppWebViewController controller, WebUri? url) async {
                await DebugLogHelper.addDebugLog('VOICE: WebView loaded: $url');
                await DebugLogHelper.addDebugLog('VOICE: Getting tour info');
                getTourInfo();
                
                // Auto-start tour playback
                await Future.delayed(Duration(milliseconds: 2000)); // Wait longer for page to fully load
                try {
                  await controller.evaluateJavascript(source: """
                    console.log('Attempting auto-start...');
                    if (typeof startTour === 'function') {
                      console.log('Found startTour function, calling it');
                      startTour();
                    } else {
                      console.log('No startTour function, trying audio1');
                      var audio1 = document.getElementById('audio1');
                      if (audio1) {
                        console.log('Found audio1 element, playing');
                        audio1.play().then(() => {
                          console.log('Audio1 started successfully');
                        }).catch(e => {
                          console.log('Audio1 play failed:', e);
                        });
                      } else {
                        console.log('No audio1 element found');
                        var firstAudio = document.querySelector('audio');
                        if (firstAudio) {
                          console.log('Found first audio element, playing');
                          firstAudio.play();
                        }
                      }
                    }
                  """);
                  await DebugLogHelper.addDebugLog('TOUR_PLAYER: Auto-start command executed');
                } catch (e) {
                  await DebugLogHelper.addDebugLog('TOUR_PLAYER: Auto-start failed: $e');
                }
              },
              onReceivedError: (InAppWebViewController controller, WebResourceRequest request, WebResourceError error) {
                DebugLogHelper.addDebugLog('VOICE: WebView load error: ${error.description} for URL: ${request.url}');
              },
            );
          } else {
            return Center(child: CircularProgressIndicator());
          }
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          await DebugLogHelper.addDebugLog('VOICE: Mic button pressed - starting voice recognition');
          voiceService.startVoiceListening();
        },
        backgroundColor: const Color(0xFF3498db),
        child: const Icon(Icons.mic, color: Colors.white),
      ),
    );
  }
  void _showTourHelpDialog() {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text('🎤 Tour Voice Commands'),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Audio Control:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Play" to start or resume audio'),
                Text('• Say "Pause" to stop audio'),
                Text('• Say "Repeat" to restart current stop'),
                SizedBox(height: 12),
                Text(
                  'Navigation:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Next stop" to move forward'),
                Text('• Say "Previous stop" to move back'),
                Text('• Say "Go to stop [number]" to jump to specific stop'),
                SizedBox(height: 12),
                Text(
                  'Seeking:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Forward 10 seconds" to skip ahead'),
                Text('• Say "Backward 5 seconds" to skip back'),
                SizedBox(height: 12),
                Text(
                  'Tour Switching:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                SizedBox(height: 4),
                Text('• Say "Next tour" to switch tours'),
                Text('• Say "Previous tour" to go back'),
                SizedBox(height: 12),
                Text(
                  'Activation:',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.blue),
                ),
                SizedBox(height: 4),
                Text('• Press microphone button or triple-press volume buttons'),
                Text('• Speak clearly after the beep'),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text('Close'),
            ),
          ],
        );
      },
    );
  }

}