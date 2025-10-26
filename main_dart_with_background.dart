import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'dart:convert';
import 'dart:async';
import 'dart:io';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AudioTourApp());
}

class AudioTourApp extends StatelessWidget {
  const AudioTourApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Audio Tour Generator',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const MainScreen(),
    );
  }
}

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> with WidgetsBindingObserver {
  int _selectedIndex = 0;
  Timer? _backgroundTimer;

  final List<Widget> _screens = [
    const TourGeneratorScreen(),
    const MyToursScreen(),
    const BackgroundToursScreen(),
    const AboutScreen(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _startBackgroundMonitoring();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _backgroundTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _startBackgroundMonitoring();
    } else if (state == AppLifecycleState.paused) {
      // Keep monitoring in background
    }
  }

  void _startBackgroundMonitoring() {
    _backgroundTimer?.cancel();
    _backgroundTimer = Timer.periodic(const Duration(minutes: 2), (timer) async {
      await _checkBackgroundTours();
    });
  }

  Future<void> _checkBackgroundTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
      
      for (String tourJson in List.from(pendingTours)) {
        final tour = jsonDecode(tourJson);
        final jobId = tour['jobId'];
        final location = tour['location'];
        final apiBaseUrl = tour['apiBaseUrl'];
        
        final response = await http.get(Uri.parse('$apiBaseUrl/status/$jobId'));
        
        if (response.statusCode == 200) {
          final status = jsonDecode(response.body);
          
          if (status['status'] == 'completed') {
            // Remove from pending
            pendingTours.remove(tourJson);
            await prefs.setStringList('pending_background_tours', pendingTours);
            
            // Add to ready tours
            final readyTours = prefs.getStringList('background_tours') ?? [];
            readyTours.add(jsonEncode({
              'id': jobId,
              'title': location,
              'downloadUrl': '$apiBaseUrl/download/$jobId',
              'created': DateTime.now().toIso8601String(),
              'status': 'ready'
            }));
            await prefs.setStringList('background_tours', readyTours);
            
            // Show notification
            await _showTourReadyNotification(location);
          }
        }
      }
    } catch (e) {
      print('Background check error: $e');
    }
  }

  Future<void> _showTourReadyNotification(String location) async {
    final FlutterLocalNotificationsPlugin notifications = FlutterLocalNotificationsPlugin();
    
    const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      'tour_ready_channel',
      'Tour Ready Notifications',
      channelDescription: 'Notifications when tours are ready',
      importance: Importance.high,
      priority: Priority.high,
    );
    
    const NotificationDetails notificationDetails = NotificationDetails(android: androidDetails);
    
    await notifications.show(
      DateTime.now().millisecondsSinceEpoch ~/ 1000,
      '🎵 Tour Ready!',
      'Your tour "$location" is ready to download and play!',
      notificationDetails,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: _selectedIndex,
        onTap: (index) => setState(() => _selectedIndex = index),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.add),
            label: 'Generate Tour',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.library_music),
            label: 'My Tours',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.notifications),
            label: 'Background',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.info),
            label: 'About',
          ),
        ],
      ),
    );
  }
}

class TourGeneratorScreen extends StatefulWidget {
  const TourGeneratorScreen({super.key});

  @override
  State<TourGeneratorScreen> createState() => _TourGeneratorScreenState();
}

class _TourGeneratorScreenState extends State<TourGeneratorScreen> {
  final TextEditingController _tourRequestController = TextEditingController();
  bool _isGenerating = false;
  String _progress = '';
  String _apiBaseUrl = 'http://192.168.0.217:5002';
  final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();

  @override
  void initState() {
    super.initState();
    _initializeNotifications();
  }

