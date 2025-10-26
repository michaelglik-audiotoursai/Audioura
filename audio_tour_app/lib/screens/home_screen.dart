import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:math';
import '../screens/debug_log_viewer_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  MapController _mapController = MapController();
  LatLng? _userLocation;
  LatLng? _displayLocation; // Location being displayed (may differ from user location)
  List<Marker> _tourMarkers = [];
  bool _isLoading = true;
  String _appMode = 'Tours';
  bool _isUsingCustomLocation = false;
  String _customLocationName = '';
  List<Map<String, dynamic>> _locationHistory = [];
  List<Map<String, dynamic>> _newsletters = [];
  String _selectedTypeFilter = 'All';
  final List<String> _articleTypes = [
    'All',
    'News and Politics',
    'Business and Investment', 
    'Technology',
    'Lifestyle and Entertainment',
    'Education and Learning',
    'Others'
  ];

  @override
  void initState() {
    super.initState();
    _loadAppMode();
  }
  
  Future<void> _loadAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('app_mode') ?? 'Tours';
    await _loadLocationHistory();
    await _loadCustomLocation();
    
    setState(() {
      _appMode = mode;
    });
    
    if (_appMode == 'Audio') {
      await _loadNewsletters();
    } else {
      await _initializeMap();
    }
  }
  
  Future<void> _loadCustomLocation() async {
    final prefs = await SharedPreferences.getInstance();
    final customLat = prefs.getDouble('custom_location_lat');
    final customLng = prefs.getDouble('custom_location_lng');
    final customName = prefs.getString('custom_location_name');
    
    if (customLat != null && customLng != null && customName != null) {
      setState(() {
        _displayLocation = LatLng(customLat, customLng);
        _isUsingCustomLocation = true;
        _customLocationName = customName;
      });
    }
  }
  
  Future<void> _saveCustomLocation() async {
    final prefs = await SharedPreferences.getInstance();
    if (_isUsingCustomLocation && _displayLocation != null) {
      await prefs.setDouble('custom_location_lat', _displayLocation!.latitude);
      await prefs.setDouble('custom_location_lng', _displayLocation!.longitude);
      await prefs.setString('custom_location_name', _customLocationName);
    } else {
      await prefs.remove('custom_location_lat');
      await prefs.remove('custom_location_lng');
      await prefs.remove('custom_location_name');
    }
  }
  
  Future<void> _loadLocationHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final historyJson = prefs.getStringList('location_history') ?? [];
    _locationHistory = historyJson.map((item) => json.decode(item) as Map<String, dynamic>).toList();
  }
  
  Future<void> _saveLocationHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final historyJson = _locationHistory.map((item) => json.encode(item)).toList();
    await prefs.setStringList('location_history', historyJson);
  }
  
  Future<LatLng?> _geocodeLocation(String query) async {
    try {
      // Simple geocoding using OpenStreetMap Nominatim API
      final encodedQuery = Uri.encodeComponent(query);
      final response = await http.get(
        Uri.parse('https://nominatim.openstreetmap.org/search?q=$encodedQuery&format=json&limit=1'),
        headers: {'User-Agent': 'AudioTours/1.0'},
      ).timeout(Duration(seconds: 10));
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as List;
        if (data.isNotEmpty) {
          final result = data[0];
          final lat = double.parse(result['lat']);
          final lon = double.parse(result['lon']);
          return LatLng(lat, lon);
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Geocoding error: $e');
    }
    return null;
  }

  Future<void> _initializeMap() async {
    await DebugLogHelper.addDebugLog('HOME: Starting map initialization');
    
    // Load cached tours first
    await _loadCachedTours();
    
    await _getCurrentLocation();
    await _loadNearbyTours();
    
    setState(() {
      _isLoading = false;
    });
    
    await DebugLogHelper.addDebugLog('HOME: Map initialization completed');
  }

  Future<void> _getCurrentLocation() async {
    try {
      await DebugLogHelper.addDebugLog('HOME: Requesting location permission');
      
      var permission = await Permission.location.request();
      if (permission != PermissionStatus.granted) {
        await DebugLogHelper.addDebugLog('HOME: Location permission denied');
        setState(() {
          _userLocation = LatLng(42.3601, -71.0589);
        });
        return;
      }

      await DebugLogHelper.addDebugLog('HOME: Getting current position');
      Position? position;
      try {
        position = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high,
        );
      } catch (e) {
        await DebugLogHelper.addDebugLog('HOME: Geolocator error: $e');
        throw e;
      }

      if (position != null) {
        if (mounted) {
          setState(() {
            _userLocation = LatLng(position!.latitude, position.longitude);
          });
        }

        await DebugLogHelper.addDebugLog('HOME: User location: ${position.latitude}, ${position.longitude}');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Position is null, using default location');
        if (mounted) {
          setState(() {
            _userLocation = LatLng(42.3601, -71.0589);
          });
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error getting location: $e');
      setState(() {
        _userLocation = LatLng(42.3601, -71.0589);
      });
    }
  }

  Future<void> _loadCachedTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedTours = prefs.getString('cached_tours');
      
      if (cachedTours != null) {
        await DebugLogHelper.addDebugLog('HOME: Loading cached tours');
        final tours = json.decode(cachedTours) as List;
        
        // Apply clustering to cached tours too
        final clusteredTours = _clusterTours(tours);
        
        setState(() {
          _tourMarkers = clusteredTours.map((cluster) {
            final isTreat = cluster['tours'][0]['type'] == 'treat';
            final isMultiple = cluster['tours'].length > 1;
            
            return Marker(
              point: LatLng(cluster['lat'], cluster['lng']),
              width: 40,
              height: 40,
              child: GestureDetector(
                onTap: () => isMultiple 
                  ? _showMultipleTourDialog(cluster['tours'])
                  : _onTourMarkerTapped(cluster['tours'][0]),
                child: Stack(
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: isTreat ? Colors.orange : (isMultiple ? Colors.purple : Colors.blue),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                      child: Icon(
                        isTreat ? Icons.local_cafe : (isMultiple ? Icons.layers : Icons.directions_walk),
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
                    if (isMultiple)
                      Positioned(
                        right: -2,
                        top: -2,
                        child: Container(
                          width: 20,
                          height: 20,
                          decoration: BoxDecoration(
                            color: Colors.green,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 1),
                          ),
                          child: Icon(
                            Icons.apps,
                            color: Colors.white,
                            size: 12,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            );
          }).toList();
        });
        
        await DebugLogHelper.addDebugLog('HOME: Loaded ${tours.length} cached tours with clustering');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error loading cached tours: $e');
    }
  }

  Future<void> _loadNearbyTours() async {
    final searchLocation = _displayLocation ?? _userLocation;
    if (searchLocation == null) {
      await DebugLogHelper.addDebugLog('HOME: Cannot load tours - no location available');
      return;
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final url = 'http://$serverIp:5005/tours-near/${searchLocation.latitude}/${searchLocation.longitude}?radius=50';
      
      await DebugLogHelper.addDebugLog('HOME: Requesting tours from: $url');
      
      final response = await http.get(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
      ).timeout(Duration(seconds: 10));

      await DebugLogHelper.addDebugLog('HOME: Response status: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = data['tours'] as List;
        await DebugLogHelper.addDebugLog('HOME: Received ${tours.length} tours from server');

        // Cache the tours
        await prefs.setString('cached_tours', json.encode(tours));
        await DebugLogHelper.addDebugLog('HOME: Cached ${tours.length} tours');

        // Group tours by proximity (within 100m)
        final clusteredTours = _clusterTours(tours);
        
        if (mounted) {
          setState(() {
            _tourMarkers = clusteredTours.map((cluster) {
              try {
                final toursList = cluster['tours'] as List?;
                if (toursList == null || toursList.isEmpty) return null;
                
                final firstTour = toursList[0] as Map<String, dynamic>?;
                if (firstTour == null) return null;
                
                final isTreat = firstTour['type'] == 'treat';
                final isMultiple = toursList.length > 1;
                
                return Marker(
                  point: LatLng(cluster['lat'], cluster['lng']),
                  width: 40,
                  height: 40,
                  child: GestureDetector(
                    onTap: () => isMultiple 
                      ? _showMultipleTourDialog(toursList)
                      : _onTourMarkerTapped(firstTour),
                    child: Stack(
                      children: [
                        Container(
                          decoration: BoxDecoration(
                            color: isTreat ? Colors.orange : (toursList.length > 1 ? Colors.purple : Colors.blue),
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            isTreat ? Icons.local_cafe : Icons.directions_walk,
                            color: Colors.white,
                            size: 20,
                          ),
                        ),
                        if (isMultiple)
                          Positioned(
                            right: -2,
                            top: -2,
                            child: Container(
                              width: 20,
                              height: 20,
                              decoration: BoxDecoration(
                                color: Colors.green,
                                shape: BoxShape.circle,
                                border: Border.all(color: Colors.white, width: 1),
                              ),
                              child: Icon(
                                Icons.apps,
                                color: Colors.white,
                                size: 12,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              } catch (e) {
                return null;
              }
            }).where((marker) => marker != null).cast<Marker>().toList();
          });
        }

        await DebugLogHelper.addDebugLog('HOME: Loaded ${tours.length} tours for ${_isUsingCustomLocation ? _customLocationName : "current location"}');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Server error: ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error loading tours: $e');
    }
  }
  
  void _showLocationSearchDialog() {
    final TextEditingController controller = TextEditingController();
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Search Location'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              decoration: InputDecoration(
                hintText: 'Buenos Aires, Argentina',
                labelText: 'City, Country or Address',
              ),
              autofocus: true,
            ),
            SizedBox(height: 16),

            SizedBox(height: 16),
            if (_locationHistory.isNotEmpty) ...[
              Text('Recent Locations:', style: TextStyle(fontWeight: FontWeight.bold)),
              SizedBox(height: 8),
              Expanded(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _locationHistory.length,
                  itemBuilder: (context, index) {
                    final location = _locationHistory[index];
                    return ListTile(
                      dense: true,
                      leading: Icon(Icons.history, size: 16),
                      title: Text(location['name'], style: TextStyle(fontSize: 14)),
                      onTap: () {
                        Navigator.pop(context);
                        _useCustomLocation(
                          LatLng(location['lat'], location['lng']),
                          location['name'],
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _resetToCurrentLocation();
            },
            child: Text('Use Current Location'),
          ),
          ElevatedButton(
            onPressed: () async {
              final query = controller.text.trim();
              if (query.isEmpty) return;
              
              Navigator.pop(context);
              await _searchAndUseLocation(query);
            },
            child: Text('Search'),
          ),
        ],
      ),
    );
  }
  
  Future<void> _searchAndUseLocation(String query) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Text('Searching location...'),
          ],
        ),
      ),
    );
    
    final location = await _geocodeLocation(query);
    Navigator.pop(context);
    
    if (location != null) {
      await _useCustomLocation(location, query);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Location not found. Please try a different search.')),
      );
    }
  }
  
  Future<void> _useCustomLocation(LatLng location, String name) async {
    setState(() {
      _displayLocation = location;
      _isUsingCustomLocation = true;
      _customLocationName = name;
      _isLoading = true;
    });
    
    // Add to history (avoid duplicates)
    final locationData = {
      'name': name,
      'lat': location.latitude,
      'lng': location.longitude,
      'timestamp': DateTime.now().toIso8601String(),
    };
    
    _locationHistory.removeWhere((item) => item['name'] == name);
    _locationHistory.insert(0, locationData);
    if (_locationHistory.length > 10) {
      _locationHistory = _locationHistory.take(10).toList();
    }
    await _saveLocationHistory();
    await _saveCustomLocation();
    
    await DebugLogHelper.addDebugLog('HOME: Using custom location: $name');
    
    // Move map to new location
    _mapController.move(location, 13.0);
    
    // Load tours for new location
    await _loadNearbyTours();
    
    setState(() {
      _isLoading = false;
    });
  }
  
  void _resetToCurrentLocation() async {
    setState(() {
      _displayLocation = null;
      _isUsingCustomLocation = false;
      _customLocationName = '';
      _isLoading = true;
    });
    
    await _saveCustomLocation();
    await DebugLogHelper.addDebugLog('HOME: Reset to current location');
    
    if (_userLocation != null) {
      _mapController.move(_userLocation!, 13.0);
      await _loadNearbyTours();
    }
    
    setState(() {
      _isLoading = false;
    });
  }

  void _onTourMarkerTapped(Map<String, dynamic> item) {
    if (item['type'] == 'treat') {
      // Navigate directly to treat detail view
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => _TreatDetailView(
            treatData: item,
          ),
        ),
      );
    } else {
      // Show download dialog for tours
      showDialog(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(item['name']),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Distance: ${item['distance_km']} km'),
              Text('Downloads: ${item['popularity']}'),
              SizedBox(height: 10),
              Text(item['request_string']),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text('Close'),
            ),
            ElevatedButton(
              onPressed: () => _downloadTour(item['id']),
              child: Text('Download Tour'),
            ),
          ],
        ),
      );
    }
  }

  List<Map<String, dynamic>> _clusterTours(List tours) {
    final clusters = <Map<String, dynamic>>[];
    final processed = <bool>[];
    
    for (int i = 0; i < tours.length; i++) {
      processed.add(false);
    }
    
    for (int i = 0; i < tours.length; i++) {
      if (processed[i]) continue;
      
      final cluster = {
        'lat': tours[i]['lat'],
        'lng': tours[i]['lng'],
        'tours': [tours[i]],
      };
      processed[i] = true;
      
      // Find nearby tours (within 100m)
      for (int j = i + 1; j < tours.length; j++) {
        if (processed[j]) continue;
        
        final distance = _calculateDistance(
          tours[i]['lat'], tours[i]['lng'],
          tours[j]['lat'], tours[j]['lng'],
        );
        
        if (distance <= 0.1) { // 100m
          cluster['tours'].add(tours[j]);
          processed[j] = true;
        }
      }
      
      clusters.add(cluster);
    }
    
    return clusters;
  }
  
  double _calculateDistance(double lat1, double lng1, double lat2, double lng2) {
    const double earthRadius = 6371;
    final double dLat = (lat2 - lat1) * (3.14159 / 180);
    final double dLng = (lng2 - lng1) * (3.14159 / 180);
    final double a = sin(dLat / 2) * sin(dLat / 2) +
        cos(lat1 * (3.14159 / 180)) * cos(lat2 * (3.14159 / 180)) *
        sin(dLng / 2) * sin(dLng / 2);
    final double c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }
  
  void _showMultipleTourDialog(List tours) {
    List<bool> selectedTours = List.filled(tours.length, false);
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Select Tours (${tours.length} available)'),
          content: Container(
            width: double.maxFinite,
            height: MediaQuery.of(context).size.height * 0.4,
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          setDialogState(() {
                            for (int i = 0; i < selectedTours.length; i++) {
                              selectedTours[i] = true;
                            }
                          });
                        },
                        child: Text('Select All'),
                      ),
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () {
                          setDialogState(() {
                            for (int i = 0; i < selectedTours.length; i++) {
                              selectedTours[i] = false;
                            }
                          });
                        },
                        child: Text('Clear All'),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 16),
                Expanded(
                  child: ListView.builder(
                    itemCount: tours.length,
                    itemBuilder: (context, index) {
                      final tour = tours[index];
                      return CheckboxListTile(
                        value: selectedTours[index],
                        onChanged: (bool? value) {
                          setDialogState(() {
                            selectedTours[index] = value ?? false;
                          });
                        },
                        title: Text(
                          tour['name'],
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Distance: ${tour['distance_km']} km'),
                            Text('Downloads: ${tour['popularity']}'),
                          ],
                        ),
                        dense: true,
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.pop(context);
                final selected = <Map<String, dynamic>>[];
                for (int i = 0; i < tours.length; i++) {
                  if (selectedTours[i]) {
                    selected.add(tours[i]);
                  }
                }
                if (selected.isNotEmpty) {
                  _downloadMultipleTours(selected);
                }
              },
              child: Text('Download Selected (${selectedTours.where((s) => s).length})'),
            ),
          ],
        ),
      ),
    );
  }
  
  Future<void> _downloadMultipleTours(List<Map<String, dynamic>> tours) async {
    // Check which tours are already downloaded
    final prefs = await SharedPreferences.getInstance();
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final existingTours = savedTours.map((tour) => json.decode(tour) as Map<String, dynamic>).toList();
    final existingTourIds = existingTours.map((tour) => tour['tour_id']).toSet();
    
    final toursToDownload = tours.where((tour) => !existingTourIds.contains(tour['id'].toString())).toList();
    final alreadyDownloaded = tours.length - toursToDownload.length;
    
    if (toursToDownload.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('All selected tours are already downloaded'),
          backgroundColor: Colors.green,
        ),
      );
      return;
    }
    
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Text('Downloading ${toursToDownload.length} new tours...'),
          ],
        ),
      ),
    );
    
    int successCount = 0;
    for (final tour in toursToDownload) {
      try {
        await _downloadSingleTour(tour['id']);
        successCount++;
      } catch (e) {
        // Continue with next tour
      }
    }
    
    Navigator.pop(context);
    
    String message;
    if (successCount > 0) {
      message = '$successCount tours downloaded and now are available on your Listen Page';
      if (alreadyDownloaded > 0) {
        message += ' ($alreadyDownloaded were already downloaded)';
      }
    } else {
      message = 'No new tours downloaded';
      if (alreadyDownloaded > 0) {
        message += ' - all selected tours were already available';
      }
    }
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        action: successCount > 0 ? SnackBarAction(
          label: 'View',
          onPressed: () => Navigator.pushNamed(context, '/my_tours'),
        ) : null,
      ),
    );
  }
  
  Future<void> _downloadTour(int tourId) async {
    await DebugLogHelper.addDebugLog('HOME: Starting tour download for ID: $tourId');
    await DebugLogHelper.addDebugLog('HOME: Using context: ${context.runtimeType}');
    await DebugLogHelper.addDebugLog('HOME: Widget mounted at start: $mounted');
    
    // Check if this exact tour is already downloaded
    final prefs = await SharedPreferences.getInstance();
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final existingTours = savedTours.map((tour) => json.decode(tour) as Map<String, dynamic>).toList();
    
    // Check for exact match by tour_id
    Map<String, dynamic>? existingTour;
    try {
      existingTour = existingTours.where((tour) => tour['tour_id'] == tourId.toString()).firstOrNull;
    } catch (e) {
      existingTour = null;
    }
    
    if (existingTour != null) {
      await DebugLogHelper.addDebugLog('HOME: Tour $tourId already exists in My Tours');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('This tour is already downloaded'),
            backgroundColor: Colors.green,
            action: SnackBarAction(
              label: 'Open',
              onPressed: () {
                Navigator.pushNamed(context, '/my_tours');
              },
            ),
          ),
        );
      }
      return;
    }
    
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => AlertDialog(
        title: Text('Downloading Tour'),
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Expanded(
              child: Text('Downloading tour...\nYou can dismiss this dialog and continue using the app.'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(context);
            },
            child: Text('Dismiss'),
          ),
        ],
      ),
    );

    try {
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final url = 'http://$serverIp:5005/download-tour/$tourId';
      
      await DebugLogHelper.addDebugLog('HOME: Downloading from: $url');
      
      final response = await http.get(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
      ).timeout(Duration(seconds: 120));

      await DebugLogHelper.addDebugLog('HOME: Download response: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('HOME: Tour downloaded successfully (${response.bodyBytes.length} bytes)');
        
        // Save tour to My Tours
        await _saveTourToMyTours(tourId, response.bodyBytes);
        await DebugLogHelper.addDebugLog('HOME: MAIN - Back from _saveTourToMyTours');
        
        // Dismiss dialog AFTER save completes
        await DebugLogHelper.addDebugLog('HOME: MAIN - Checking if widget is mounted: $mounted');
        
        // Try to update UI regardless of mounted state
        try {
          if (mounted) {
            await DebugLogHelper.addDebugLog('HOME: MAIN - Widget is mounted, dismissing dialog');
            Navigator.pop(context);
            await DebugLogHelper.addDebugLog('HOME: MAIN - Dialog dismissed successfully');
          } else {
            await DebugLogHelper.addDebugLog('HOME: MAIN - Widget NOT mounted, trying to find context');
            // Try to find any available context to show success
            final navigatorState = Navigator.of(context, rootNavigator: true);
            if (navigatorState.canPop()) {
              navigatorState.pop();
              await DebugLogHelper.addDebugLog('HOME: MAIN - Dialog dismissed via root navigator');
            }
          }
          
          // Always show success message
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Tour downloaded and added to My Tours!'),
              backgroundColor: Colors.green,
              action: SnackBarAction(
                label: 'View',
                onPressed: () => Navigator.pushNamed(context, '/my_tours'),
              ),
            ),
          );
          await DebugLogHelper.addDebugLog('HOME: MAIN - Success message shown');
        } catch (uiError) {
          await DebugLogHelper.addDebugLog('HOME: MAIN - UI update error: $uiError');
          // Download completed successfully even if UI update failed
        }
        
        await DebugLogHelper.addDebugLog('HOME: MAIN - Download function completing');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Download failed: ${response.body}');
        throw Exception('Failed to download tour: ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Download error: $e');
      await DebugLogHelper.addDebugLog('HOME: Error stack trace: ${e.toString()}');
      
      await DebugLogHelper.addDebugLog('HOME: MAIN - In error handler, mounted: $mounted');
      
      if (mounted) {
        try {
          Navigator.pop(context);
          await DebugLogHelper.addDebugLog('HOME: MAIN - Error dialog dismissed');
        } catch (navError) {
          await DebugLogHelper.addDebugLog('HOME: MAIN - Error dialog dismiss failed: $navError');
        }
        
        String errorMessage = 'Error downloading tour';
        if (e.toString().contains('Connection closed')) {
          errorMessage = 'Download interrupted - please try again';
        } else if (e.toString().contains('timeout')) {
          errorMessage = 'Download timed out - please check connection';
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            duration: Duration(seconds: 5),
          ),
        );
      }
    }
  }
  
  Future<void> _downloadSingleTour(int tourId) async {
    final prefs = await SharedPreferences.getInstance();
    final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
    final url = 'http://$serverIp:5005/download-tour/$tourId';
    
    final response = await http.get(
      Uri.parse(url),
      headers: {'Content-Type': 'application/json'},
    ).timeout(Duration(seconds: 120));

    if (response.statusCode == 200) {
      await _saveTourToMyTours(tourId, response.bodyBytes);
    } else {
      throw Exception('Failed to download tour: ${response.statusCode}');
    }
  }
  
  void _showTourSearchDialog() {
    final TextEditingController controller = TextEditingController();
    List<Map<String, dynamic>> searchResults = [];
    List<bool> selectedTours = [];
    bool isSearching = false;
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Search Tours'),
          content: Container(
            width: double.maxFinite,
            height: MediaQuery.of(context).size.height * 0.6,
            child: Column(
              children: [
                TextField(
                  controller: controller,
                  decoration: InputDecoration(
                    hintText: 'enter your search parameters here',
                    labelText: 'Search tours (use * for wildcards)',
                    helperText: 'Examples: "Boston", "walking*tour", "museum*history", "art*gallery"',
                    helperMaxLines: 2,
                    labelStyle: TextStyle(fontSize: 12),
                    suffixIcon: IconButton(
                      icon: Icon(Icons.search),
                      onPressed: () async {
                        if (controller.text.trim().isEmpty) return;
                        
                        setDialogState(() {
                          isSearching = true;
                          searchResults = [];
                          selectedTours = [];
                        });
                        
                        final results = await _searchTours(controller.text.trim());
                        
                        setDialogState(() {
                          isSearching = false;
                          searchResults = results;
                          selectedTours = List.filled(results.length, false);
                        });
                      },
                    ),
                  ),
                  onSubmitted: (value) async {
                    if (value.trim().isEmpty) return;
                    
                    setDialogState(() {
                      isSearching = true;
                      searchResults = [];
                      selectedTours = [];
                    });
                    
                    final results = await _searchTours(value.trim());
                    
                    setDialogState(() {
                      isSearching = false;
                      searchResults = results;
                      selectedTours = List.filled(results.length, false);
                    });
                  },
                ),
                SizedBox(height: 16),
                if (isSearching)
                  Center(child: CircularProgressIndicator())
                else if (searchResults.isNotEmpty) ...[
                  Row(
                    children: [
                      Expanded(
                        child: ElevatedButton(
                          onPressed: () {
                            setDialogState(() {
                              for (int i = 0; i < selectedTours.length; i++) {
                                selectedTours[i] = true;
                              }
                            });
                          },
                          child: Text('Select All'),
                        ),
                      ),
                      SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () {
                            setDialogState(() {
                              for (int i = 0; i < selectedTours.length; i++) {
                                selectedTours[i] = false;
                              }
                            });
                          },
                          child: Text('Clear All'),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 16),
                  Expanded(
                    child: ListView.builder(
                      itemCount: searchResults.length,
                      itemBuilder: (context, index) {
                        final tour = searchResults[index];
                        return CheckboxListTile(
                          value: selectedTours[index],
                          onChanged: (bool? value) {
                            setDialogState(() {
                              selectedTours[index] = value ?? false;
                            });
                          },
                          title: Text(
                            tour['name'],
                            style: TextStyle(fontWeight: FontWeight.bold),
                          ),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Distance: ${tour['distance_km']} km'),
                              Text('Downloads: ${tour['popularity']}'),
                            ],
                          ),
                          dense: true,
                        );
                      },
                    ),
                  ),
                ] else if (controller.text.isNotEmpty && !isSearching)
                  Center(child: Text('No tours found')),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text('Cancel'),
            ),
            if (searchResults.isNotEmpty)
              ElevatedButton(
                onPressed: () {
                  Navigator.pop(context);
                  final selected = <Map<String, dynamic>>[];
                  for (int i = 0; i < searchResults.length; i++) {
                    if (selectedTours[i]) {
                      selected.add(searchResults[i]);
                    }
                  }
                  if (selected.isNotEmpty) {
                    _downloadMultipleTours(selected);
                  }
                },
                child: Text('Download Selected (${selectedTours.where((s) => s).length})'),
              ),
          ],
        ),
      ),
    );
  }
  
  Future<List<Map<String, dynamic>>> _searchTours(String query) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      // Convert wildcard pattern to regex
      final regexPattern = query.replaceAll('*', '.*');
      
      final searchLocation = _displayLocation ?? _userLocation;
      if (searchLocation == null) {
        await DebugLogHelper.addDebugLog('HOME: Tour search failed - no location available');
        return [];
      }
      
      final searchUrl = 'http://$serverIp:5005/search-tours?pattern=${Uri.encodeComponent(regexPattern)}&lat=${searchLocation.latitude}&lng=${searchLocation.longitude}';
      await DebugLogHelper.addDebugLog('HOME: Searching tours with URL: $searchUrl');
      
      final response = await http.get(
        Uri.parse(searchUrl),
        headers: {'Content-Type': 'application/json'},
      ).timeout(Duration(seconds: 10));
      
      await DebugLogHelper.addDebugLog('HOME: Tour search response: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = List<Map<String, dynamic>>.from(data['tours'] ?? []);
        await DebugLogHelper.addDebugLog('HOME: Found ${tours.length} tours matching "$query"');
        return tours;
      } else {
        await DebugLogHelper.addDebugLog('HOME: Tour search error: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Tour search exception: $e');
    }
    return [];
  }
  
  void _showTourOnMap(Map<String, dynamic> tour) {
    final tourLocation = LatLng(tour['lat'], tour['lng']);
    _mapController.move(tourLocation, 15.0);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Showing ${tour['name']} on map'),
        action: SnackBarAction(
          label: 'Download',
          onPressed: () => _downloadSingleTour(tour['id']),
        ),
      ),
    );
  }

  Future<void> _saveTourToMyTours(int tourId, List<int> zipBytes) async {
    try {
      await DebugLogHelper.addDebugLog('HOME: SAVE - Starting _saveTourToMyTours');
      
      final prefs = await SharedPreferences.getInstance();
      await DebugLogHelper.addDebugLog('HOME: SAVE - Got SharedPreferences');
      
      final appDir = await getApplicationDocumentsDirectory();
      await DebugLogHelper.addDebugLog('HOME: SAVE - Got app directory: ${appDir.path}');
      
      // Get tour resolution info first
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      await DebugLogHelper.addDebugLog('HOME: Resolving tour ID for download ID: $tourId');
      
      final resolutionResponse = await http.get(
        Uri.parse('http://$serverIp:5025/tour/$tourId/resolve'),
      );
      
      await DebugLogHelper.addDebugLog('HOME: Tour resolution response: ${resolutionResponse.statusCode}');
      
      String editTourId;
      String baseTourName = 'Downloaded Tour';
      bool isEditable = false;
      
      if (resolutionResponse.statusCode == 200) {
        try {
          final resolutionData = json.decode(resolutionResponse.body);
          await DebugLogHelper.addDebugLog('HOME: Tour resolution data: $resolutionData');
          
          if (resolutionData['status'] == 'success') {
            editTourId = resolutionData['edit_tour_id'] ?? tourId.toString();
            baseTourName = resolutionData['tour_name'] ?? 'Downloaded Tour';
            isEditable = resolutionData['editable'] ?? false;
            
            await DebugLogHelper.addDebugLog('HOME: Resolved - Edit ID: $editTourId, Name: $baseTourName, Editable: $isEditable');
          } else {
            throw Exception('Resolution failed: ${resolutionData['message']}');
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('HOME: Error parsing resolution data: $e');
          throw Exception('Failed to resolve tour ID $tourId: $e');
        }
      } else {
        final errorBody = resolutionResponse.body;
        await DebugLogHelper.addDebugLog('HOME: Tour resolution error: ${resolutionResponse.statusCode} - $errorBody');
        
        String errorMessage;
        try {
          final errorData = json.decode(errorBody);
          errorMessage = 'Tour "$baseTourName" (ID: $tourId) could not be downloaded.\n\nError: ${errorData['message'] ?? 'Unknown error'}\n\nPlease contact your administrator with this information.';
        } catch (e) {
          errorMessage = 'Tour download failed (ID: $tourId).\n\nServer returned error ${resolutionResponse.statusCode}.\n\nPlease contact your administrator with this information.';
        }
        
        throw Exception(errorMessage);
      }
      
      await DebugLogHelper.addDebugLog('HOME: SAVE - Getting saved tours list');
      
      // Check for duplicates by name only (not tour_id) and create versioned name
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      await DebugLogHelper.addDebugLog('HOME: SAVE - Found ${savedTours.length} existing tours');
      
      final existingTours = savedTours.map((tour) => json.decode(tour) as Map<String, dynamic>).toList();
      await DebugLogHelper.addDebugLog('HOME: SAVE - Parsed existing tours');
      
      String finalTourName = baseTourName;
      int version = 1;
      
      // Check if tour with same name already exists (different tour_id)
      while (existingTours.any((tour) => tour['title'] == finalTourName)) {
        version++;
        finalTourName = '$baseTourName (v$version)';
      }
      
      await DebugLogHelper.addDebugLog('HOME: Final tour name: $finalTourName');
      
      await DebugLogHelper.addDebugLog('HOME: SAVE - Creating tour directory');
      
      // Create tour directory using edit tour ID (reuse edit tour logic)
      final safeName = finalTourName.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      final tourDir = Directory('${appDir.path}/tours/${safeName}_$editTourId');
      await tourDir.create(recursive: true);
      await DebugLogHelper.addDebugLog('HOME: SAVE - Created directory with edit ID: ${tourDir.path}');
      
      // Save ZIP file
      final zipFile = File('${tourDir.path}/tour.zip');
      await zipFile.writeAsBytes(zipBytes);
      await DebugLogHelper.addDebugLog('HOME: SAVE - Saved ZIP file');
      
      // Extract ZIP file
      await DebugLogHelper.addDebugLog('HOME: SAVE - Starting ZIP extraction');
      final archive = ZipDecoder().decodeBytes(zipBytes);
      await DebugLogHelper.addDebugLog('HOME: SAVE - ZIP decoded, ${archive.length} files');
      
      for (final file in archive) {
        final filename = file.name;
        if (file.isFile) {
          final data = file.content as List<int>;
          final extractedFile = File('${tourDir.path}/$filename');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(data);
        }
      }
      await DebugLogHelper.addDebugLog('HOME: SAVE - ZIP extraction completed');
      
      await DebugLogHelper.addDebugLog('HOME: SAVE - Creating tour data object');
      
      // Add to saved tours list with edit tour ID (only store tour_id)
      final tourData = {
        'title': finalTourName,
        'path': tourDir.path,
        'created': DateTime.now().toIso8601String(),
        'stops': '10',
        'original_request': baseTourName,
        'tour_id': editTourId,  // Store edit tour ID, not download ID
        'editable': isEditable,
      };
      
      await DebugLogHelper.addDebugLog('HOME: SAVE - Adding to saved tours list');
      savedTours.add(json.encode(tourData));
      
      await DebugLogHelper.addDebugLog('HOME: SAVE - Saving to SharedPreferences');
      await prefs.setStringList('saved_tours', savedTours);
      
      await DebugLogHelper.addDebugLog('HOME: Tour saved to My Tours: $finalTourName at ${tourDir.path}');
      await DebugLogHelper.addDebugLog('HOME: SAVE - _saveTourToMyTours COMPLETED');
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error saving tour to My Tours: $e');
      throw e;
    }
  }

  Future<void> _loadNewsletters() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await DebugLogHelper.addDebugLog('HOME: Loading newsletters from http://$serverIp:5017/newsletters_v2');
      
      final response = await http.get(
        Uri.parse('http://$serverIp:5017/newsletters_v2'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(Duration(seconds: 10));
      
      await DebugLogHelper.addDebugLog('HOME: Newsletter response status: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final newsletters = List<Map<String, dynamic>>.from(data['newsletters'] ?? []);
        await DebugLogHelper.addDebugLog('HOME: Loaded ${newsletters.length} newsletters from server');
        
        setState(() {
          _newsletters = newsletters;
          _isLoading = false;
        });
      } else {
        await DebugLogHelper.addDebugLog('HOME: Newsletter server error: ${response.statusCode}');
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Server error: ${response.statusCode}. Please try again later.'),
            backgroundColor: Colors.red,
          ),
        );
        
        setState(() {
          _newsletters = [];
          _isLoading = false;
        });
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Newsletter loading error: $e');
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('No connection. Please check network and try again.'),
          backgroundColor: Colors.red,
        ),
      );
      
      setState(() {
        _newsletters = [];
        _isLoading = false;
      });
    }
  }
  
  Future<void> _processNewsletter(int newsletterId, String name) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Loading newsletter articles...')),
            ],
          ),
        ),
      );
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5017/get_articles_by_newsletter_id'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'newsletter_id': newsletterId}),
      ).timeout(Duration(seconds: 30));
      
      Navigator.pop(context);
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final articles = List<Map<String, dynamic>>.from(data['articles'] ?? []);
        
        if (articles.isEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('No articles found in this newsletter edition')),
          );
          return;
        }
        
        _showArticleSelectionDialog(articles, newsletterId, name);
      } else {
        final error = json.decode(response.body)['error'] ?? 'Failed to load articles';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $error'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error loading articles: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _processSelectedArticles(List<Map<String, dynamic>> selectedArticles, int newsletterId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Adding ${selectedArticles.length} articles to Listen page...')),
            ],
          ),
        ),
      );
      
      final savedNews = prefs.getStringList('saved_news') ?? [];
      final existingArticleIds = <String>{};
      
      // Get existing article IDs to avoid duplicates
      for (final newsJson in savedNews) {
        try {
          final news = json.decode(newsJson) as Map<String, dynamic>;
          final articleId = news['article_id'];
          if (articleId != null) {
            existingArticleIds.add(articleId);
          }
        } catch (e) {
          // Continue if parsing fails
        }
      }
      
      int addedCount = 0;
      
      // Remove duplicates from selected articles and filter out existing ones
      final uniqueSelected = <String, Map<String, dynamic>>{};
      for (final article in selectedArticles) {
        final articleId = article['article_id'];
        if (!existingArticleIds.contains(articleId)) {
          uniqueSelected[articleId] = article;
        }
      }
      
      for (final article in uniqueSelected.values) {
        try {
          final articleId = article['article_id'];
          final title = article['title'];
          
          final downloadResponse = await http.get(
            Uri.parse('http://$serverIp:5012/download/$articleId'),
            headers: {'Content-Type': 'application/json'},
          ).timeout(Duration(seconds: 30));
          
          if (downloadResponse.statusCode == 200) {
            final appDir = await getApplicationDocumentsDirectory();
            final truncatedTitle = title.length > 50 ? title.substring(0, 50) : title;
            final safeName = truncatedTitle.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
            final articleDir = Directory('${appDir.path}/news/${safeName}_$articleId');
            await articleDir.create(recursive: true);
            
            final zipFile = File('${articleDir.path}/article.zip');
            await zipFile.writeAsBytes(downloadResponse.bodyBytes);
            
            final archive = ZipDecoder().decodeBytes(downloadResponse.bodyBytes);
            for (final file in archive) {
              if (file.isFile) {
                final extractedFile = File('${articleDir.path}/${file.name}');
                await extractedFile.create(recursive: true);
                await extractedFile.writeAsBytes(file.content as List<int>);
              }
            }
            
            // Extract and save text content for search
            try {
              final textFile = File('${articleDir.path}/audiotours_search_content.txt');
              String textContent = '';
              
              // Try to extract text from index.html
              final indexFile = File('${articleDir.path}/index.html');
              if (await indexFile.exists()) {
                final htmlContent = await indexFile.readAsString();
                // Simple text extraction - remove HTML tags
                textContent = htmlContent
                    .replaceAll(RegExp(r'<[^>]*>'), ' ')
                    .replaceAll(RegExp(r'\s+'), ' ')
                    .trim();
              }
              
              await textFile.writeAsString(textContent);
            } catch (e) {
              // Continue if text extraction fails
            }
            
            final articleData = {
              'title': title,
              'path': articleDir.path,
              'created': DateTime.now().toIso8601String(),
              'original_request': title,
              'article_id': articleId,
              'article_type': article['article_type'] ?? 'Others',
            };
            
            savedNews.add(json.encode(articleData));
            addedCount++;
          }
        } catch (e) {
          // Continue with next article
        }
      }
      
      await prefs.setStringList('saved_news', savedNews);
      Navigator.pop(context);
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$addedCount articles added to Listen page!')),
      );
      
      // Refresh newsletters to show the new one
      await _loadNewsletters();
    } catch (e) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error processing articles: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  void _showArticleSelectionDialog(List<Map<String, dynamic>> articles, int newsletterId, String newsletterName) {
    List<bool> selectedArticles = List.filled(articles.length, false);
    String dialogFilter = 'All';
    String searchQuery = '';
    TextEditingController searchController = TextEditingController();
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          List<Map<String, dynamic>> filteredArticles = List.from(articles);
          
          // Apply type filter
          if (dialogFilter != 'All') {
            filteredArticles = filteredArticles.where((article) {
              final articleType = article['article_type'] ?? 'Others';
              return articleType == dialogFilter;
            }).toList();
          }
          
          // Apply search filter
          if (searchQuery.isNotEmpty) {
            filteredArticles = filteredArticles.where((article) {
              final title = (article['title'] ?? '').toLowerCase();
              final author = (article['author'] ?? '').toLowerCase();
              final searchLower = searchQuery.toLowerCase();
              
              // Simple search in title and author
              bool matches = title.contains(searchLower) || author.contains(searchLower);
              
              // Handle exclude terms (words starting with -)
              final terms = searchQuery.split(' ');
              for (final term in terms) {
                if (term.startsWith('-') && term.length > 1) {
                  final excludeTerm = term.substring(1).toLowerCase();
                  if (title.contains(excludeTerm) || author.contains(excludeTerm)) {
                    matches = false;
                    break;
                  }
                }
              }
              
              return matches;
            }).toList();
          }
          
          final keyboardHeight = MediaQuery.of(context).viewInsets.bottom;
          final screenHeight = MediaQuery.of(context).size.height;
          final availableHeight = screenHeight - keyboardHeight - 200; // Reserve space for title and actions
          
          return AlertDialog(
            title: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Expanded(child: Text('Select Articles')),
                    IconButton(
                      icon: Icon(Icons.search, size: 20),
                      onPressed: () {
                        showDialog(
                          context: context,
                          builder: (context) => AlertDialog(
                            title: Text('Search Articles'),
                            content: TextField(
                              controller: searchController,
                              decoration: InputDecoration(
                                hintText: 'microsoft profit -speculation',
                                helperText: 'Include terms, exclude with -term',
                              ),
                              autofocus: true,
                            ),
                            actions: [
                              TextButton(
                                onPressed: () {
                                  searchController.clear();
                                  setDialogState(() {
                                    searchQuery = '';
                                  });
                                  Navigator.pop(context);
                                },
                                child: Text('Clear'),
                              ),
                              ElevatedButton(
                                onPressed: () {
                                  setDialogState(() {
                                    searchQuery = searchController.text;
                                  });
                                  Navigator.pop(context);
                                },
                                child: Text('Search'),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                    PopupMenuButton<String>(
                      icon: Icon(Icons.filter_list, size: 20),
                      onSelected: (String value) {
                        setDialogState(() {
                          dialogFilter = value;
                        });
                      },
                      itemBuilder: (BuildContext context) {
                        return _articleTypes.map((String type) {
                          return PopupMenuItem<String>(
                            value: type,
                            child: Row(
                              children: [
                                Icon(
                                  dialogFilter == type ? Icons.check : Icons.radio_button_unchecked,
                                  size: 16,
                                ),
                                SizedBox(width: 8),
                                Text(type, style: TextStyle(fontSize: 12)),
                              ],
                            ),
                          );
                        }).toList();
                      },
                    ),
                  ],
                ),
                if (searchQuery.isNotEmpty)
                  Padding(
                    padding: EdgeInsets.only(top: 8),
                    child: Text(
                      'Search: "$searchQuery"',
                      style: TextStyle(fontSize: 12, color: Colors.blue),
                    ),
                  ),
              ],
            ),
            content: Container(
              width: double.maxFinite,
              height: availableHeight > 200 ? availableHeight : 200,
              child: Column(
                children: [
                  Text(
                    dialogFilter == 'All' 
                      ? 'Found ${articles.length} articles from $newsletterName'
                      : 'Showing ${filteredArticles.length} "$dialogFilter" articles from $newsletterName',
                    style: TextStyle(fontSize: 14, color: Colors.grey.shade600),
                  ),
                  SizedBox(height: 16),
                  Expanded(
                    child: ListView.builder(
                      itemCount: filteredArticles.length,
                      itemBuilder: (context, index) {
                        final article = filteredArticles[index];
                        final originalIndex = articles.indexOf(article);
                        final title = article['title'] ?? 'Untitled Article';
                        final author = article['author'] ?? 'Unknown Author';
                        final date = article['date'] ?? 'Unknown Date';
                        final articleType = article['article_type'] ?? 'Others';
                        
                        return CheckboxListTile(
                          value: selectedArticles[originalIndex],
                          onChanged: (bool? value) {
                            setDialogState(() {
                              selectedArticles[originalIndex] = value ?? false;
                            });
                          },
                          title: Text(
                            title,
                            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Container(
                                    padding: EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: _getTypeColor(articleType),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: Text(
                                      articleType,
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 10,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ),
                                  SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      'By: $author',
                                      style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                    ),
                                  ),
                                ],
                              ),
                              Text(
                                'Date: $date',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
                              ),
                            ],
                          ),
                          dense: true,
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('Cancel'),
              ),
              TextButton(
                onPressed: () {
                  setDialogState(() {
                    // Only select articles that are currently visible (filtered)
                    for (final article in filteredArticles) {
                      final originalIndex = articles.indexOf(article);
                      if (originalIndex >= 0) {
                        selectedArticles[originalIndex] = true;
                      }
                    }
                  });
                },
                child: Text('Select All (${filteredArticles.length})'),
              ),
              ElevatedButton(
                onPressed: () {
                  final selected = <Map<String, dynamic>>[];
                  for (int i = 0; i < articles.length; i++) {
                    if (selectedArticles[i]) {
                      selected.add(articles[i]);
                    }
                  }
                  
                  Navigator.pop(context);
                  
                  if (selected.isEmpty) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('No articles selected')),
                    );
                    return;
                  }
                  
                  _processSelectedArticles(selected, newsletterId);
                },
                child: Text('Add Selected (${selectedArticles.where((s) => s).length})'),
              ),
            ],
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(
          title: Text('🏠 Home'),
          backgroundColor: Color(0xFF2c3e50),
          foregroundColor: Colors.white,
        ),
        body: Center(child: CircularProgressIndicator()),
      );
    }
    
    if (_appMode == 'Audio') {
      return _buildNewsletterView();
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('🏠 Home'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: Icon(Icons.tour),
            onPressed: _showTourSearchDialog,
            tooltip: 'Search Tours',
          ),
          IconButton(
            icon: Icon(Icons.search),
            onPressed: _showLocationSearchDialog,
            tooltip: 'Search Location',
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () async {
              await DebugLogHelper.addDebugLog('HOME: Manual refresh triggered');
              await _loadNearbyTours();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Container(
            padding: EdgeInsets.all(16),
            color: _isUsingCustomLocation ? Colors.orange.shade50 : Colors.blue.shade50,
            child: Column(
              children: [
                if (_isUsingCustomLocation) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.location_on, color: Colors.orange.shade700, size: 20),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Showing tours near: $_customLocationName',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.bold,
                            color: Colors.orange.shade800,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: _resetToCurrentLocation,
                        child: Text('Reset', style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                  SizedBox(height: 4),
                ],
                Text(
                  _isUsingCustomLocation 
                    ? 'Select to download for your trip'
                    : 'Most popular tours and treats in your area\nSelect to download',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                    color: _isUsingCustomLocation ? Colors.orange.shade800 : Colors.blue.shade800,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: _displayLocation ?? _userLocation ?? LatLng(42.3601, -71.0589),
                initialZoom: 13.0,
              ),
              children: [
                TileLayer(
                  urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.example.audiotours',
                ),
                
                MarkerLayer(markers: _tourMarkers),
                
                // User location marker (always show if available)
                if (_userLocation != null && !_isUsingCustomLocation)
                  MarkerLayer(
                    markers: [
                      Marker(
                        point: _userLocation!,
                        width: 30,
                        height: 30,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.red,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            Icons.person,
                            color: Colors.white,
                            size: 16,
                          ),
                        ),
                      ),
                    ],
                  ),
                
                // Custom location marker
                if (_isUsingCustomLocation && _displayLocation != null)
                  MarkerLayer(
                    markers: [
                      Marker(
                        point: _displayLocation!,
                        width: 35,
                        height: 35,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.orange,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            Icons.search,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          if (_isUsingCustomLocation) {
            _resetToCurrentLocation();
          } else {
            final position = await Geolocator.getCurrentPosition();
            final newLocation = LatLng(position.latitude, position.longitude);
            _mapController.move(newLocation, 15.0);
            setState(() {
              _userLocation = newLocation;
            });
          }
        },
        backgroundColor: _isUsingCustomLocation ? Colors.orange : null,
        child: Icon(_isUsingCustomLocation ? Icons.home : Icons.my_location),
      ),
    );
  }
  
  Widget _buildNewsletterView() {
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedTypeFilter == 'All' 
          ? '📧 Newsletters' 
          : '📧 Newsletters (${_selectedTypeFilter})'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          PopupMenuButton<String>(
            icon: Icon(Icons.filter_list),
            onSelected: (String value) {
              setState(() {
                _selectedTypeFilter = value;
              });
            },
            itemBuilder: (BuildContext context) {
              return _articleTypes.map((String type) {
                return PopupMenuItem<String>(
                  value: type,
                  child: Row(
                    children: [
                      Icon(
                        _selectedTypeFilter == type ? Icons.check : Icons.radio_button_unchecked,
                        size: 16,
                      ),
                      SizedBox(width: 8),
                      Text(type),
                    ],
                  ),
                );
              }).toList();
            },
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () async {
              await DebugLogHelper.addDebugLog('HOME: Manual newsletter refresh triggered');
              setState(() {
                _isLoading = true;
              });
              await _loadNewsletters();
            },
          ),
        ],
      ),
      body: _newsletters.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.email_outlined,
                    size: 64,
                    color: Colors.grey,
                  ),
                  SizedBox(height: 16),
                  Text(
                    'No newsletters available',
                    style: TextStyle(
                      fontSize: 18,
                      color: Colors.grey,
                    ),
                  ),
                  SizedBox(height: 8),
                  Text(
                    'Add newsletter URLs in the Generate section',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            )
          : RefreshIndicator(
              onRefresh: _loadNewsletters,
              child: _buildNewsletterSections(),
            ),
    );
  }
  
  List<Map<String, dynamic>> _getFilteredNewsletters() {
    final now = DateTime.now();
    final oneMonthAgo = now.subtract(Duration(days: 30));
    
    // Filter by type and date, limit to 12 latest
    var filtered = _newsletters.where((newsletter) {
      // Filter by type
      if (_selectedTypeFilter != 'All') {
        final newsletterType = newsletter['type'] ?? 'Others';
        if (newsletterType != _selectedTypeFilter) return false;
      }
      
      // Filter by date (last 30 days)
      final createdAt = newsletter['created_at'];
      if (createdAt != null) {
        try {
          final date = DateTime.parse(createdAt);
          return date.isAfter(oneMonthAgo);
        } catch (e) {
          return true; // Include if date parsing fails
        }
      }
      return true;
    }).toList();
    
    // Sort by date (newest first) and limit to 12
    filtered.sort((a, b) {
      try {
        final dateA = DateTime.parse(a['created_at'] ?? '');
        final dateB = DateTime.parse(b['created_at'] ?? '');
        return dateB.compareTo(dateA);
      } catch (e) {
        return 0;
      }
    });
    
    return filtered.take(12).toList();
  }
  
  Widget _buildNewsletterSections() {
    final newsletters = _getFilteredNewsletters();
    if (newsletters.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.email_outlined, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('No newsletters available', style: TextStyle(fontSize: 18, color: Colors.grey)),
            SizedBox(height: 8),
            Text('Add newsletter URLs in the Generate section', style: TextStyle(fontSize: 14, color: Colors.grey.shade600)),
          ],
        ),
      );
    }
    
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final weekAgo = now.subtract(Duration(days: 7));
    
    final todayNewsletters = <Map<String, dynamic>>[];
    final weekNewsletters = <Map<String, dynamic>>[];
    final monthNewsletters = <Map<String, dynamic>>[];
    
    for (final newsletter in newsletters) {
      try {
        final createdAt = DateTime.parse(newsletter['created_at'] ?? '');
        final createdDate = DateTime(createdAt.year, createdAt.month, createdAt.day);
        
        if (createdDate.isAtSameMomentAs(today)) {
          todayNewsletters.add(newsletter);
        } else if (createdAt.isAfter(weekAgo)) {
          weekNewsletters.add(newsletter);
        } else {
          monthNewsletters.add(newsletter);
        }
      } catch (e) {
        monthNewsletters.add(newsletter);
      }
    }
    
    return ListView(
      padding: EdgeInsets.all(16),
      children: [
        if (todayNewsletters.isNotEmpty) ..._buildSection('Today', todayNewsletters),
        if (weekNewsletters.isNotEmpty) ..._buildSection('This Week', weekNewsletters),
        if (monthNewsletters.isNotEmpty) ..._buildSection('This Month', monthNewsletters),
      ],
    );
  }
  
  List<Widget> _buildSection(String title, List<Map<String, dynamic>> newsletters) {
    return [
      Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text(
          title,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: Color(0xFF2c3e50),
          ),
        ),
      ),
      ...newsletters.map((newsletter) => _buildNewsletterCard(newsletter)),
      SizedBox(height: 16),
    ];
  }
  
  Widget _buildNewsletterCard(Map<String, dynamic> newsletter) {
    final name = newsletter['name'] ?? 'Unknown Newsletter';
    final url = newsletter['url'] ?? '';
    final createdAt = newsletter['created_at'] ?? '';
    final newsletterId = newsletter['id'] ?? 0;
    final articleCount = newsletter['article_count'] ?? 0;
    
    String dateStr = '';
    if (createdAt.isNotEmpty) {
      try {
        final date = DateTime.parse(createdAt);
        dateStr = '${date.month}/${date.day}/${date.year}';
      } catch (e) {
        dateStr = 'Unknown date';
      }
    }
    
    return Card(
      margin: EdgeInsets.only(bottom: 12),
      elevation: 2,
      child: ListTile(
        contentPadding: EdgeInsets.all(16),
        leading: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: Color(0xFF3498db),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(Icons.newspaper, color: Colors.white, size: 24),
        ),
        title: Text(
          name,
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: 4),
            Row(
              children: [
                Icon(Icons.calendar_today, size: 14, color: Colors.blue.shade600),
                SizedBox(width: 4),
                Text(
                  dateStr,
                  style: TextStyle(color: Colors.blue.shade600, fontSize: 12, fontWeight: FontWeight.w500),
                ),
                SizedBox(width: 12),
                Icon(Icons.article, size: 14, color: Colors.green.shade600),
                SizedBox(width: 4),
                Text(
                  '$articleCount articles',
                  style: TextStyle(color: Colors.green.shade600, fontSize: 12, fontWeight: FontWeight.w500),
                ),
              ],
            ),
            SizedBox(height: 4),
            Text(
              url,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 11),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
        trailing: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: Color(0xFF27ae60),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            icon: Icon(Icons.play_arrow, color: Colors.white, size: 24),
            onPressed: () => _processNewsletter(newsletterId, name),
          ),
        ),
        onTap: () => _processNewsletter(newsletterId, name),
      ),
    );
  }
  
  Color _getTypeColor(String type) {
    switch (type) {
      case 'News and Politics':
        return Colors.red.shade600;
      case 'Business and Investment':
        return Colors.green.shade600;
      case 'Technology':
        return Colors.blue.shade600;
      case 'Lifestyle and Entertainment':
        return Colors.purple.shade600;
      case 'Education and Learning':
        return Colors.orange.shade600;
      default:
        return Colors.grey.shade600;
    }
  }
}

class _TreatDetailView extends StatelessWidget {
  final Map<String, dynamic> treatData;

  const _TreatDetailView({
    required this.treatData,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(treatData['name'] ?? 'Treat'),
        actions: [
          if (treatData['link_to_vendor'] != null)
            IconButton(
              icon: Icon(Icons.open_in_browser),
              onPressed: () async {
                final url = treatData['link_to_vendor'];
                try {
                  final uri = Uri.parse(url);
                  await launchUrl(
                    uri,
                    mode: LaunchMode.externalApplication,
                  );
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Error opening link: $e')),
                  );
                }
              },
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: treatData['image_base64'] != null
                  ? InteractiveViewer(
                      child: Image.memory(
                        base64Decode(treatData['image_base64']),
                        fit: BoxFit.contain,
                      ),
                    )
                  : Icon(
                      Icons.local_cafe,
                      size: 100,
                      color: Colors.white54,
                    ),
            ),
          ),
          if (treatData['request_string'] != null && treatData['request_string'].isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              color: Colors.black87,
              child: Text(
                treatData['request_string'],
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
                textAlign: TextAlign.center,
              ),
            ),
        ],
      ),
    );
  }
}