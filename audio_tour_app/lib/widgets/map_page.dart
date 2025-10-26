import 'package:flutter/material.dart';
import 'package:mapbox_gl/mapbox_gl.dart';
import '../services/tour_service.dart';

class MapPage extends StatefulWidget {
  @override
  _MapPageState createState() => _MapPageState();
}

class _MapPageState extends State<MapPage> {
  MapboxMapController? mapController;
  List<Map<String, dynamic>> tours = [];

  @override
  void initState() {
    super.initState();
    _loadPopularTours();
  }

  void _onMapCreated(MapboxMapController controller) {
    mapController = controller;
    _addTourMarkers();
  }

  Future<void> _loadPopularTours() async {
    try {
      final popularTours = await TourService.getPopularTours();
      setState(() {
        tours = popularTours;
      });
      _addTourMarkers();
    } catch (e) {
      print('Error loading tours: $e');
    }
  }

  void _addTourMarkers() {
    if (mapController == null) return;
    
    for (var tour in tours) {
      mapController!.addSymbol(SymbolOptions(
        geometry: LatLng(tour['latitude'], tour['longitude']),
        iconImage: _getIconForType(tour['type']),
        iconSize: 1.5,
        textField: tour['title'],
        textOffset: Offset(0, 2),
      ));
    }
  }

  String _getIconForType(String type) {
    switch (type) {
      case 'museum': return 'frame';
      case 'bike': return 'bicycle';
      case 'auto': return 'car';
      default: return 'marker';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          MapboxMap(
            accessToken: 'YOUR_MAPBOX_TOKEN',
            onMapCreated: _onMapCreated,
            initialCameraPosition: CameraPosition(
              target: LatLng(40.7589, -73.9851),
              zoom: 12.0,
            ),
            onMapClick: (point, latLng) => _onMapTap(latLng),
          ),
          Positioned(
            top: 50,
            left: 20,
            right: 20,
            child: Container(
              padding: EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [BoxShadow(blurRadius: 4, color: Colors.black26)],
              ),
              child: Text(
                'Please click on the most popular tours',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _onMapTap(LatLng latLng) {
    var nearestTour = _findNearestTour(latLng);
    if (nearestTour != null) {
      _showTourDialog(nearestTour);
    }
  }

  Map<String, dynamic>? _findNearestTour(LatLng tapPoint) {
    double minDistance = double.infinity;
    Map<String, dynamic>? nearest;
    
    for (var tour in tours) {
      double distance = _calculateDistance(
        tapPoint.latitude, tapPoint.longitude,
        tour['latitude'], tour['longitude']
      );
      if (distance < minDistance && distance < 0.01) {
        minDistance = distance;
        nearest = tour;
      }
    }
    return nearest;
  }

  double _calculateDistance(double lat1, double lon1, double lat2, double lon2) {
    return ((lat1 - lat2).abs() + (lon1 - lon2).abs());
  }

  void _showTourDialog(Map<String, dynamic> tour) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(tour['title']),
        content: Text('Download this tour to My Tours?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              await TourService.downloadTour(tour['id']);
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Tour downloaded!')),
              );
            },
            child: Text('Download'),
          ),
        ],
      ),
    );
  }
}