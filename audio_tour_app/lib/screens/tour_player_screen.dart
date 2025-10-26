import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'dart:io';
import 'dart:async';
import 'voice_methods.dart';
import 'debug_log_viewer_screen.dart';

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
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri('file://${widget.tourPath}/index.html')),
        initialOptions: InAppWebViewGroupOptions(
          crossPlatform: InAppWebViewOptions(
            javaScriptEnabled: true,
            mediaPlaybackRequiresUserGesture: false, // CRITICAL: Enable audio autoplay
            useShouldOverrideUrlLoading: false,
            useOnLoadResource: false,
          ),
          android: AndroidInAppWebViewOptions(
            useHybridComposition: true,
            allowContentAccess: true,
            allowFileAccess: true,
          ),
          ios: IOSInAppWebViewOptions(
            allowsInlineMediaPlayback: true,
            allowsAirPlayForMediaPlayback: true,
          ),
        ),
        onWebViewCreated: (InAppWebViewController controller) async {
          _controller = controller;
          webController = controller;
          await DebugLogHelper.addDebugLog('VOICE: InAppWebView created, controller set');
        },
        onLoadStop: (InAppWebViewController controller, Uri? url) async {
          await DebugLogHelper.addDebugLog('VOICE: WebView loaded: $url');
          await DebugLogHelper.addDebugLog('VOICE: Getting tour info');
          getTourInfo();
        },
        onLoadError: (InAppWebViewController controller, Uri? url, int code, String message) {
          DebugLogHelper.addDebugLog('VOICE: WebView load error: $code - $message for URL: $url');
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