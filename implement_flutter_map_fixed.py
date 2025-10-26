#!/usr/bin/env python3
"""
Script to implement Flutter Map in the AudioTours app
"""

def main():
    print("Implementing Flutter Map in AudioTours app...")
    
    # Create a new home page with Flutter Map
    home_page_code = '''import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class HomePage extends StatefulWidget {
  @override
  _HomePageState createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  MapController _mapController = MapController();
  LatLng? _userLocation;
  List<Marker> _tourMarkers = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _initializeMap();
  }

  Future<void> _initializeMap() async {
    await _getCurrentLocation();
    await _loadNearbyTours();
    setState(() {
      _isLoading = false;
    });
  }

  Future<void> _getCurrentLocation() async {
    try {
      // Request location permission
      var permission = await Permission.location.request();
      if (permission != PermissionStatus.granted) {
        print('Location permission denied');
        return;
      }

      // Get current position
      Position position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );

      setState(() {
        _userLocation = LatLng(position.latitude, position.longitude);
      });

      print('User location: ${position.latitude}, ${position.longitude}');
    } catch (e) {
      print('Error getting location: $e');
      // Default to Boston if location fails
      setState(() {
        _userLocation = LatLng(42.3601, -71.0589);
      });
    }
  }

  Future<void> _loadNearbyTours() async {
    if (_userLocation == null) return;

    try {
      final response = await http.get(
        Uri.parse('http://localhost:5005/tours-near/${_userLocation!.latitude}/${_userLocation!.longitude}?radius=50'),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = data['tours'] as List;

        setState(() {
          _tourMarkers = tours.map((tour) {
            return Marker(
              point: LatLng(tour['lat'], tour['lng']),
              width: 40,
              height: 40,
              child: GestureDetector(
                onTap: () => _onTourMarkerTapped(tour),
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.blue,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                  child: Icon(
                    Icons.tour,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
              ),
            );
          }).toList();
        });

        print('Loaded ${tours.length} nearby tours');
      }
    } catch (e) {
      print('Error loading tours: $e');
    }
  }

  void _onTourMarkerTapped(Map<String, dynamic> tour) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(tour['name']),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Distance: ${tour['distance_km']} km'),
            Text('Downloads: ${tour['popularity']}'),
            SizedBox(height: 10),
            Text(tour['request_string']),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Close'),
          ),
          ElevatedButton(
            onPressed: () => _downloadTour(tour['id']),
            child: Text('Download Tour'),
          ),
        ],
      ),
    );
  }

  Future<void> _downloadTour(int tourId) async {
    Navigator.pop(context); // Close dialog
    
    // Show loading
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Text('Downloading tour...'),
          ],
        ),
      ),
    );

    try {
      final response = await http.get(
        Uri.parse('http://localhost:5005/download-tour/$tourId'),
      );

      Navigator.pop(context); // Close loading dialog

      if (response.statusCode == 200) {
        // TODO: Save tour locally and add to My Tours
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Tour downloaded successfully!')),
        );
      } else {
        throw Exception('Failed to download tour');
      }
    } catch (e) {
      Navigator.pop(context); // Close loading dialog
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error downloading tour: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(title: Text('AudioTours')),
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('AudioTours'),
        backgroundColor: Colors.blue,
      ),
      body: FlutterMap(
        mapController: _mapController,
        options: MapOptions(
          initialCenter: _userLocation ?? LatLng(42.3601, -71.0589),
          initialZoom: 13.0,
        ),
        children: [
          // Base map tiles (free OpenStreetMap)
          TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.example.audiotours',
          ),
          
          // Tour markers
          MarkerLayer(markers: _tourMarkers),
          
          // User location marker
          if (_userLocation != null)
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
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          if (_userLocation != null) {
            _mapController.move(_userLocation!, 15.0);
          }
        },
        child: Icon(Icons.my_location),
      ),
    );
  }
}'''
    
    with open("home_page_flutter_map.dart", "w") as f:
        f.write(home_page_code)
    
    print("Created home_page_flutter_map.dart")
    print("Includes user location detection")
    print("Shows nearby tours as markers")
    print("Interactive tour download")
    print("Uses free OpenStreetMap tiles")

if __name__ == "__main__":
    main()