import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:workmanager/workmanager.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'dart:convert';
import 'dart:async';
import 'dart:io';

// Background task callback
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    try {
      final jobId = inputData?['jobId'] as String?;
      final location = inputData?['location'] as String?;
      final apiBaseUrl = inputData?['apiBaseUrl'] as String?;
      
      if (jobId != null && location != null && apiBaseUrl != null) {
        await _checkTourStatus(jobId, location, apiBaseUrl);
      }
      return Future.value(true);
    } catch (e) {
      print('Background task error: $e');
      return Future.value(false);
    }
  });
}

Future<void> _checkTourStatus(String jobId, String location, String apiBaseUrl) async {
  try {
    final response = await http.get(Uri.parse('$apiBaseUrl/status/$jobId'));
    
    if (response.statusCode == 200) {
      final status = jsonDecode(response.body);
      
      if (status['status'] == 'completed') {
        // Show notification
        await _showTourReadyNotification(location, jobId);
        
        // Save as background completed tour
        final prefs = await SharedPreferences.getInstance();
        final backgroundTours = prefs.getStringList('background_tours') ?? [];
        backgroundTours.add(jsonEncode({
          'id': jobId,
          'title': location,
          'downloadUrl': '$apiBaseUrl/download/$jobId',
          'created': DateTime.now().toIso8601String(),
          'status': 'ready'
        }));
        await prefs.setStringList('background_tours', backgroundTours);
      }
    }
  } catch (e) {
    print('Error checking tour status: $e');
  }
}

Future<void> _showTourReadyNotification(String location, String jobId) async {
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
    jobId.hashCode,
    '🎵 Tour Ready!',
    'Your tour "$location" is ready to download and play!',
    notificationDetails,
  );
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Workmanager().initialize(callbackDispatcher, isInDebugMode: false);
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

class _MainScreenState extends State<MainScreen> {
  int _selectedIndex = 0;

  final List<Widget> _screens = [
    const TourGeneratorScreen(),
    const MyToursScreen(),
    const BackgroundToursScreen(),
    const AboutScreen(),
  ];

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
        Uri.parse('$_apiBaseUrl/generate-complete-tour'),
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
      print('DETAILED ERROR: $error');
      _showError('Failed to generate tour: $error');
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
      
      // Start tour generation
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
      
      // Show notification permission dialog
      _showNotificationPermissionDialog(jobId, tourData['location']);
      
    } catch (error) {
      _showError('Failed to start background generation: $error');
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
              Text('Your tour "$location" is being generated in the background.'),
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
    // Request notification permission
    final status = await Permission.notification.request();
    
    if (status.isGranted) {
      // Start background monitoring
      await Workmanager().registerPeriodicTask(
        jobId,
        'checkTourStatus',
        inputData: {
          'jobId': jobId,
          'location': location,
          'apiBaseUrl': _apiBaseUrl,
        },
        frequency: const Duration(minutes: 15),
      );
      
      _showSuccess('Background generation started! You\'ll be notified when ready.');
      
      // Clear the input
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
      setState(() {
        _progress = 'Downloading tour files...';
      });
      
      final response = await http.get(
        Uri.parse('$_apiBaseUrl/download/$jobId'),
      );
      
      if (response.statusCode != 200) {
        throw Exception('Failed to download tour');
      }
      
      final directory = await getApplicationDocumentsDirectory();
      final toursDir = Directory('${directory.path}/tours');
      if (!await toursDir.exists()) {
        await toursDir.create(recursive: true);
      }
      
      setState(() {
        _progress = 'Extracting tour files...';
      });
      
      final zipPath = '${toursDir.path}/${jobId}.zip';
      final zipFile = File(zipPath);
      await zipFile.writeAsBytes(response.bodyBytes);
      
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
      _showError('Failed to download tour: $error');
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
    print('ERROR: $message');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Colors.red,
        duration: const Duration(seconds: 10),
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

class MyToursScreen extends StatefulWidget {
  const MyToursScreen({super.key});

  @override
  State<MyToursScreen> createState() => _MyToursScreenState();
}

class _MyToursScreenState extends State<MyToursScreen> {
  List<Map<String, dynamic>> _tours = [];

  @override
  void initState() {
    super.initState();
    _loadTours();
  }

  Future<void> _loadTours() async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];
    
    setState(() {
      _tours = tours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎵 My Tours'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _tours.isEmpty
          ? const Center(
              child: Text(
                'No tours yet.\nGenerate your first tour!',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            )
          : ListView.builder(
              itemCount: _tours.length,
              itemBuilder: (context, index) {
                final tour = _tours[index];
                
                return Card(
                  margin: const EdgeInsets.all(8),
                  child: ListTile(
                    leading: const Icon(Icons.tour, color: Color(0xFF3498db)),
                    title: Text(tour['title']),
                    subtitle: Text('Created: ${DateTime.parse(tour['created']).toLocal().toString().split('.')[0]}'),
                    trailing: const Icon(Icons.play_arrow),
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => TourPlayerScreen(
                            tourPath: tour['path'],
                            tourTitle: tour['title'],
                          ),
                        ),
                      );
                    },
                  ),
                );
              },
            ),
    );
  }
}

class BackgroundToursScreen extends StatefulWidget {
  const BackgroundToursScreen({super.key});

  @override
  State<BackgroundToursScreen> createState() => _BackgroundToursScreenState();
}

class _BackgroundToursScreenState extends State<BackgroundToursScreen> {
  List<Map<String, dynamic>> _backgroundTours = [];

  @override
  void initState() {
    super.initState();
    _loadBackgroundTours();
  }

  Future<void> _loadBackgroundTours() async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('background_tours') ?? [];
    
