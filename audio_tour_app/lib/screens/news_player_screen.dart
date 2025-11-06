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
    _displayTitle = widget.articleTitle; // Default to original title
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
    
    // Always reset all state when voice control starts (interruption handling)
    if (webController != null) {
      final resetResult = await webController!.evaluateJavascript(source: 'window.resetVoiceControlState()');
      await DebugLogHelper.addDebugLog('NEWS VOICE: Interrupted - $resetResult');
    }
    
    // Reset microphone to blue state after command
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
            // Special handling: don't exit voice control, keep listening
            if (webController != null) {
              final result = await webController!.evaluateJavascript(source: 'window.listPoints()');
              await DebugLogHelper.addDebugLog('NEWS VOICE: listPoints result: $result');
              
              // Get topics audio duration for proper timing
              final durationStr = await webController!.evaluateJavascript(source: 'window.getTopicsAudioDuration()');
              final duration = double.tryParse(durationStr.toString()) ?? 3.0;
              final waitTime = (duration + 1).round(); // Add 1 second buffer
              
              await DebugLogHelper.addDebugLog('NEWS VOICE: Topics duration: ${duration}s, waiting: ${waitTime}s');
              
              // Continue listening after topics finish
              Timer(Duration(seconds: waitTime), () async {
                // Check if list is still being read before resuming
                final stillReading = await webController!.evaluateJavascript(source: 'window.isListBeingRead()');
                if (stillReading.toString() == 'false') {
                  voiceService.startVoiceListening();
                }
              });
            }
            return;
          case 'play_topic':
            if (value != null) {
              jsCommand = 'window.playPoint($value)';
            }
            break;
          case 'play_point':
            if (value != null) {
              jsCommand = 'window.playPoint($value)';
            }
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
                  final topicTitle = searchResult['title'];
                  final score = searchResult['score'];
                  
                  await DebugLogHelper.addDebugLog('NEWS VOICE: Found topic match - Index: $topicIndex, Title: "$topicTitle", Score: $score');
                  
                  final playResult = await webController!.evaluateJavascript(source: 'window.playPoint($topicIndex)');
                  await DebugLogHelper.addDebugLog('NEWS VOICE: Play topic by name result: $playResult');
                } else {
                  await DebugLogHelper.addDebugLog('NEWS VOICE: No topic match found for: "$searchText"');
                  final playResult = await webController!.evaluateJavascript(source: 'window.playAudio()');
                  await DebugLogHelper.addDebugLog('NEWS VOICE: Fallback playAudio result: $playResult');
                }
              } catch (e) {
                await DebugLogHelper.addDebugLog('NEWS VOICE: Error parsing topic search result: $e');
                final playResult = await webController!.evaluateJavascript(source: 'window.playAudio()');
                await DebugLogHelper.addDebugLog('NEWS VOICE: Error fallback playAudio result: $playResult');
              }
            }
            return;
          case 'show_help':
            if (webController != null) {
              final helpText = await webController!.evaluateJavascript(source: 'window.getHelpText()');
              final helpResult = await webController!.evaluateJavascript(source: 'window.showHelp()');
              await DebugLogHelper.addDebugLog('NEWS VOICE: Help audio result: $helpResult');
              
              // Continue listening after help finishes
              Timer(Duration(seconds: 3), () {
                voiceService.startVoiceListening();
              });
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
          // First pause all audio
          await webController!.evaluateJavascript(source: 'window.pauseAudio()');
          await DebugLogHelper.addDebugLog('NEWS VOICE: Paused audio before $action');
          
          final result = await webController!.evaluateJavascript(source: jsCommand);
          await DebugLogHelper.addDebugLog('NEWS VOICE: $action result: $result');
          
          // Call playAudio for play, repeat, and navigation commands
          if (['play', 'listen', 'read', 'repeat', 'repeat_and_play', 'next_and_play', 'previous_and_play'].contains(action)) {
            final playResult = await webController!.evaluateJavascript(source: 'window.playAudio()');
            await DebugLogHelper.addDebugLog('NEWS VOICE: playAudio result: $playResult');
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
                await DebugLogHelper.addDebugLog('NEWS: Help button pressed');
                final helpText = await webController!.evaluateJavascript(source: 'window.getHelpText()');
                final helpResult = await webController!.evaluateJavascript(source: 'window.showHelp()');
                await DebugLogHelper.addDebugLog('NEWS: Help audio result: $helpResult');
                
                // Show help dialog with text commands
                _showHelpDialog(helpText.toString());
              }
            },
          ),
        ],
      ),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri('file://${widget.articlePath}/index.html')),
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
        onWebViewCreated: (controller) async {
          webController = controller;
          await DebugLogHelper.addDebugLog('NEWS: InAppWebView created, controller set');
          await DebugLogHelper.addDebugLog('NEWS: Loading file: file://${widget.articlePath}/index.html');
          
          // Verify file exists before loading
          final indexFile = File('${widget.articlePath}/index.html');
          final exists = await indexFile.exists();
          await DebugLogHelper.addDebugLog('NEWS: File exists before WebView load: $exists');
          
          if (!exists) {
            await DebugLogHelper.addDebugLog('NEWS: ERROR - index.html file does not exist at path!');
          }
        },
        onLoadStop: (controller, url) async {
          await DebugLogHelper.addDebugLog('NEWS: WebView loaded successfully: $url');
          
          // Test JavaScript availability and HTML content
          try {
            final jsResult = await controller.evaluateJavascript(source: 'document.title');
            await DebugLogHelper.addDebugLog('NEWS: Document title: $jsResult');
            
            final bodyContent = await controller.evaluateJavascript(source: 'document.body ? document.body.innerHTML.substring(0, 200) : "No body"');
            await DebugLogHelper.addDebugLog('NEWS: Body content preview: $bodyContent');
            
            final audioElements = await controller.evaluateJavascript(source: 'document.querySelectorAll("audio").length');
            await DebugLogHelper.addDebugLog('NEWS: Audio elements found: $audioElements');
            
            // Auto-start first audio with duplicate prevention
            await Future.delayed(Duration(milliseconds: 1000));
            final playResult = await controller.evaluateJavascript(source: '''
              (function() {
                try {
                  // Stop all audio first to prevent duplicates
                  document.querySelectorAll('audio').forEach(audio => {
                    audio.pause();
                    audio.currentTime = 0;
                  });
                  
                  // Play only the first audio-1 (summary)
                  const firstAudio = document.getElementById('audio-1');
                  if (firstAudio) {
                    firstAudio.play();
                    return 'SUCCESS: Playing first audio-1 only';
                  }
                  return 'ERROR: First audio not found';
                } catch (error) {
                  return 'ERROR: ' + error.message;
                }
              })()
            ''');
            await DebugLogHelper.addDebugLog('NEWS: Auto-play result: $playResult');
            
          } catch (e) {
            await DebugLogHelper.addDebugLog('NEWS: JavaScript test failed: $e');
          }
        },
        onLoadError: (controller, url, code, message) async {
          await DebugLogHelper.addDebugLog('NEWS: WebView load error: $code - $message for URL: $url');
          
          // Check if file exists
          final filePath = widget.articlePath + '/index.html';
          final file = File(filePath);
          final exists = await file.exists();
          await DebugLogHelper.addDebugLog('NEWS: File exists check - $filePath: $exists');
          
          if (exists) {
            final size = await file.length();
            final content = await file.readAsString();
            await DebugLogHelper.addDebugLog('NEWS: File size: $size bytes');
            await DebugLogHelper.addDebugLog('NEWS: File content preview: ${content.substring(0, content.length > 200 ? 200 : content.length)}');
          }
        },
        androidOnPermissionRequest: (controller, origin, resources) async {
          return PermissionRequestResponse(
            resources: resources,
            action: PermissionRequestResponseAction.GRANT,
          );
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
                await DebugLogHelper.addDebugLog('NEWS: Help FAB pressed');
                final helpText = await webController!.evaluateJavascript(source: 'window.getHelpText()');
                final helpResult = await webController!.evaluateJavascript(source: 'window.showHelp()');
                await DebugLogHelper.addDebugLog('NEWS: Help audio result: $helpResult');
                
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
              if (_isListening) {
                voiceService.startVoiceListening();
              }
            },
            backgroundColor: _isListening ? Colors.red : const Color(0xFF3498db),
            child: Icon(_isListening ? Icons.mic : Icons.mic_none),
          ),
        ],
      ),
    );
  }

  Future<void> _listMajorTopics() async {
    try {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Playing topics list audio');
      
      if (webController != null) {
        // Use the HTML's listPoints function directly
        final result = await webController!.evaluateJavascript(source: 'window.listPoints()');
        
        await DebugLogHelper.addDebugLog('NEWS VOICE: Topics audio result: $result');
        
        // Start listening after a delay
        Timer(Duration(seconds: 2), () {
          voiceService.startVoiceListening();
        });
        
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: List topics error: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error listing topics: $e')),
      );
    }
  }

  
  String _numberToWord(int number) {
    const words = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten'];
    return number < words.length ? words[number] : number.toString();
  }

  Future<void> _navigateToPreviousArticle() async {
    try {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Starting previous article navigation');
      
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      
      await DebugLogHelper.addDebugLog('NEWS VOICE: Found ${savedNews.length} saved articles');
      
      if (savedNews.isEmpty) {
        await DebugLogHelper.addDebugLog('NEWS VOICE: No articles available');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No articles available')),
        );
        return;
      }
      
      // Find current article index
      int currentIndex = -1;
      for (int i = 0; i < savedNews.length; i++) {
        final article = json.decode(savedNews[i]);
        if (article['path'] == widget.articlePath) {
          currentIndex = i;
          await DebugLogHelper.addDebugLog('NEWS VOICE: Current article index: $i');
          break;
        }
      }
      
      // Navigate to previous article
      if (currentIndex > 0) {
        final previousArticle = json.decode(savedNews[currentIndex - 1]);
        await DebugLogHelper.addDebugLog('NEWS VOICE: Navigating to previous article: ${previousArticle['title']}');
        
        // Pause current audio before leaving
        if (webController != null) {
          await webController!.evaluateJavascript(source: 'window.pauseAudio()');
        }
        
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => NewsPlayerScreen(
              articlePath: previousArticle['path'],
              articleTitle: previousArticle['title'],
            ),
          ),
        );
      } else {
        await DebugLogHelper.addDebugLog('NEWS VOICE: Already at first article (current index: $currentIndex)');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Already at first article')),
        );
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Previous article error: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }

  Future<void> _navigateToNextArticle() async {
    try {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Starting next article navigation');
      
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      
      await DebugLogHelper.addDebugLog('NEWS VOICE: Found ${savedNews.length} saved articles');
      
      if (savedNews.isEmpty) {
        await DebugLogHelper.addDebugLog('NEWS VOICE: No articles available');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No articles available')),
        );
        return;
      }
      
      // Find current article index
      int currentIndex = -1;
      for (int i = 0; i < savedNews.length; i++) {
        final article = json.decode(savedNews[i]);
        if (article['path'] == widget.articlePath) {
          currentIndex = i;
          await DebugLogHelper.addDebugLog('NEWS VOICE: Current article index: $i');
          break;
        }
      }
      
      // Navigate to next article
      if (currentIndex >= 0 && currentIndex < savedNews.length - 1) {
        final nextArticle = json.decode(savedNews[currentIndex + 1]);
        await DebugLogHelper.addDebugLog('NEWS VOICE: Navigating to next article: ${nextArticle['title']}');
        
        // Pause current audio before leaving
        if (webController != null) {
          await webController!.evaluateJavascript(source: 'window.pauseAudio()');
        }
        
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => NewsPlayerScreen(
              articlePath: nextArticle['path'],
              articleTitle: nextArticle['title'],
            ),
          ),
        );
      } else {
        await DebugLogHelper.addDebugLog('NEWS VOICE: No more articles (current index: $currentIndex, total: ${savedNews.length})');
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No more articles')),
        );
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Next article error: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }

  Future<void> _navigateToListenPage() async {
    try {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Navigating to Listen Page');
      
      // Pause current audio before leaving
      if (webController != null) {
        await webController!.evaluateJavascript(source: 'window.pauseAudio()');
      }
      
      // Navigate back to Listen Page (My News Screen)
      Navigator.pop(context);
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS VOICE: Navigate to Listen Page error: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error returning to Listen Page: $e')),
      );
    }
  }

  void _showHelpDialog(String helpJsonString) {
    try {
      final helpData = json.decode(helpJsonString.replaceAll('"', '"'));
      
      showDialog(
        context: context,
        builder: (BuildContext context) {
          return AlertDialog(
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
                        Text(
                          category['category'] ?? '',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                        ),
                        SizedBox(height: 4),
                        for (var item in category['items'] ?? [])
                          Padding(
                            padding: EdgeInsets.only(left: 16, bottom: 2),
                            child: Text('• $item'),
                          ),
                        SizedBox(height: 8),
                      ],
                    ),
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
    } catch (e) {
      // Fallback simple dialog
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Voice Commands'),
          content: Text('Say "What are my options" to hear all available voice commands.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text('Close'),
            ),
          ],
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