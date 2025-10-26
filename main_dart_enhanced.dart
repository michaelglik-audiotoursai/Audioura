import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:async';
import 'dart:io';

void main() {
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
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
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

  Future<void> _generateTour() async {
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
      
      // Step 2: Poll for completion and auto-download
      await _pollAndDownloadTour(jobId, tourData['location']);
      
    } catch (error) {
      print('DETAILED ERROR: $error');
      _showError('Failed to generate tour: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _pollAndDownloadTour(String jobId, String location) async {
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
            
            // Auto-download and extract
            await _downloadAndExtractTour(jobId, location);
            
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

  Future<void> _downloadAndExtractTour(String jobId, String location) async {
    try {
      // Step 1: Download ZIP file
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
      
      // Step 3: Save ZIP file
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
      
      // Step 7: Navigate to tour
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      _showSuccess('Tour downloaded and ready to play!');
      
      // Auto-navigate to the tour
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
        duration: const Duration(seconds: 5),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎵 Audio Tour Generator'),
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
              'Example: "Auto museum, brookline, ma"',
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
            ElevatedButton(
              onPressed: _isGenerating ? null : _generateTour,
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
                      '🎯 Generate & Download Tour',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
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
          onProgress: (int progress) {
            // Update loading progress
          },
          onPageStarted: (String url) {},
          onPageFinished: (String url) {},
        ),
      );
    
    // Load the tour HTML file
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
          // Future: Add voice commands here
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