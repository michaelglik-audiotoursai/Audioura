import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

class TreatsScreen extends StatefulWidget {
  const TreatsScreen({super.key});

  @override
  State<TreatsScreen> createState() => _TreatsScreenState();
}

class _TreatsScreenState extends State<TreatsScreen> {
  List<Map<String, dynamic>> _treats = [];
  bool _isLoading = true;
  Position? _userPosition;

  @override
  void initState() {
    super.initState();
    _loadTreats();
  }

  Future<void> _loadTreats() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Check for custom location first
      final customLat = prefs.getDouble('custom_location_lat');
      final customLng = prefs.getDouble('custom_location_lng');
      
      double searchLat, searchLng;
      
      if (customLat != null && customLng != null) {
        // Use custom location
        searchLat = customLat;
        searchLng = customLng;
      } else {
        // Use current location
        _userPosition = await Geolocator.getCurrentPosition();
        searchLat = _userPosition!.latitude;
        searchLng = _userPosition!.longitude;
      }
      
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      final response = await http.get(
        Uri.parse('http://$serverIp:5007/treats-near/$searchLat/$searchLng'),
        headers: {'Content-Type': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final treats = data['treats'] as List;
        
        setState(() {
          _treats = treats.cast<Map<String, dynamic>>();
          _isLoading = false;
        });
      }
    } catch (e) {
      print('Error loading treats: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  double _calculateDistance(double lat1, double lng1, double lat2, double lng2) {
    const double earthRadius = 6371; // km
    final double dLat = _degreesToRadians(lat2 - lat1);
    final double dLng = _degreesToRadians(lng2 - lng1);
    final double a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_degreesToRadians(lat1)) * cos(_degreesToRadians(lat2)) *
        sin(dLng / 2) * sin(dLng / 2);
    final double c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  double _degreesToRadians(double degrees) {
    return degrees * (pi / 180);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🍰 Treats'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadTreats,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _treats.isEmpty
              ? const Center(
                  child: Text(
                    'No treats available',
                    style: TextStyle(fontSize: 18, color: Colors.grey),
                  ),
                )
              : ListView.builder(
                  itemCount: _treats.length,
                  itemBuilder: (context, index) {
                    final treat = _treats[index];
                    final hasCoords = treat['lat'] != null && treat['lng'] != null;
                    
                    return Card(
                      margin: const EdgeInsets.all(8),
                      child: ListTile(
                        leading: treat['image_base64'] != null
                            ? Container(
                                width: 50,
                                height: 50,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(8),
                                  image: DecorationImage(
                                    image: MemoryImage(
                                      base64Decode(treat['image_base64']),
                                    ),
                                    fit: BoxFit.cover,
                                  ),
                                ),
                              )
                            : Icon(
                                Icons.local_cafe,
                                color: hasCoords ? Colors.green : Colors.grey,
                                size: 32,
                              ),
                        title: GestureDetector(
                          onTap: () async {
                            final url = treat['link_to_vendor'];
                            if (url != null && url.isNotEmpty) {
                              try {
                                final uri = Uri.parse(url);
                                await launchUrl(
                                  uri,
                                  mode: LaunchMode.externalApplication,
                                  webViewConfiguration: const WebViewConfiguration(
                                    enableJavaScript: true,
                                  ),
                                );
                              } catch (e) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('Error opening link: $e')),
                                );
                              }
                            }
                          },
                          child: Text(
                            treat['name'] ?? 'Unknown Treat',
                            style: TextStyle(
                              color: treat['link_to_vendor'] != null ? Colors.blue : null,
                              decoration: treat['link_to_vendor'] != null ? TextDecoration.underline : null,
                            ),
                          ),
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (treat['description'] != null)
                              Text(
                                treat['description'],
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            const SizedBox(height: 4),
                            if (hasCoords && treat['distance_km'] != null)
                              Text(
                                '${treat['distance_km'].toStringAsFixed(1)} km away',
                                style: const TextStyle(
                                  color: Colors.blue,
                                  fontWeight: FontWeight.w500,
                                ),
                              )
                            else
                              const Text(
                                'Location not available',
                                style: TextStyle(color: Colors.grey),
                              ),
                          ],
                        ),
                        trailing: const Icon(Icons.arrow_forward_ios),
                        onTap: () {
                          if (treat['image_base64'] != null) {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => _FullScreenImageView(
                                  imageBase64: treat['image_base64'],
                                  title: treat['name'] ?? 'Treat',
                                  description: treat['description'] ?? '',
                                ),
                              ),
                            );
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('No image available for ${treat['name']}'),
                              ),
                            );
                          }
                        },
                      ),
                    );
                  },
                ),
    );
  }
}

class _FullScreenImageView extends StatelessWidget {
  final String imageBase64;
  final String title;
  final String description;

  const _FullScreenImageView({
    required this.imageBase64,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(title),
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: InteractiveViewer(
                child: Image.memory(
                  base64Decode(imageBase64),
                  fit: BoxFit.contain,
                ),
              ),
            ),
          ),
          if (description.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              color: Colors.black87,
              child: Text(
                description,
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