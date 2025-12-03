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
      await DebugLogHelper.addDebugLog('TOUR_PLAYER: Using web blob URL: $blobUrl');
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


}