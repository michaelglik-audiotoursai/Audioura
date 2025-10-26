// Add this to the end of main_dart_with_background.dart

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
  List<Map<String, dynamic>> _pendingTours = [];

  @override
  void initState() {
    super.initState();
    _loadBackgroundTours();
  }

  Future<void> _loadBackgroundTours() async {
    final prefs = await SharedPreferences.getInstance();
    final readyTours = prefs.getStringList('background_tours') ?? [];
    final pendingTours = prefs.getStringList('pending_background_tours') ?? [];
    
    setState(() {
      _backgroundTours = readyTours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
      _pendingTours = pendingTours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList();
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
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadBackgroundTours,
          ),
        ],
      ),
      body: Column(
        children: [
          if (_pendingTours.isNotEmpty) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              color: Colors.orange.shade50,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '⏳ Generating in Background',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Colors.orange,
                    ),
                  ),
                  const SizedBox(height: 8),
                  ..._pendingTours.map((tour) => Text(
                    '• ${tour['location']}',
                    style: const TextStyle(color: Colors.orange),
                  )),
                ],
              ),
            ),
          ],
          Expanded(
            child: _backgroundTours.isEmpty
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
          ),
        ],
      ),
    );
  }
}