  Future<void> _initializeNotifications() async {
    const AndroidInitializationSettings androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const InitializationSettings settings = InitializationSettings(android: androidSettings);
    await _notifications.initialize(settings);
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
      'total_stops': 10,
    };
  }

  Future<void> _generateTourForeground() async {
    if (_tourRequestController.text.trim().isEmpty) {
      _showError('Please enter a tour request');
      return;
    }

    setState(() {
      _isGenerating = true;
      _progress = 'Starting tour generation...';
    });

    try {
      Map<String, dynamic> tourData = _parseTourRequest(_tourRequestController.text);
      
      final response = await http.post(
        Uri.parse('\$_apiBaseUrl/generate-complete-tour'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(tourData),
      );

      if (response.statusCode != 200) {
        throw Exception('Failed to start tour generation');
      }

      Map<String, dynamic> result = jsonDecode(response.body);
      String jobId = result['job_id'];
      
      await _pollAndAutoDownload(jobId, tourData['location']);
      
    } catch (error) {
      print('DETAILED ERROR: \$error');
      _showError('Failed to generate tour: \$error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _generateTourBackground() async {
    if (_tourRequestController.text.trim().isEmpty) {
      _showError('Please enter a tour request');
      return;
    }

    try {
      Map<String, dynamic> tourData = _parseTourRequest(_tourRequestController.text);
      
      final response = await http.post(
        Uri.parse('\$_apiBaseUrl/generate-complete-tour'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(tourData),
      );

      if (response.statusCode != 200) {
        throw Exception('Failed to start tour generation');
      }

      Map<String, dynamic> result = jsonDecode(response.body);
      String jobId = result['job_id'];
      
      _showNotificationPermissionDialog(jobId, tourData['location']);
      
    } catch (error) {
      _showError('Failed to start background generation: \$error');
    }
  }

  void _showNotificationPermissionDialog(String jobId, String location) {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('🔔 Background Generation Started'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Your tour "\$location" is being generated in the background.'),
              const SizedBox(height: 16),
              const Text('Would you like to be notified when it\'s ready?'),
              const SizedBox(height: 8),
              const Text(
                'This requires notification permission.',
                style: TextStyle(fontSize: 12, color: Colors.grey),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('No Thanks'),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.of(context).pop();
                await _requestNotificationPermissionAndStartBackground(jobId, location);
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF3498db),
                foregroundColor: Colors.white,
              ),
              child: const Text('Get Notified'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _requestNotificationPermissionAndStartBackground(String jobId, String location) async {
    final status = await Permission.notification.request();
    
    if (status.isGranted) {
      // Add to pending background tours
      final prefs = await SharedPreferences.getInstance();
      final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
      pendingTours.add(jsonEncode({
        'jobId': jobId,
        'location': location,
        'apiBaseUrl': _apiBaseUrl,
        'startTime': DateTime.now().toIso8601String(),
      }));
      await prefs.setStringList('pending_background_tours', pendingTours);
      
      _showSuccess('Background generation started! You\'ll be notified when ready.');
      _tourRequestController.clear();
      
    } else {
      _showError('Notification permission denied. You won\'t be notified when the tour is ready.');
    }
  }

  Future<void> _pollAndAutoDownload(String jobId, String location) async {
    const int maxAttempts = 60;
    int attempts = 0;
    
    Timer.periodic(const Duration(seconds: 10), (timer) async {
      try {
        final response = await http.get(
          Uri.parse('\$_apiBaseUrl/status/\$jobId'),
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
            
            await _autoDownloadAndPlay(jobId, location);
            
          } else if (status['status'] == 'error') {
            timer.cancel();
            throw Exception(status['error'] ?? 'Tour generation failed');
          } else if (attempts >= maxAttempts) {
            timer.cancel();
            throw Exception('Tour generation timed out');
          }
          
          attempts++;
        }
      } catch (error) {
        timer.cancel();
        _showError('Error: \$error');
        setState(() {
          _isGenerating = false;
          _progress = '';
        });
      }
    });
  }

  Future<void> _autoDownloadAndPlay(String jobId, String location) async {
    try {
      setState(() {
        _progress = 'Downloading tour files...';
      });
      
      final response = await http.get(
        Uri.parse('\$_apiBaseUrl/download/\$jobId'),
      );
      
      if (response.statusCode != 200) {
        throw Exception('Failed to download tour');
      }
      
      final directory = await getApplicationDocumentsDirectory();
      final toursDir = Directory('\${directory.path}/tours');
      if (!await toursDir.exists()) {
        await toursDir.create(recursive: true);
      }
      
      setState(() {
        _progress = 'Extracting tour files...';
      });
      
      final zipPath = '\${toursDir.path}/\$jobId.zip';
      final zipFile = File(zipPath);
      await zipFile.writeAsBytes(response.bodyBytes);
      
      final bytes = await zipFile.readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      
      final extractPath = '\${toursDir.path}/\$jobId';
      final extractDir = Directory(extractPath);
      if (await extractDir.exists()) {
        await extractDir.delete(recursive: true);
      }
      await extractDir.create(recursive: true);
      
      for (final file in archive) {
        final filename = file.name;
        if (file.isFile) {
          final data = file.content as List<int>;
          final extractedFile = File('\${extractDir.path}/\$filename');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(data);
        }
      }
      
      await zipFile.delete();
      await _saveTourInfo(jobId, location, extractPath);
      
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      _showSuccess('Tour ready! Opening now...');
      
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
      _showError('Failed to download tour: \$error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _saveTourInfo(String jobId, String location, String path) async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];
    
    final tourInfo = jsonEncode({
      'id': jobId,
      'title': location,
      'path': path,
      'created': DateTime.now().toIso8601String(),
    });
    
    tours.add(tourInfo);
    await prefs.setStringList('saved_tours', tours);
  }

  void _showError(String message) {
    print('ERROR: \$message');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.red,
        duration: const Duration(seconds: 10),
      ),
    );
  }

  void _showSuccess(String message) {
    print('SUCCESS: \$message');
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
        title: const Text('🎵 Generate My Custom Tour'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'What tour would you like?',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2c3e50),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Example: "Durant-Kenrick House and Grounds, Newton ma"',
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey,
                fontStyle: FontStyle.italic,
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _tourRequestController,
              maxLines: 3,
              enabled: !_isGenerating,
              decoration: const InputDecoration(
                hintText: 'Describe your desired tour...',
                border: OutlineInputBorder(),
                filled: true,
                fillColor: Colors.white,
              ),
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: ElevatedButton(
                    onPressed: _isGenerating ? null : _generateTourForeground,
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
                    onPressed: _isGenerating ? null : _generateTourBackground,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF27ae60),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: const Text(
                      '🔔 Generate in Background',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
              ],
            ),
            if (_progress.isNotEmpty) ..[
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
            const SizedBox(height: 30),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: const Column(
                children: [
                  Icon(Icons.info_outline, size: 40, color: Colors.orange),
                  SizedBox(height: 10),
                  Text(
                    'Generation Options',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: Colors.orange,
                    ),
                  ),
                  SizedBox(height: 10),
                  Text(
                    '• Generate Now: Wait and play immediately\n'
                    '• Generate in Background: Get notified when ready',
                    textAlign: TextAlign.left,
                    style: TextStyle(color: Colors.orange),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _tourRequestController.dispose();
    super.dispose();
  }
}

// Add remaining screens here - MyTours, Background, About, TourPlayer
// (Content from remaining_screens.dart and About/TourPlayer from auto_download version)