import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:async';

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
      
      // Step 2: Poll for completion
      await _pollForCompletion(jobId, tourData['location']);
      
    } catch (error) {
      print('DETAILED ERROR: $error');
      _showError('Failed to generate tour: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  Future<void> _pollForCompletion(String jobId, String location) async {
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
            
            // Save tour info and show success
            await _saveTourInfo(jobId, location);
            
            setState(() {
              _isGenerating = false;
              _progress = '';
            });
            
            _showTourReady(jobId, location);
            
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

  void _showTourReady(String jobId, String location) {
    final downloadUrl = '$_apiBaseUrl/download/$jobId';
    
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('🎉 Tour Ready!'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Your tour "$location" is ready!'),
              const SizedBox(height: 16),
              const Text('Download URL:'),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.grey.shade100,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: SelectableText(
                  downloadUrl,
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                'Copy this URL to your browser to download the tour ZIP file.',
                style: TextStyle(fontSize: 14, color: Colors.grey),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.of(context).pop();
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => TourDetailsScreen(
                      tourTitle: location,
                      downloadUrl: downloadUrl,
                    ),
                  ),
                );
              },
              child: const Text('View Tour'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _saveTourInfo(String jobId, String location) async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];
    
    final tourInfo = jsonEncode({
      'id': jobId,
      'title': location,
      'downloadUrl': '$_apiBaseUrl/download/$jobId',
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
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: const Column(
                children: [
                  Icon(Icons.phone_android, size: 40, color: Colors.green),
                  SizedBox(height: 10),
                  Text(
                    'Native Android App',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                      color: Colors.green,
                    ),
                  ),
                  SizedBox(height: 5),
                  Text(
                    'Generate tours and get download links for offline access!',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.green),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 30),
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
                      '🎯 Generate Audio Tour',
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
                    trailing: const Icon(Icons.arrow_forward),
                    onTap: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => TourDetailsScreen(
                            tourTitle: tour['title'],
                            downloadUrl: tour['downloadUrl'],
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

class TourDetailsScreen extends StatelessWidget {
  final String tourTitle;
  final String downloadUrl;

  const TourDetailsScreen({
    super.key,
    required this.tourTitle,
    required this.downloadUrl,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(tourTitle),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Icon(
              Icons.tour,
              size: 100,
              color: Color(0xFF3498db),
            ),
            const SizedBox(height: 20),
            Text(
              tourTitle,
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2c3e50),
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 30),
            const Text(
              'Download URL:',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.grey.shade300),
              ),
              child: SelectableText(
                downloadUrl,
                style: const TextStyle(fontSize: 14),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Instructions:',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 10),
            const Text(
              '1. Copy the URL above\n'
              '2. Open your browser\n'
              '3. Paste the URL to download the tour ZIP file\n'
              '4. Extract the ZIP file\n'
              '5. Open index.html to play the tour',
              style: TextStyle(fontSize: 14, height: 1.5),
            ),
            const SizedBox(height: 30),
            ElevatedButton.icon(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('URL copied: $downloadUrl'),
                    duration: const Duration(seconds: 3),
                  ),
                );
              },
              icon: const Icon(Icons.copy),
              label: const Text('Copy Download URL'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF3498db),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
            ),
          ],
        ),
      ),
    );
  }
}