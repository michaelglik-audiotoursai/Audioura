import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:io';
import 'dart:async';
import 'voice_methods.dart';
import 'debug_log_viewer_screen.dart';
import 'tour_map_screen.dart';
import '../widgets/swipe_feedback_widget.dart';

class TourPlayerScreen extends StatefulWidget {
  final String tourPath;
  final String tourTitle;
  final String? tourId;
  final String? jobId;

  const TourPlayerScreen({
    super.key,
    required this.tourPath,
    required this.tourTitle,
    this.tourId,
    this.jobId,
  });

  @override
  State<TourPlayerScreen> createState() => _TourPlayerScreenState();
}

class _TourPlayerScreenState extends State<TourPlayerScreen> with VoiceMethods {
  InAppWebViewController? _controller;
  int _currentStopIndex = 0;

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
    // Mobile platform only: use file URL.
    // A#56: heal stale container path. iOS reassigns the app container UUID on
    // reinstall, so the stored tour path can point at an old container that is
    // now outside the sandbox (white screen). Re-anchor it to the current
    // Documents directory before building the file URL.
    String tourPath = widget.tourPath;
    const docsMarker = '/Documents/';
    final mi = tourPath.indexOf(docsMarker);
    if (mi != -1) {
      final docsDir = await getApplicationDocumentsDirectory();
      final healedPath =
          '${docsDir.path}/${tourPath.substring(mi + docsMarker.length)}';
      if (healedPath != tourPath) {
        await DebugLogHelper.addDebugLog('TOUR_PLAYER: Healed stale container path');
        tourPath = healedPath;
      }
    }
    final fileUrl = 'file://$tourPath/index.html';
    await DebugLogHelper.addDebugLog('TOUR_PLAYER: Using mobile file URL: $fileUrl');
    return fileUrl;
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
            return Column(
              children: [
                Expanded(
                  child: InAppWebView(
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
                      controller.addJavaScriptHandler(
                        handlerName: 'openMap',
                        callback: (args) async {
                          final stopArg = args.isNotEmpty && args[0] is Map ? args[0]['stop'] : null;
                          final stopIndex = stopArg is int ? stopArg : int.tryParse('$stopArg');
                          await DebugLogHelper.addDebugLog('MAP: openMap handler fired for stop $stopIndex');
                          if (!mounted) return;
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => TourMapScreen(
                                tourPath: widget.tourPath,
                                tourTitle: widget.tourTitle,
                                focusStopIndex: stopIndex,
                              ),
                            ),
                          );
                        },
                      );
                      // Track current stop index for swipe feedback
                      controller.addJavaScriptHandler(
                        handlerName: 'onStopChanged',
                        callback: (args) {
                          final idx = args.isNotEmpty ? (args[0] is int ? args[0] : int.tryParse('${args[0]}') ?? 0) : 0;
                          if (mounted) {
                            setState(() => _currentStopIndex = idx);
                          }
                        },
                      );
                    },
                    onLoadStop: (InAppWebViewController controller, WebUri? url) async {
                      await DebugLogHelper.addDebugLog('VOICE: WebView loaded: $url');
                      await DebugLogHelper.addDebugLog('VOICE: Getting tour info');
                      getTourInfo();

                      // Inject stop-change listener so we track which stop is playing
                      try {
                        await controller.evaluateJavascript(source: """
                          (function() {
                            // Hook into stop navigation to report current stop index
                            var origNextStop = window.nextStop;
                            var origPreviousStop = window.previousStop;
                            var origGoToStop = window.goToStop;
                            var currentIdx = 0;
                            function reportStop(idx) {
                              currentIdx = idx;
                              if (window.flutter_inappwebview) {
                                window.flutter_inappwebview.callHandler('onStopChanged', idx);
                              }
                            }
                            if (typeof origNextStop === 'function') {
                              window.nextStop = function() {
                                origNextStop();
                                currentIdx++;
                                reportStop(currentIdx);
                              };
                            }
                            if (typeof origPreviousStop === 'function') {
                              window.previousStop = function() {
                                origPreviousStop();
                                if (currentIdx > 0) currentIdx--;
                                reportStop(currentIdx);
                              };
                            }
                            if (typeof origGoToStop === 'function') {
                              window.goToStop = function(n) {
                                origGoToStop(n);
                                currentIdx = n - 1;
                                reportStop(currentIdx);
                              };
                            }
                            // Also hook audio 'ended' events to detect auto-advance
                            var audios = document.querySelectorAll('audio');
                            audios.forEach(function(audio, idx) {
                              audio.addEventListener('play', function() {
                                if (idx !== currentIdx) {
                                  currentIdx = idx;
                                  reportStop(currentIdx);
                                }
                              });
                            });
                            // Report initial state
                            reportStop(0);
                          })();
                        """);
                      } catch (e) {
                        await DebugLogHelper.addDebugLog('SWIPE: Failed to inject stop listener: $e');
                      }
                
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
                      unawaited(DebugLogHelper.addDebugLog('VOICE: WebView load error: ${error.description} for URL: ${request.url}')); // WebView callback
                    },
                  ),
                ),
                // Swipe feedback widget — always visible at bottom
                SwipeFeedbackWidget(
                  currentStopIndex: _currentStopIndex,
                  tourId: widget.tourId ?? _deriveTourId(),
                  jobId: widget.jobId,
                  tourPath: widget.tourPath,
                  onSwipe: (swipe) {
                    // Light haptic feedback on swipe
                    HapticFeedback.lightImpact();
                  },
                ),
              ],
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
  /// Derive tour_id from the tour path (last segment of path).
  String _deriveTourId() {
    final segments = widget.tourPath.split('/');
    return segments.isNotEmpty ? segments.last : 'unknown';
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