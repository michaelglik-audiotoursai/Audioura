import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import '../services/voice_control_service_news.dart';
import 'debug_log_viewer_screen.dart';

class NewsPlayerScreen extends StatefulWidget {
  final String articlePath;
  final String articleTitle;

  const NewsPlayerScreen({
    super.key,
    required this.articlePath,
    required this.articleTitle,
  });

  @override
  State<NewsPlayerScreen> createState() => _NewsPlayerScreenState();
}

class _NewsPlayerScreenState extends State<NewsPlayerScreen> {
  final VoiceControlServiceNews voiceService = VoiceControlServiceNews();
  InAppWebViewController? webController;
  bool _isListening = false;
  String _displayTitle = '';

  @override
  void initState() {
    super.initState();
    _displayTitle = widget.articleTitle;
    _initializeVoiceControl();
    _loadShortTitle();
  }

  Future<void> _loadShortTitle() async {
    try {
      final shortTitleFile = File('${widget.articlePath}/audiotours_short_title.txt');
      if (await shortTitleFile.exists()) {
        final shortTitle = await shortTitleFile.readAsString();
        setState(() {
          _displayTitle = shortTitle.trim();
        });
        await DebugLogHelper.addDebugLog('NEWS: Loaded short title: $_displayTitle');
      } else {
        await DebugLogHelper.addDebugLog('NEWS: No short title file found, using original title');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS: Error loading short title: $e');
    }
  }

  Future<void> _initializeVoiceControl() async {
    await voiceService.initialize();
    voiceService.onVoiceCommand = _handleVoiceCommand;
  }

  void _handleVoiceCommand(String action, int? value, String message) async {
    await DebugLogHelper.addDebugLog('NEWS VOICE: Executing action: $action');

    if (webController != null) {
      final resetResult = await webController!.evaluateJavascript(source: 'window.resetVoiceControlState()');
      await DebugLogHelper.addDebugLog('NEWS VOICE: Interrupted - $resetResult');
    }

    setState(() {
      _isListening = false;
    });

    try {
      if (webController != null) {
        final testResult = await webController!.evaluateJavascript(source: '"JS_TEST_OK"');
        await DebugLogHelper.addDebugLog('NEWS VOICE: JavaScript test result: $testResult');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: JavaScript test failed: $e');
    }

    try {
      if (webController != null) {
        String jsCommand = '';

        switch (action) {
          case 'play':
          case 'listen':
          case 'read':
            jsCommand = 'window.playAudio()';
            break;
          case 'pause':
            jsCommand = '(function() { document.querySelectorAll("audio").forEach(a => a.pause()); return "All audio paused"; })()';
            break;
          case 'next_topic':
            jsCommand = 'window.nextTopic()';
            break;
          case 'next_and_play':
            jsCommand = 'window.nextTopic()';
            break;
          case 'previous_topic':
            jsCommand = 'window.previousTopic()';
            break;
          case 'previous_and_play':
            jsCommand = 'window.previousTopic()';
            break;
          case 'repeat':
            jsCommand = 'window.repeatTopic()';
            break;
          case 'repeat_and_play':
            jsCommand = 'window.repeatTopic()';
            break;
          case 'forward':
            jsCommand = 'window.seekForward(${value ?? 10})';
            break;
          case 'backward':
            jsCommand = 'window.seekBackward(${value ?? 10})';
            break;
          case 'play_full_article':
            jsCommand = 'window.playFullArticle()';
            break;
          case 'play_summary':
            jsCommand = 'window.playSummary()';
            break;
          case 'list_points':
            jsCommand = 'window.listPoints()';
            break;
          case 'list_major_topics':
            if (webController != null) {
              final result = await webController!.evaluateJavascript(source: 'window.listPoints()');
              await DebugLogHelper.addDebugLog('NEWS VOICE: listPoints result: $result');
              final durationStr = await webController!.evaluateJavascript(source: 'window.getTopicsAudioDuration()');
              final duration = double.tryParse(durationStr.toString()) ?? 3.0;
              final waitTime = (duration + 1).round();
              Timer(Duration(seconds: waitTime), () async {
                final stillReading = await webController!.evaluateJavascript(source: 'window.isListBeingRead()');
                if (stillReading.toString() == 'false') {
                  voiceService.startVoiceListening();
                }
              });
            }
            return;
          case 'play_topic':
            if (value != null) jsCommand = 'window.playPoint($value)';
            break;
          case 'play_point':
            if (value != null) jsCommand = 'window.playPoint($value)';
            break;
          case 'play_topic_by_name':
            String searchText = message.replaceAll(RegExp(r'\b(play|topic|point|the|a|an)\b'), '').trim();
            if (searchText.isNotEmpty) {
              final result = await webController!.evaluateJavascript(source: 'window.findTopicByName("$searchText")');
              await DebugLogHelper.addDebugLog('NEWS VOICE: Topic search result: $result');
              try {
                final searchResult = json.decode(result.toString());
                if (searchResult['found'] == true) {
                  final topicIndex = searchResult['topic'];
                  await webController!.evaluateJavascript(source: 'window.playPoint($topicIndex)');
                } else {
                  await webController!.evaluateJavascript(source: 'window.playAudio()');
                }
              } catch (e) {
                await webController!.evaluateJavascript(source: 'window.playAudio()');
              }
            }
            return;
          case 'show_help':
            if (webController != null) {
              await webController!.evaluateJavascript(source: 'window.showHelp()');
              Timer(Duration(seconds: 3), () => voiceService.startVoiceListening());
            }
            return;
          case 'next_article':
            await _navigateToNextArticle();
            return;
          case 'previous_article':
            await _navigateToPreviousArticle();
            return;
          case 'navigate_to_listen_page':
            await _navigateToListenPage();
            return;
          case 'pause_for_listening':
            jsCommand = '(function() { document.querySelectorAll("audio").forEach(a => a.pause()); return "All audio paused for listening"; })()';
            break;
        }

        if (jsCommand.isNotEmpty) {
          await webController!.evaluateJavascript(source: 'window.pauseAudio()');
          final result = await webController!.evaluateJavascript(source: jsCommand);
          await DebugLogHelper.addDebugLog('NEWS VOICE: $action result: $result');
          if (['play', 'listen', 'read', 'repeat', 'repeat_and_play', 'next_and_play', 'previous_and_play'].contains(action)) {
            await webController!.evaluateJavascript(source: 'window.playAudio()');
          }
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: $action error: $e');
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('📰 $_displayTitle'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: Icon(Icons.help_outline),
            onPressed: () async {
              if (webController != null) {
                final helpText = await webController!.evaluateJavascript(source: 'window.getHelpText()');
                await webController!.evaluateJavascript(source: 'window.showHelp()');
                _showHelpDialog(helpText.toString());
              }
            },
          ),
        ],
      ),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri('file://${widget.articlePath}/index.html')),
        initialSettings: InAppWebViewSettings(
          javaScriptEnabled: true,
          mediaPlaybackRequiresUserGesture: false,
          useShouldOverrideUrlLoading: false,
          useOnLoadResource: false,
          useHybridComposition: true,
          allowContentAccess: true,
          allowFileAccess: true,
          allowsInlineMediaPlayback: true,
          allowsAirPlayForMediaPlayback: true,
        ),
        onWebViewCreated: (controller) async {
          webController = controller;
          await DebugLogHelper.addDebugLog('NEWS: InAppWebView created');
          await DebugLogHelper.addDebugLog('NEWS: Loading file: file://${widget.articlePath}/index.html');
          final indexFile = File('${widget.articlePath}/index.html');
          final exists = await indexFile.exists();
          await DebugLogHelper.addDebugLog('NEWS: File exists: $exists');
          if (!exists) {
            await DebugLogHelper.addDebugLog('NEWS: ERROR - index.html does not exist at path!');
          }
        },
        onLoadStop: (controller, url) async {
          await DebugLogHelper.addDebugLog('NEWS: WebView loaded: $url');
          try {
            final jsResult = await controller.evaluateJavascript(source: 'document.title');
            await DebugLogHelper.addDebugLog('NEWS: Document title: $jsResult');
            final audioElements = await controller.evaluateJavascript(source: 'document.querySelectorAll("audio").length');
            await DebugLogHelper.addDebugLog('NEWS: Audio elements found: $audioElements');
            await Future.delayed(Duration(milliseconds: 1000));
            final playResult = await controller.evaluateJavascript(source: '''
              (function() {
                try {
                  document.querySelectorAll('audio').forEach(audio => {
                    audio.pause();
                    audio.currentTime = 0;
                  });
                  const firstAudio = document.getElementById('audio-1');
                  if (firstAudio) {
                    firstAudio.play();
                    return 'SUCCESS: Playing audio-1';
                  }
                  return 'ERROR: audio-1 not found';
                } catch (error) {
                  return 'ERROR: ' + error.message;
                }
              })()
            ''');
            await DebugLogHelper.addDebugLog('NEWS: Auto-play result: $playResult');
          } catch (e) {
            await DebugLogHelper.addDebugLog('NEWS: JavaScript error: $e');
          }
        },
        onReceivedError: (controller, request, error) async {
          unawaited(DebugLogHelper.addDebugLog('NEWS: WebView error: ${error.description} for URL: ${request.url}'));
          final filePath = widget.articlePath + '/index.html';
          final file = File(filePath);
          final exists = await file.exists();
          await DebugLogHelper.addDebugLog('NEWS: File exists check - $filePath: $exists');
        },
      ),
      floatingActionButton: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          FloatingActionButton(
            heroTag: "help",
            mini: true,
            onPressed: () async {
              if (webController != null) {
                final helpText = await webController!.evaluateJavascript(source: 'window.getHelpText()');
                await webController!.evaluateJavascript(source: 'window.showHelp()');
                _showHelpDialog(helpText.toString());
              }
            },
            backgroundColor: const Color(0xFF95a5a6),
            child: Icon(Icons.help_outline),
          ),
          SizedBox(width: 16),
          FloatingActionButton(
            heroTag: "mic",
            onPressed: () {
              setState(() {
                _isListening = !_isListening;
              });
              if (_isListening) voiceService.startVoiceListening();
            },
            backgroundColor: _isListening ? Colors.red : const Color(0xFF3498db),
            child: Icon(_isListening ? Icons.mic : Icons.mic_none),
          ),
        ],
      ),
    );
  }

  Future<void> _navigateToPreviousArticle() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      int currentIndex = -1;
      for (int i = 0; i < savedNews.length; i++) {
        final article = json.decode(savedNews[i]);
        if (article['path'] == widget.articlePath) { currentIndex = i; break; }
      }
      if (currentIndex > 0) {
        final previousArticle = json.decode(savedNews[currentIndex - 1]);
        if (webController != null) await webController!.evaluateJavascript(source: 'window.pauseAudio()');
        Navigator.pushReplacement(context, MaterialPageRoute(
          builder: (context) => NewsPlayerScreen(articlePath: previousArticle['path'], articleTitle: previousArticle['title']),
        ));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Already at first article')));
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Previous article error: $e');
    }
  }

  Future<void> _navigateToNextArticle() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      int currentIndex = -1;
      for (int i = 0; i < savedNews.length; i++) {
        final article = json.decode(savedNews[i]);
        if (article['path'] == widget.articlePath) { currentIndex = i; break; }
      }
      if (currentIndex >= 0 && currentIndex < savedNews.length - 1) {
        final nextArticle = json.decode(savedNews[currentIndex + 1]);
        if (webController != null) await webController!.evaluateJavascript(source: 'window.pauseAudio()');
        Navigator.pushReplacement(context, MaterialPageRoute(
          builder: (context) => NewsPlayerScreen(articlePath: nextArticle['path'], articleTitle: nextArticle['title']),
        ));
      } else {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No more articles')));
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Next article error: $e');
    }
  }

  Future<void> _navigateToListenPage() async {
    if (webController != null) await webController!.evaluateJavascript(source: 'window.pauseAudio()');
    Navigator.pop(context);
  }

  void _showHelpDialog(String helpJsonString) async {
    try {
      final helpFile = File('${widget.articlePath}/help_commands.txt');
      if (await helpFile.exists()) {
        final helpText = await helpFile.readAsString();
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: Text('Voice Commands'),
            content: SingleChildScrollView(child: Text(helpText, style: TextStyle(fontSize: 14))),
            actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: Text('Close'))],
          ),
        );
        return;
      }
      final helpData = json.decode(helpJsonString.replaceAll('"', '"'));
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(helpData['title'] ?? 'Voice Commands'),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var category in helpData['commands'] ?? [])
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(category['category'] ?? '', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                      SizedBox(height: 4),
                      for (var item in category['items'] ?? [])
                        Padding(padding: EdgeInsets.only(left: 16, bottom: 2), child: Text('• $item')),
                      SizedBox(height: 8),
                    ],
                  ),
              ],
            ),
          ),
          actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: Text('Close'))],
        ),
      );
    } catch (e) {
      const fallback = 'Say Play, Pause, Next topic, Previous topic, Forward/Backward N seconds, Repeat, Next article, Previous article';
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Voice Commands'),
          content: Text(fallback, style: TextStyle(fontSize: 14)),
          actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: Text('Close'))],
        ),
      );
    }
  }

  @override
  void dispose() {
    voiceService.dispose();
    super.dispose();
  }
}
