import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';



import '../services/tour_status_service.dart';
import '../services/background_tour_monitor.dart';

import '../screens/debug_log_viewer_screen.dart';
import '../screens/tour_player_screen.dart';
import '../screens/news_player_screen.dart';
import 'main_screen.dart';

class TourGeneratorScreen extends StatefulWidget {
  const TourGeneratorScreen({super.key});

  @override
  State<TourGeneratorScreen> createState() => _TourGeneratorScreenState();
}

class _TourGeneratorScreenState extends State<TourGeneratorScreen> {
  final TextEditingController _tourRequestController = TextEditingController();
  final TextEditingController _stopCountController = TextEditingController(text: '10');
  bool _isGenerating = false;
  String _progress = '';
  String _apiBaseUrl = 'http://192.168.0.217:5002';
  List<Map<String, dynamic>> _pendingTours = [];
  List<Map<String, dynamic>> _backgroundTours = [];
  String _appMode = 'Tours'; // Default to Tours mode
  String _contentType = 'Article'; // Article or Newsletter


  
  @override
  void initState() {
    super.initState();
    _loadServerIp();
    _loadBackgroundStatus();
    _loadAppMode();
    
    // Check for stalled tours immediately
    BackgroundTourMonitor.checkStalledTours();
    
    // Auto-refresh background status every 10 seconds
    Timer.periodic(const Duration(seconds: 10), (timer) {
      if (mounted) {
        // Check for stalled tours
        BackgroundTourMonitor.checkStalledTours();
        
        // Check background tour status
        BackgroundTourMonitor.checkBackgroundTourStatus();
        
        // Reload background status
        _loadBackgroundStatus();
      } else {
        timer.cancel();
      }
    });
  }
  
  Future<void> _loadBackgroundStatus() async {
    final prefs = await SharedPreferences.getInstance();
    final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
    final readyTours = prefs.getStringList('background_tours') ?? [];
    
    setState(() {
      _pendingTours = pendingTours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
      _backgroundTours = readyTours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
    });
  }
  
  Future<void> _clearBackgroundStatus() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('pending_background_tours', []);
    await prefs.setStringList('background_tours', []);
    
