import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class MapService {
  static const String baseUrl = 'http://map_delivery:5005';
  
  // Get nearby tours within a radius (in miles)
  static Future<List<Map<String, dynamic>>> getNearbyTours(double lat, double lng, double radius) async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/nearby-tours?lat=$lat&lng=$lng&radius=$radius'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return List<Map<String, dynamic>>.from(data['tours'] ?? []);
      } else {
        print('Error fetching nearby tours: ${response.statusCode} - ${response.body}');
        return [];
      }
    } catch (e) {
      print('Exception fetching nearby tours: $e');
      return [];
    }
  }
  
  // Add a tour to the user's saved tours
  static Future<bool> addTourToSaved(Map<String, dynamic> tour) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedTours = prefs.getStringList('saved_tours') ?? [];
      
      // Create a new tour entry
      final newTour = {
        'title': tour['title'],
        'path': tour['path'] ?? '',
        'stops': tour['stops'] ?? 10,
        'created': DateTime.now().toIso8601String(),
        'original_request': tour['request_string'] ?? tour['title'],
        'lat': tour['lat'],
        'lng': tour['lng'],
      };
      
      // Add to saved tours
      savedTours.add(json.encode(newTour));
      await prefs.setStringList('saved_tours', savedTours);
      
      return true;
    } catch (e) {
      print('Error adding tour to saved: $e');
      return false;
    }
  }
  
  // Get default location (Boston Town Hall)
  static Map<String, double> getDefaultLocation() {
    return {'lat': 42.3601, 'lng': -71.0589}; // Boston Town Hall coordinates
  }
  
  // Get user's saved location
  static Future<Map<String, double>?> getSavedLocation() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final lat = prefs.getDouble('user_lat');
      final lng = prefs.getDouble('user_lng');
      
      if (lat != null && lng != null) {
        return {'lat': lat, 'lng': lng};
      }
      return null;
    } catch (e) {
      print('Error getting saved location: $e');
      return null;
    }
  }
  
  // Save user's location
  static Future<bool> saveUserLocation(double lat, double lng) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setDouble('user_lat', lat);
      await prefs.setDouble('user_lng', lng);
      return true;
    } catch (e) {
      print('Error saving user location: $e');
      return false;
    }
  }
}