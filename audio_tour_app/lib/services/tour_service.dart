import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

class TourService {
  static Future<List<Map<String, dynamic>>> getNearbyTours(double lat, double lng) async {
    final response = await http.get(
      Uri.parse('${ApiConfig.baseUrl}/tours/nearby?lat=$lat&lng=$lng'),
    );
    
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(json.decode(response.body));
    }
    throw Exception('Failed to load nearby tours');
  }
  
  static Future<List<Map<String, dynamic>>> getPopularTours() async {
    final response = await http.get(
      Uri.parse('${ApiConfig.baseUrl}/tours/popular'),
    );
    
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(json.decode(response.body));
    }
    throw Exception('Failed to load popular tours');
  }
  
  static Future<void> downloadTour(String tourId) async {
    // Mock download - in real app, save to local storage
    await Future.delayed(Duration(seconds: 1));
    print('Downloaded tour: $tourId');
  }
}