    setState(() {
      _pendingTours = [];
      _backgroundTours = [];
    });
    
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Background status cleared'),
        backgroundColor: Colors.green,
      ),
    );
  }
  
  Future<void> _loadServerIp() async {
    final prefs = await SharedPreferences.getInstance();
    final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
    print('Server IP from preferences: $serverIp');
    setState(() {
      _apiBaseUrl = 'http://$serverIp:5002';
    });
    print('API Base URL: $_apiBaseUrl');
  }
  
  Future<void> _loadAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _appMode = prefs.getString('app_mode') ?? 'Tours';
      if (_appMode == 'Audio') {
        _stopCountController.text = '4'; // Default for Audio mode
      }
    });
  }

  Map<String, dynamic> _parseTourRequest(String request) {
    String lowerRequest = request.toLowerCase();
    
    String tourType = 'museum';
    if (lowerRequest.contains('walking') || lowerRequest.contains('walk')) {
      tourType = 'walking';
    } else if (lowerRequest.contains('museum')) {
      tourType = 'museum';
    } else if (lowerRequest.contains('park')) {
      tourType = 'park';
    } else if (lowerRequest.contains('exhibit')) {
      tourType = 'exhibit';
    }
    
    String location = request;
    RegExp forMatch = RegExp(r'for\s+(.+)', caseSensitive: false);
    Match? match = forMatch.firstMatch(request);
    if (match != null) {
      location = match.group(1)!.trim();
    }
    
    return {
      'location': location,
      'tour_type': tourType,
      // Don't set total_stops here, it will be set by the caller
    };
  }

  String _sanitizeInput(String input) {
    // Remove potentially dangerous characters and normalize whitespace
    return input
        .replaceAll(RegExp(r'[\r\n]+'), ' ')  // Replace newlines with spaces
        .replaceAll(RegExp(r'[<>"/\\]'), '')  // Remove HTML/script/path chars
        .replaceAll(RegExp(r'\s+'), ' ')  // Normalize multiple spaces
        .trim();
  }

  Future<void> _generateTour() async {
    final rawInput = _tourRequestController.text.trim();
    if (rawInput.isEmpty) {
      _showError('Please enter a tour request');
      return;
    }
    
    final sanitizedInput = _sanitizeInput(rawInput);
    if (sanitizedInput.isEmpty) {
      _showError('Please enter valid tour request text');
      return;
    }
    
    // Validate stop count
    int stopCount;
    try {
      stopCount = int.parse(_stopCountController.text);
      if (stopCount < 1 || stopCount > 30) {
        _showError('Number of stops must be between 1 and 30');
        return;
      }
    } catch (e) {
      _showError('Please enter a valid number of stops');
      return;
    }
    
    // Check for duplicate tour
    if (await _checkDuplicateTour(_tourRequestController.text)) {
      final confirmed = await _showDuplicateDialog();
      if (!confirmed) return;
    }

    setState(() {
      _isGenerating = true;
      _progress = 'Starting tour generation...';
    });

    try {
      Map<String, dynamic> tourData = _parseTourRequest(sanitizedInput);
      tourData['total_stops'] = stopCount; // Add custom stop count
      
      // Step 1: Start tour generation
      final response = await http.post(
        Uri.parse('$_apiBaseUrl/generate-complete-tour'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(tourData),
      );

      if (response.statusCode != 200) {
        throw Exception('Failed to start tour generation');
      }

      Map<String, dynamic> result = jsonDecode(response.body);
      String jobId = result['job_id'];
      
      // Add user tracking for foreground generation with the job ID and stop count
      await TourStatusService.trackTourRequest(sanitizedInput, jobId, stopCount: stopCount);
      
      // Step 2: Poll for completion and auto-download
      await _pollAndAutoDownload(jobId, tourData['location']);
      
    } catch (error) {
      print('DETAILED ERROR: $error');
      _showError('Failed to generate tour: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _pollAndAutoDownload(String jobId, String location) async {
    const int maxAttempts = 90; // 15 minutes timeout
    int attempts = 0;
    
    // Create unique timer for this job to avoid conflicts
    Timer? jobTimer;
    jobTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {
      try {
        final response = await http.get(
          Uri.parse('$_apiBaseUrl/status/$jobId'),
        );
        
        if (response.statusCode == 200) {
          Map<String, dynamic> status = jsonDecode(response.body);
          
          setState(() {
            _progress = status['progress'] ?? 'Processing...';
          });
          
          if (status['status'] == 'completed') {
            timer.cancel();
            setState(() {
              _progress = 'Downloading and extracting tour...';
            });
            
            // Auto-download, extract, and play
            await _autoDownloadAndPlay(jobId, location);
            
            // Update tour request status to completed AFTER download
            // This ensures we don't mark it complete until we've actually downloaded it
            await TourStatusService.updateTourStatus(jobId, 'completed');
            
          } else if (status['status'] == 'error') {
            timer.cancel();
            await TourStatusService.updateTourStatus(jobId, 'failed');
            throw Exception(status['error'] ?? 'Tour generation failed');
          } else if (attempts >= maxAttempts) {
            timer.cancel();
            await TourStatusService.updateTourStatus(jobId, 'timeout');
            _showTimeoutError();
            setState(() {
              _isGenerating = false;
              _progress = '';
            });
            return;
          }
          
          attempts++;
        }
      } catch (error) {
        timer.cancel();
        await TourStatusService.updateTourStatus(jobId, 'failed');
        _showError('Error: $error');
        setState(() {
          _isGenerating = false;
          _progress = '';
        });
      }
    });
  }

  Future<void> _autoDownloadAndPlay(String jobId, String location) async {
    try {
      // Step 1: Download ZIP file
      setState(() {
        _progress = 'Downloading tour files...';
      });
      
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/download/$jobId'),
      );
      
      if (response.statusCode != 200) {
        throw Exception('Failed to download tour');
      }
      
      // Step 2: Get app documents directory
      final directory = await getApplicationDocumentsDirectory();
      final toursDir = Directory('${directory.path}/tours');
      if (!await toursDir.exists()) {
        await toursDir.create(recursive: true);
      }
      
      // Step 3: Save ZIP file temporarily
      setState(() {
        _progress = 'Extracting tour files...';
      });
      
      final zipPath = '${toursDir.path}/${jobId}.zip';
      final zipFile = File(zipPath);
      await zipFile.writeAsBytes(response.bodyBytes);
      
      // Step 4: Extract ZIP
      final bytes = await zipFile.readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      
      final extractPath = '${toursDir.path}/${jobId}';
      final extractDir = Directory(extractPath);
      if (await extractDir.exists()) {
        await extractDir.delete(recursive: true);
      }
      await extractDir.create(recursive: true);
      
      for (final file in archive) {
        final filename = file.name;
        if (file.isFile) {
          final data = file.content as List<int>;
          final extractedFile = File('${extractDir.path}/$filename');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(data);
        }
      }
      
      // Step 5: Delete ZIP file
      await zipFile.delete();
      
      // Step 6: Save tour info
      await _saveTourInfo(jobId, location, extractPath);
      
      // Step 7: Auto-navigate to tour player
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      _showSuccess('Tour ready! Opening now...');
      
      // Auto-open the tour
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => TourPlayerScreen(
            tourPath: extractPath,
            tourTitle: location,
          ),
        ),
      );
      
    } catch (error) {
      _showError('Failed to download tour: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _saveTourInfo(String jobId, String location, String path) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Get coordinates from status endpoint
      double? lat;
      double? lng;
      try {
        final statusResponse = await http.get(Uri.parse('$_apiBaseUrl/status/$jobId'));
        if (statusResponse.statusCode == 200) {
          final statusData = jsonDecode(statusResponse.body);
          if (statusData['coordinates'] != null && 
              statusData['coordinates'] is List && 
              statusData['coordinates'].length >= 2) {
            lat = statusData['coordinates'][0]?.toDouble();
            lng = statusData['coordinates'][1]?.toDouble();
            print('SAVE_TOUR: Found coordinates: $lat, $lng');
          }
        }
      } catch (e) {
        print('SAVE_TOUR: Error getting coordinates: $e');
      }
      
      // Get existing tours to generate unique title
      final tours = prefs.getStringList('saved_tours') ?? [];
      String uniqueTitle = _generateUniqueTitle(location, tours);
      
      final tourInfo = {
        'id': jobId,
        'title': uniqueTitle,
        'original_request': location,
        'path': path,
        'created': DateTime.now().toIso8601String(),
        'stops': _stopCountController.text,
        'lat': lat,
        'lng': lng,
      };
      
      print('SAVE_TOUR: Saving tour info: $tourInfo');
      
      // Add to saved tours list
      tours.add(jsonEncode(tourInfo));
      await prefs.setStringList('saved_tours', tours);
      
      // Update available tours list for voice navigation
      final tourInfoList = tours.map((tourJson) {
        final tour = jsonDecode(tourJson) as Map<String, dynamic>;
        return '${tour['title']}|${tour['path']}';
      }).toList();
      await prefs.setStringList('available_tours', tourInfoList);
      print('VOICE: Updated available_tours list with ${tourInfoList.length} tours');
      
      print('SAVE_TOUR: Tour saved successfully. Total tours: ${tours.length}');
      
      // Verify save
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      print('SAVE_TOUR: Verification - saved tours count: ${savedTours.length}');
      
    } catch (e) {
      print('SAVE_TOUR: Error saving tour info: $e');
      throw e;
    }
  }
  
  String _generateUniqueTitle(String originalTitle, List<String> existingTours) {
    // Count existing tours with similar titles
    int count = 0;
    String baseTitle = originalTitle.length > 50 ? '${originalTitle.substring(0, 50)}...' : originalTitle;
    
    for (String tourJson in existingTours) {
      final tour = jsonDecode(tourJson);
      String existingOriginal = tour['original_request'] ?? tour['title'] ?? '';
      
      if (existingOriginal.toLowerCase().contains(originalTitle.toLowerCase().substring(0, originalTitle.length > 20 ? 20 : originalTitle.length))) {
        count++;
      }
    }
    
    return count > 0 ? '$baseTitle (v${count + 1})' : baseTitle;
  }

  void _showError(String message) {
    print('ERROR: $message');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.red,
        duration: const Duration(seconds: 10),
      ),
    );
  }
  
  void _showTimeoutError() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text(
          '⏰ Tour generation timed out (15 min limit).\n'
          '🔧 Our AI administrator has been notified and help is on the way.\n'
          '✨ Feel free to try generating a new tour!',
        ),
        backgroundColor: Colors.orange,
        duration: const Duration(seconds: 15),
        action: SnackBarAction(
          label: 'Try Again',
          textColor: Colors.white,
          onPressed: () {
            _tourRequestController.clear();
          },
        ),
      ),
    );
  }

  void _showSuccess(String message) {
    print('SUCCESS: $message');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.green,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_appMode == 'Audio' ? '🎵 Generate Audio' : '🎵 Audio Tour Generator'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: Column(
                children: [
                  const Icon(Icons.phone_android, size: 40, color: Colors.green),
                  const SizedBox(height: 10),
                  const Text(
                    'Auto-Download & Play',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: Colors.green,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    _appMode == 'Tours' 
                      ? 'Tours are automatically downloaded, extracted, and ready to play!'
                      : 'Your audio editions of newsletters and articles are adapted to your tastes and controlled by your voice',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.green),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 30),
            // Content Type Switch for Audio mode
            if (_appMode == 'Audio') ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.blue.shade200),
                ),
                child: Column(
                  children: [
                    const Text(
                      'Content Type',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF2c3e50),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SegmentedButton<String>(
                      segments: const [
                        ButtonSegment(
                          value: 'Article',
                          label: Text('Article'),
                          icon: Icon(Icons.article),
                        ),
                        ButtonSegment(
                          value: 'Newsletter',
                          label: Text('Newsletter'),
                          icon: Icon(Icons.email),
                        ),
                      ],
                      selected: {_contentType},
                      onSelectionChanged: (Set<String> selection) {
                        setState(() {
                          _contentType = selection.first;
                        });
                      },
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
            ],
            Text(
              _appMode == 'Audio' 
                ? (_contentType == 'Article' 
                    ? 'Please copy your article into the text area below' 
                    : 'Please copy your newsletter with links into the text area below')
                : 'What tour would you like?',
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2c3e50),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _appMode == 'Audio' 
                ? (_contentType == 'Article' 
                    ? 'Example: "Your local newspaper article"'
                    : 'Example: "https://thegrenadianvoice.com/category/news/"')
                : 'Example: "Durant-Kenrick House and Grounds, Newton ma"',
              style: const TextStyle(
                fontSize: 14,
                color: Colors.grey,
                fontStyle: FontStyle.italic,
              ),
            ),
            const SizedBox(height: 16),
            _appMode == 'Audio' && _contentType == 'Newsletter'
                ? TextField(
                    controller: _tourRequestController,
                    maxLines: 3,
                    enabled: !_isGenerating,
                    keyboardType: TextInputType.multiline,
                    decoration: const InputDecoration(
                      hintText: 'Enter up to 3 newsletter URLs (one per line):\n\nhttps://thedailyrip.stocktwits.com/\nhttps://morningbrew.com/daily\nhttps://example.com/newsletter',
                      border: OutlineInputBorder(),
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: EdgeInsets.all(12),
                      helperText: 'Up to 3 URLs, one per line. Each will be processed for up to 10 articles.',
                    ),
                  )
                : TextField(
                    controller: _tourRequestController,
                    maxLines: 3,
                    enabled: !_isGenerating,
                    decoration: InputDecoration(
                      hintText: _appMode == 'Audio' 
                        ? 'Paste your article here...\n\nExample:\n"The Grenadian Voice: Latest News - Prime Minister announces new economic policies affecting local businesses..."' 
                        : 'Describe your desired tour...',
                      border: const OutlineInputBorder(),
                      filled: true,
                      fillColor: Colors.white,
                    ),
                  ),
            const SizedBox(height: 16),

            Row(
              children: [
                Text(
                  _appMode == 'Audio' ? 'Major Points Summary:' : 'Number of stops:',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Color(0xFF2c3e50),
                  ),
                ),
                const SizedBox(width: 16),
                SizedBox(
                  width: 80,
                  child: TextField(
                    controller: _stopCountController,
                    enabled: !_isGenerating,
                    keyboardType: TextInputType.number,
                    textAlign: TextAlign.center,
                    decoration: const InputDecoration(
                      border: OutlineInputBorder(),
                      filled: true,
                      fillColor: Colors.white,
                      contentPadding: EdgeInsets.symmetric(vertical: 8),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _appMode == 'Audio' ? '(0-5)' : '(1-30)',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Colors.grey,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _isGenerating ? null : (_appMode == 'Audio' ? _generateNews : _generateTour),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3498db),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: _isGenerating
                        ? const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                ),
                              ),
                              SizedBox(width: 10),
                              Text('Generating...'),
                            ],
                          )
                        : const Text(
                            '🎯 Generate Now',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                          ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: ElevatedButton(
                    onPressed: (_isGenerating || _appMode == 'Audio') ? null : _generateTourBackground,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF27ae60),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: const Text(
                      '🔔 Generate in Background',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ],
            ),
            if (_progress.isNotEmpty) ...[
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(15),
                decoration: BoxDecoration(
                  color: const Color(0xFFe8f4f8),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _progress,
                  style: const TextStyle(
                    color: Color(0xFF2c3e50),
                    fontSize: 16,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
            // Background Tours Status Section
            if (_pendingTours.isNotEmpty) ...[
              const SizedBox(height: 30),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange.shade200),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.notifications, color: Colors.orange),
                            SizedBox(width: 8),
                            Text(
                              'Background Tours Status',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.orange,
                              ),
                            ),
                          ],
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline, color: Colors.orange),
                          onPressed: _clearBackgroundStatus,
                          tooltip: 'Clear status',
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      '⏳ Generating:',
                      style: TextStyle(fontWeight: FontWeight.bold, color: Colors.orange),
                    ),
                    ..._pendingTours.map((tour) => Padding(
                      padding: const EdgeInsets.only(left: 16, top: 4),
                      child: Text('• ${tour['location']}', style: const TextStyle(color: Colors.orange)),
                    )),
                    const SizedBox(height: 8),
                    const Text(
                      '✅ Tours will be automatically downloaded when ready',
                      style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: Colors.green),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _generateTourBackground() async {
    final rawInput = _tourRequestController.text.trim();
    if (rawInput.isEmpty) {
      _showError('Please enter a tour request');
      return;
    }
    
    final sanitizedInput = _sanitizeInput(rawInput);
    if (sanitizedInput.isEmpty) {
      _showError('Please enter valid tour request text');
      return;
    }
    
    // Validate stop count
    int stopCount;
    try {
      stopCount = int.parse(_stopCountController.text);
      if (stopCount < 1 || stopCount > 30) {
        _showError('Number of stops must be between 1 and 30');
        return;
      }
    } catch (e) {
      _showError('Please enter a valid number of stops');
      return;
    }
    
    // Check for duplicate tour
    if (await _checkDuplicateTour(_tourRequestController.text)) {
      final confirmed = await _showDuplicateDialog();
      if (!confirmed) return;
    }

    try {
      Map<String, dynamic> tourData = _parseTourRequest(sanitizedInput);
      tourData['total_stops'] = stopCount; // Add custom stop count
      
      // Print debug info
      print('Generating background tour: ${tourData['location']}');
      print('API URL: $_apiBaseUrl/generate-complete-tour');
      
      final response = await http.post(
        Uri.parse('$_apiBaseUrl/generate-complete-tour'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(tourData),
      );

      print('Response status: ${response.statusCode}');
      print('Response body: ${response.body}');
      
      if (response.statusCode != 200) {
        throw Exception('Failed to start tour generation: ${response.body}');
      }

      Map<String, dynamic> result = jsonDecode(response.body);
      String jobId = result['job_id'];
      
      print('Job ID: $jobId');
      
      // Add user tracking with the job ID and stop count
      await TourStatusService.trackTourRequest(sanitizedInput, jobId, stopCount: stopCount);
      
      // Immediately update the UI to show the pending tour
      setState(() {
        _pendingTours.add({
          'jobId': jobId,
          'location': tourData['location'],
          'apiBaseUrl': _apiBaseUrl,
          'startTime': DateTime.now().toIso8601String(),
        });
      });
      
      // Show notification permission dialog
      _showNotificationPermissionDialog(jobId, tourData['location']);
      
      // Clear the input field
      _tourRequestController.clear();
      
    } catch (error) {
      print('ERROR: $error');
      _showError('Failed to start background generation: $error');
    }
  }

  void _showNotificationPermissionDialog(String jobId, String location) {
    print('Showing notification permission dialog for job $jobId');
    
    // Show a dialog asking for notification permission
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('🔔 Enable Notifications?'),
        content: const Text(
          'Would you like to receive a notification when your tour is ready?\n\n'
          'This will allow you to be notified when the tour generation is complete.'
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _requestNotificationPermissionAndStartBackground(jobId, location, false);
            },
            child: const Text('No Thanks'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _requestNotificationPermissionAndStartBackground(jobId, location, true);
            },
            child: const Text('Yes, Notify Me', style: TextStyle(color: Colors.blue)),
          ),
        ],
      ),
    );
  }

  Future<void> _requestNotificationPermissionAndStartBackground(String jobId, String location, bool requestPermission) async {
    print('Requesting notification permission for job $jobId, requestPermission: $requestPermission');
    
    // Only request permission if user agreed
    PermissionStatus status = PermissionStatus.denied;
    if (requestPermission) {
      status = await Permission.notification.request();
      print('Permission status: $status');
    }
    
    // Always proceed with background tour, even if permission denied
    final prefs = await SharedPreferences.getInstance();
    final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
    
    // Store the stop count for this job
    await prefs.setString('stop_count_$jobId', _stopCountController.text);
    
    // Create pending tour entry
    final pendingTour = jsonEncode({
      'jobId': jobId,
      'location': location,
      'apiBaseUrl': _apiBaseUrl,
      'startTime': DateTime.now().toIso8601String(),
      'stopCount': _stopCountController.text,
      'notificationsEnabled': requestPermission && status.isGranted,
    });
    
    print('Adding pending tour: $pendingTour');
    pendingTours.add(pendingTour);
    await prefs.setStringList('pending_background_tours', pendingTours);
    
    // Show success message based on permission status
    if (requestPermission && status.isGranted) {
      _showSuccess('Background generation started! You\'ll be notified when ready.');
    } else {
      _showSuccess('Background generation started! Check back later for results.');
    }
    
    // Clear the input field
    _tourRequestController.clear();
    
    // Refresh background status immediately
    _loadBackgroundStatus();
  }

  Future<bool> _checkDuplicateTour(String tourRequest) async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];
    
    for (String tourJson in tours) {
      final tour = jsonDecode(tourJson);
      if (tour['title'].toString().toLowerCase().contains(tourRequest.toLowerCase().substring(0, tourRequest.length > 20 ? 20 : tourRequest.length))) {
        return true;
      }
    }
    return false;
  }
  
  Future<bool> _showDuplicateDialog() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('🔄 Similar Tour Found'),
        content: const Text(
          'You may already have a similar tour. Generate anyway?\n\n'
          '💡 Tip: Each generation creates a unique tour with different content!'
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Generate Anyway', style: TextStyle(color: Colors.blue)),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }
  
  Future<void> _downloadBackgroundTour(Map<String, dynamic> tour) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      // First get status to check for coordinates
      double? lat;
      double? lng;
      try {
        final statusResponse = await http.get(Uri.parse('http://$serverIp:5002/status/${tour['id']}'));
        if (statusResponse.statusCode == 200) {
          final statusData = jsonDecode(statusResponse.body);
          if (statusData['coordinates'] != null && 
              statusData['coordinates'] is List && 
              statusData['coordinates'].length >= 2) {
            lat = statusData['coordinates'][0]?.toDouble();
            lng = statusData['coordinates'][1]?.toDouble();
            print('Found coordinates: $lat, $lng');
          }
        }
      } catch (e) {
        print('Error getting coordinates: $e');
      }
      
      // Now download the tour
      final response = await http.get(Uri.parse('http://$serverIp:5002/download/${tour['id']}'));
      
      if (response.statusCode == 200) {
        final directory = await getApplicationDocumentsDirectory();
        final toursDir = Directory('${directory.path}/tours');
        if (!await toursDir.exists()) {
          await toursDir.create(recursive: true);
        }
        
        final zipPath = '${toursDir.path}/${tour['id']}.zip';
        final zipFile = File(zipPath);
        await zipFile.writeAsBytes(response.bodyBytes);
        
        final bytes = await zipFile.readAsBytes();
        final archive = ZipDecoder().decodeBytes(bytes);
        
        final extractPath = '${toursDir.path}/${tour['id']}';
        final extractDir = Directory(extractPath);
        if (await extractDir.exists()) {
          await extractDir.delete(recursive: true);
        }
        await extractDir.create(recursive: true);
        
        for (final file in archive) {
          final filename = file.name;
          if (file.isFile) {
            final data = file.content as List<int>;
            final extractedFile = File('${extractDir.path}/$filename');
            await extractedFile.create(recursive: true);
            await extractedFile.writeAsBytes(data);
          }
        }
        
        await zipFile.delete();
        
        final tours = prefs.getStringList('saved_tours') ?? [];
        tours.add(jsonEncode({
          'id': tour['id'],
          'title': tour['title'],
          'original_request': tour['title'],
          'path': extractPath,
          'created': tour['created'] ?? DateTime.now().toIso8601String(),
          'stops': tour['stops'] ?? '10',
          'lat': lat,
          'lng': lng,
        }));
        await prefs.setStringList('saved_tours', tours);
        
        // Remove from background tours
        final backgroundTours = prefs.getStringList('background_tours') ?? [];
        backgroundTours.removeWhere((bgTour) {
          final bgTourData = jsonDecode(bgTour);
          return bgTourData['id'] == tour['id'];
        });
        await prefs.setStringList('background_tours', backgroundTours);
        
        _loadBackgroundStatus();
        
        // Show success message
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Tour downloaded successfully!'),
              backgroundColor: Colors.green,
            ),
          );
        }
      }
    } catch (error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Download failed: $error'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _generateNews() async {
    String inputText = _tourRequestController.text.trim();
    
    if (inputText.isEmpty) {
      _showError(_contentType == 'Article' ? 'Please enter article text' : 'Please enter newsletter text');
      return;
    }
    
    setState(() {
      _isGenerating = true;
      _progress = _contentType == 'Article' ? 'Starting article generation...' : 'Processing newsletter links...';
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final userId = prefs.getString('user_id') ?? 'anonymous';
      
      if (_contentType == 'Article') {
        // Original article processing
        final response = await http.post(
          Uri.parse('http://$serverIp:5012/generate-news'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'article_text': inputText,
            'request_string': 'News Article',
            'secret_id': userId,
            'major_points_count': int.parse(_stopCountController.text),
          }),
        );

        if (response.statusCode != 200) {
          throw Exception('Failed to start news generation: ${response.body}');
        }

        final result = jsonDecode(response.body);
        final articleId = result['article_id'];
        
        await _pollNewsAndAutoDownload(articleId, serverIp);
        
      } else {
        // Newsletter processing
        await _processNewsletterUrl(userId, serverIp, inputText);
      }
      
    } catch (error) {
      await DebugLogHelper.addDebugLog('NEWS GENERATION ERROR: $error');
      _showError('Failed to generate news: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }
  
  Future<void> _pollNewsAndAutoDownload(String articleId, String serverIp) async {
    const int maxAttempts = 60; // 10 minutes timeout
    int attempts = 0;
    
    Timer.periodic(const Duration(seconds: 10), (timer) async {
      try {
        // Check if news is ready
        final statusResponse = await http.get(
          Uri.parse('http://$serverIp:5012/status/$articleId'),
        );
        
        if (statusResponse.statusCode == 200) {
          final statusData = jsonDecode(statusResponse.body);
          
          setState(() {
            _progress = statusData['status'] ?? 'Processing...';
          });
          
          if (statusData['status'] == 'completed' || statusData['status'] == 'ready') {
            timer.cancel();
            setState(() {
              _progress = 'Downloading article...';
            });
            
            // Auto-download and play
            await _downloadAndSaveNews(articleId, serverIp);
            
          } else if (statusData['status'] == 'error' || statusData['status'] == 'failed') {
            timer.cancel();
            throw Exception(statusData['error'] ?? 'News generation failed');
          } else if (attempts >= maxAttempts) {
            timer.cancel();
            _showError('News generation timed out (10 min limit)');
            setState(() {
              _isGenerating = false;
              _progress = '';
            });
            return;
          }
          
          attempts++;
        }
      } catch (error) {
        timer.cancel();
        await DebugLogHelper.addDebugLog('NEWS POLLING ERROR: $error');
        _showError('Error checking news status: $error');
        setState(() {
          _isGenerating = false;
          _progress = '';
        });
      }
    });
  }
  
  Future<void> _downloadAndSaveNews(String articleId, String serverIp) async {
    try {
      setState(() {
        _progress = 'Downloading article...';
      });
      
      await DebugLogHelper.addDebugLog('NEWS: Starting download for article $articleId from $serverIp:5012');
      
      final response = await http.get(
        Uri.parse('http://$serverIp:5012/download/$articleId'),
      );
      
      await DebugLogHelper.addDebugLog('NEWS: Download response status: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('NEWS: Download response size: ${response.bodyBytes.length} bytes');
      
      if (response.statusCode != 200) {
        throw Exception('Failed to download article');
      }
      
      final directory = await getApplicationDocumentsDirectory();
      final newsDir = Directory('${directory.path}/news');
      if (!await newsDir.exists()) {
        await newsDir.create(recursive: true);
      }
      
      final zipPath = '${newsDir.path}/${articleId}.zip';
      final zipFile = File(zipPath);
      await zipFile.writeAsBytes(response.bodyBytes);
      
      await DebugLogHelper.addDebugLog('NEWS: ZIP file saved to: $zipPath');
      await DebugLogHelper.addDebugLog('NEWS: ZIP file size: ${await zipFile.length()} bytes');
      
      final bytes = await zipFile.readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      
      await DebugLogHelper.addDebugLog('NEWS: ZIP archive contains ${archive.length} files');
      
      final extractPath = '${newsDir.path}/${articleId}';
      final extractDir = Directory(extractPath);
      if (await extractDir.exists()) {
        await extractDir.delete(recursive: true);
        await DebugLogHelper.addDebugLog('NEWS: Deleted existing directory: $extractPath');
      }
      await extractDir.create(recursive: true);
      await DebugLogHelper.addDebugLog('NEWS: Created extract directory: $extractPath');
      
      for (final file in archive) {
        final filename = file.name;
        await DebugLogHelper.addDebugLog('NEWS: Processing archive file: $filename');
        if (file.isFile) {
          final data = file.content as List<int>;
          final extractedFile = File('${extractDir.path}/$filename');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(data);
          await DebugLogHelper.addDebugLog('NEWS: Extracted file: ${extractedFile.path} (${data.length} bytes)');
        }
      }
      
      await zipFile.delete();
      await DebugLogHelper.addDebugLog('NEWS: ZIP file deleted, extraction complete');
      
      // Verify index.html exists
      final indexFile = File('${extractDir.path}/index.html');
      final indexExists = await indexFile.exists();
      await DebugLogHelper.addDebugLog('NEWS: index.html exists: $indexExists');
      if (indexExists) {
        final indexSize = await indexFile.length();
        await DebugLogHelper.addDebugLog('NEWS: index.html size: $indexSize bytes');
      }
      
      await _saveNewsInfo(articleId, extractPath);
      
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      _showSuccess('News article ready!');
      _tourRequestController.clear();
      
      // Auto-navigate to news player (like tours do)
      if (mounted) {
        await DebugLogHelper.addDebugLog('NEWS: Auto-opening news article');
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => NewsPlayerScreen(
              articlePath: extractPath,
              articleTitle: 'News Article',
            ),
          ),
        );
      }
      
    } catch (error) {
      await DebugLogHelper.addDebugLog('NEWS DOWNLOAD ERROR: $error');
      _showError('Failed to download article: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }
  
  Future<void> _saveNewsInfo(String articleId, String path) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final news = prefs.getStringList('saved_news') ?? [];
      
      // Get the actual title from the generated article
      String actualTitle = 'News Article';
      try {
        final indexFile = File('$path/index.html');
        if (await indexFile.exists()) {
          final htmlContent = await indexFile.readAsString();
          final titleMatch = RegExp(r'<title>([^<]+)</title>').firstMatch(htmlContent);
          if (titleMatch != null) {
            actualTitle = titleMatch.group(1) ?? 'News Article';
          }
        }
      } catch (e) {
        await DebugLogHelper.addDebugLog('Error extracting title: $e');
      }
      
      final articleInfo = {
        'id': articleId,
        'title': actualTitle,
        'original_request': actualTitle,
        'path': path,
        'created': DateTime.now().toIso8601String(),
      };
      
      await DebugLogHelper.addDebugLog('NEWS: Saved article info - ID: $articleId, Path: $path');
      
      news.add(jsonEncode(articleInfo));
      await prefs.setStringList('saved_news', news);
      
    } catch (e) {
      print('Error saving news info: $e');
      throw e;
    }
  }

  Future<void> _processNewsletterUrl(String userId, String serverIp, String inputText) async {
    try {
      // Parse multiple URLs from input (one per line)
      final urls = inputText.split('\n')
          .map((url) => url.trim())
          .where((url) => url.isNotEmpty)
          .toList();
      
      if (urls.isEmpty) {
        throw Exception('Please enter at least one newsletter URL');
      }
      
      if (urls.length > 3) {
        throw Exception('Maximum 3 URLs allowed. Please remove extra URLs.');
      }
      
      // Validate URL formats
      for (final url in urls) {
        if (!url.startsWith('http')) {
          throw Exception('Invalid URL: $url\nPlease use URLs starting with http:// or https://');
        }
      }
      
      int successCount = 0;
      int failCount = 0;
      final results = <String>[];
      
      // Process each URL sequentially
      for (int i = 0; i < urls.length; i++) {
        final url = urls[i];
        
        setState(() {
          _progress = 'Processing newsletter ${i + 1} of ${urls.length}: ${url.length > 50 ? url.substring(0, 50) + '...' : url}';
        });
        
        try {
          final response = await http.post(
            Uri.parse('http://$serverIp:5017/process_newsletter'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'newsletter_url': url,
              'user_id': userId,
              'max_articles': 10,
              'max_depth': 2,
              'days_limit': 7,
            }),
          );

          if (response.statusCode == 200) {
            final result = jsonDecode(response.body);
            await DebugLogHelper.addDebugLog('NEWSLETTER RESPONSE: ${response.body}');
            if (result['status'] == 'error') {
              final errorMsg = '❌ ${url}: ${result['message']}';
              results.add(errorMsg);
              await DebugLogHelper.addDebugLog('NEWSLETTER ERROR: $errorMsg');
              failCount++;
            } else {
              final successMsg = '✅ ${url}: ${result['articles_created'] ?? 0} articles queued';
              results.add(successMsg);
              await DebugLogHelper.addDebugLog('NEWSLETTER SUCCESS: $successMsg');
              successCount++;
            }
          } else {
            final httpError = '❌ ${url}: HTTP ${response.statusCode}';
            results.add(httpError);
            await DebugLogHelper.addDebugLog('NEWSLETTER HTTP ERROR: $httpError - ${response.body}');
            failCount++;
          }
        } catch (error) {
          final errorMsg = '❌ ${url}: ${error.toString().split(':').last.trim()}';
          results.add(errorMsg);
          await DebugLogHelper.addDebugLog('NEWSLETTER ERROR: $errorMsg');
          failCount++;
        }
        
        // Small delay between requests to avoid overwhelming the server
        if (i < urls.length - 1) {
          await Future.delayed(const Duration(seconds: 2));
        }
      }
      
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      // Show comprehensive results
      final summary = '$successCount successful, $failCount failed';
      _showSuccess('Newsletter processing complete: $summary');
      _tourRequestController.clear();
      
      // Show detailed results dialog
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('📰 Processing Results ($summary)'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Newsletter Processing Summary:\n',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                ...results.map((result) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    result,
                    style: const TextStyle(fontSize: 12),
                  ),
                )),
                if (successCount > 0) ...[
                  const SizedBox(height: 16),
                  const Text(
                    '✨ Successful newsletters are being processed in the background. Check the Home page for articles to download!',
                    style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold),
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Done'),
            ),
          ],
        ),
      );
      
    } catch (error) {
      await DebugLogHelper.addDebugLog('NEWSLETTER URL PROCESSING ERROR: $error');
      throw error;
    }
  }



  @override
  void dispose() {
    _tourRequestController.dispose();
    _stopCountController.dispose();
    super.dispose();
  }
}