    setState(() {
      _backgroundTours = tours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
    });
  }

  Future<void> _downloadBackgroundTour(Map<String, dynamic> tour) async {
    try {
      final response = await http.get(Uri.parse(tour['downloadUrl']));
      
      if (response.statusCode != 200) {
        throw Exception('Failed to download tour');
      }
      
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
      
      // Save to regular tours
      final prefs = await SharedPreferences.getInstance();
      final tours = prefs.getStringList('saved_tours') ?? [];
      tours.add(jsonEncode({
        'id': tour['id'],
        'title': tour['title'],
        'path': extractPath,
        'created': tour['created'],
      }));
      await prefs.setStringList('saved_tours', tours);
      
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Tour downloaded successfully!'),
          backgroundColor: Colors.green,
        ),
      );
      
      // Navigate to tour
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => TourPlayerScreen(
            tourPath: extractPath,
            tourTitle: tour['title'],
          ),
        ),
      );
      
    } catch (error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to download: $error'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔔 Background Tours'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _backgroundTours.isEmpty
          ? const Center(
              child: Text(
                'No background tours yet.\nUse "Generate in Background" to get started!',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            )
          : ListView.builder(
              itemCount: _backgroundTours.length,
              itemBuilder: (context, index) {
                final tour = _backgroundTours[index];
                
                return Card(
                  margin: const EdgeInsets.all(8),
                  child: ListTile(
                    leading: const Icon(Icons.notifications_active, color: Color(0xFF27ae60)),
                    title: Text(tour['title']),
                    subtitle: Text('Ready: ${DateTime.parse(tour['created']).toLocal().toString().split('.')[0]}'),
                    trailing: ElevatedButton(
                      onPressed: () => _downloadBackgroundTour(tour),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF27ae60),
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('Download & Play'),
                    ),
                  ),
                );
              },
            ),
    );
  }
}

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

class _TourPlayerScreenState extends State<TourPlayerScreen> {
  late WebViewController _controller;

  @override
  void initState() {
    super.initState();
    _initializeWebView();
  }

  void _initializeWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(
        NavigationDelegate(
          onProgress: (int progress) {},
          onPageStarted: (String url) {},
          onPageFinished: (String url) {},
        ),
      );
    
    final htmlFile = File('${widget.tourPath}/index.html');
    if (htmlFile.existsSync()) {
      _controller.loadFile(htmlFile.path);
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
            onPressed: () => _controller.reload(),
          ),
        ],
      ),
      body: WebViewWidget(controller: _controller),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Voice commands coming soon!'),
              duration: Duration(seconds: 2),
            ),
          );
        },
        backgroundColor: const Color(0xFF3498db),
        child: const Icon(Icons.mic, color: Colors.white),
      ),
    );
  }
}

class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key});

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  String _appVersion = 'Loading...';
  String _buildNumber = 'Loading...';
  String _userId = 'Loading...';
  String _deviceModel = 'Loading...';
  String _androidVersion = 'Loading...';

  @override
  void initState() {
    super.initState();
    _loadAppInfo();
  }

  Future<void> _loadAppInfo() async {
    try {
      // Get package info
      final packageInfo = await PackageInfo.fromPlatform();
      
      // Get device info
      final deviceInfo = DeviceInfoPlugin();
      final androidInfo = await deviceInfo.androidInfo;
      
      // Generate User ID from device info
      final userId = _generateUserId(androidInfo);
      
      setState(() {
        _appVersion = packageInfo.version;
        _buildNumber = packageInfo.buildNumber;
        _userId = userId;
        _deviceModel = '${androidInfo.brand} ${androidInfo.model}';
        _androidVersion = 'Android ${androidInfo.version.release}';
      });
    } catch (e) {
      setState(() {
        _appVersion = 'Error loading';
        _buildNumber = 'Error loading';
        _userId = 'Error loading';
        _deviceModel = 'Error loading';
        _androidVersion = 'Error loading';
      });
    }
  }

  String _generateUserId(AndroidDeviceInfo androidInfo) {
    // Generate a consistent User ID based on device characteristics
    final deviceId = '${androidInfo.brand}-${androidInfo.model}-${androidInfo.id}'.hashCode.abs();
    return 'USER-${deviceId.toString().padLeft(8, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ℹ️ About'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // App Info Section
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.blue.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.apps, size: 30, color: Colors.blue),
                      SizedBox(width: 10),
                      Text(
                        'Audio Tour Generator',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.blue,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  _buildInfoRow('Version', _appVersion),
                  _buildInfoRow('Build', _buildNumber),
                  _buildInfoRow('User ID', _userId),
                ],
              ),
            ),
            const SizedBox(height: 20),
            
            // Device Info Section
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.phone_android, size: 30, color: Colors.green),
                      SizedBox(width: 10),
                      Text(
                        'Device Information',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.green,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  _buildInfoRow('Device', _deviceModel),
                  _buildInfoRow('OS', _androidVersion),
                ],
              ),
            ),
            const SizedBox(height: 20),
            
            // Features Section
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.star, size: 30, color: Colors.orange),
                      SizedBox(width: 10),
                      Text(
                        'Features',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.orange,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 15),
                  Text(
                    '• AI-powered tour generation\n'
                    '• Background generation with notifications\n'
                    '• Automatic download and extraction\n'
                    '• Native audio playback\n'
                    '• Offline tour storage\n'
                    '• Voice command support (coming soon)',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.orange,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
            const Spacer(),
            
            // Footer
            Center(
              child: Text(
                '© 2024 Audio Tour Generator\nPowered by AI',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.shade600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(
              '$label:',
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 14,
                fontFamily: 'monospace',
              ),
            ),
          ),
        ],
      ),
    );
  }
}