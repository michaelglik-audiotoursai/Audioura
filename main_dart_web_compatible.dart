import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:async';
import 'dart:html' as html;

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
              _progress = 'Tour ready! Preparing download...';
            });
            
            // Auto-download for web
            await _downloadTourForWeb(jobId, location);
            
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

  Future<void> _downloadTourForWeb(String jobId, String location) async {
    try {
      // Get download URL
      final downloadUrl = '$_apiBaseUrl/download/$jobId';
      
      // Save tour info to local storage
      await _saveTourInfo(jobId, location, downloadUrl);
      
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
      
      // Show success with download options
      _showDownloadOptions(jobId, location, downloadUrl);
      
    } catch (error) {
      _showError('Failed to prepare tour: $error');
      setState(() {
        _isGenerating = false;
        _progress = '';
      });
    }
  }

  void _showDownloadOptions(String jobId, String location, String downloadUrl) {
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
              const Text('Choose an option:'),
              const SizedBox(height: 8),
              ElevatedButton.icon(
                onPressed: () {
                  Navigator.of(context).pop();
                  _downloadZipFile(downloadUrl, location);
                },
                icon: const Icon(Icons.download),
                label: const Text('Download ZIP File'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF3498db),
                  foregroundColor: Colors.white,
                ),
              ),
              const SizedBox(height: 8),
              ElevatedButton.icon(
                onPressed: () {
                  Navigator.of(context).pop();
                  _openTourInNewTab(downloadUrl);
                },
                icon: const Icon(Icons.open_in_new),
                label: const Text('Open Tour in New Tab'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF27ae60),
                  foregroundColor: Colors.white,
                ),
              ),
              const SizedBox(height: 8),
              ElevatedButton.icon(
                onPressed: () {
                  Navigator.of(context).pop();
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => TourPlayerScreen(
                        tourUrl: downloadUrl,
                        tourTitle: location,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.play_arrow),
                label: const Text('Play Tour Here'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFe74c3c),
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Close'),
            ),
          ],
        );
      },
    );
  }

  void _downloadZipFile(String url, String filename) {
    final anchor = html.AnchorElement(href: url)
      ..setAttribute('download', '${filename.replaceAll(' ', '_')}_tour.zip')
      ..click();
  }

  void _openTourInNewTab(String url) {
    html.window.open(url, '_blank');
  }

  Future<void> _saveTourInfo(String jobId, String location, String url) async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];
    
    final tourInfo = jsonEncode({
      'id': jobId,
      'title': location,
      'url': url,
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
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.download),
                          onPressed: () {
                            final anchor = html.AnchorElement(href: tour['url'])
                              ..setAttribute('download', '${tour['title'].replaceAll(' ', '_')}_tour.zip')
                              ..click();
                          },
                        ),
                        IconButton(
                          icon: const Icon(Icons.play_arrow),
                          onPressed: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => TourPlayerScreen(
                                  tourUrl: tour['url'],
                                  tourTitle: tour['title'],
                                ),
                              ),
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}

class TourPlayerScreen extends StatefulWidget {
  final String tourUrl;
  final String tourTitle;

  const TourPlayerScreen({
    super.key,
    required this.tourUrl,
    required this.tourTitle,
  });

  @override
  State<TourPlayerScreen> createState() => _TourPlayerScreenState();
}

class _TourPlayerScreenState extends State<TourPlayerScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.tourTitle),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.download),
            onPressed: () {
              final anchor = html.AnchorElement(href: widget.tourUrl)
                ..setAttribute('download', '${widget.tourTitle.replaceAll(' ', '_')}_tour.zip')
                ..click();
            },
          ),
          IconButton(
            icon: const Icon(Icons.open_in_new),
            onPressed: () {
              html.window.open(widget.tourUrl, '_blank');
            },
          ),
        ],
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.tour,
              size: 100,
              color: Color(0xFF3498db),
            ),
            const SizedBox(height: 20),
            Text(
              widget.tourTitle,
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Color(0xFF2c3e50),
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 30),
            ElevatedButton.icon(
              onPressed: () {
                final anchor = html.AnchorElement(href: widget.tourUrl)
                  ..setAttribute('download', '${widget.tourTitle.replaceAll(' ', '_')}_tour.zip')
                  ..click();
              },
              icon: const Icon(Icons.download),
              label: const Text('Download Tour'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF3498db),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15),
              ),
            ),
            const SizedBox(height: 15),
            ElevatedButton.icon(
              onPressed: () {
                html.window.open(widget.tourUrl, '_blank');
              },
              icon: const Icon(Icons.open_in_new),
              label: const Text('Open in New Tab'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF27ae60),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15),
              ),
            ),
          ],
        ),
      ),
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