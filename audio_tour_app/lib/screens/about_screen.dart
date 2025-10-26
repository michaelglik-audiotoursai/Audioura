import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geolocator/geolocator.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'dart:convert';

import 'debug_log_viewer_screen.dart';

class AboutScreen extends StatefulWidget {
  const AboutScreen({super.key});

  @override
  State<AboutScreen> createState() => _AboutScreenState();
}

class _AboutScreenState extends State<AboutScreen> {
  String _appVersion = 'Loading...';
  String _buildNumber = 'Loading...';
  String _userId = 'Loading...';
  String _deviceModel = 'Loading...';
  String _androidVersion = 'Loading...';
  final TextEditingController _serverIpController = TextEditingController();
  String _currentServerIp = '192.168.0.217';
  String _selectedMode = 'Tours'; // Default to Tours

  @override
  void initState() {
    super.initState();
    _loadAppInfo();
    _loadSelectedMode();
  }
  
  Future<void> _loadSelectedMode() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _selectedMode = prefs.getString('app_mode') ?? 'Tours';
    });
  }
  
  Future<void> _saveSelectedMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('app_mode', mode);
    setState(() {
      _selectedMode = mode;
    });
  }

  Future<void> _loadAppInfo() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      final prefs = await SharedPreferences.getInstance();
      
      // Get or create user ID
      String? userId = prefs.getString('user_id');
      if (userId == null) {
        final deviceInfo = DeviceInfoPlugin();
        final androidInfo = await deviceInfo.androidInfo;
        userId = _generateUserId(androidInfo);
        await prefs.setString('user_id', userId);
      }
      
      final deviceInfo = DeviceInfoPlugin();
      final androidInfo = await deviceInfo.androidInfo;
      
      // Load saved server IP
      final savedIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await DebugLogHelper.addDebugLog('Checking user: $userId');
      
      // Test server connectivity
      await _testServerConnectivity();
      
      setState(() {
        _appVersion = packageInfo.version;
        _buildNumber = packageInfo.buildNumber;
        _userId = userId!;
        _deviceModel = '${androidInfo.brand} ${androidInfo.model}';
        _androidVersion = 'Android ${androidInfo.version.release}';
        _currentServerIp = savedIp;
        _serverIpController.text = savedIp;
      });
    } catch (e) {
      setState(() {
        _appVersion = 'Error loading';
        _buildNumber = 'Error loading';
        _userId = 'Error loading';
        _deviceModel = 'Error loading';
        _androidVersion = 'Error loading';
      });
    }
  }

  String _generateUserId(AndroidDeviceInfo androidInfo) {
    final deviceId = '${androidInfo.brand}-${androidInfo.model}-${androidInfo.id}'.hashCode.abs();
    return 'USER-${deviceId.toString().padLeft(8, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ℹ️ About'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.blue.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.apps, size: 30, color: Colors.blue),
                      SizedBox(width: 10),
                      Text(
                        'Audio Tour Generator',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                          color: Colors.blue,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  _buildInfoRow('Version', _appVersion),
                  _buildInfoRow('Build', _buildNumber),
                  _buildInfoRow('User ID', _userId),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      const Text(
                        'Server IP:',
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextField(
                          controller: _serverIpController,
                          decoration: const InputDecoration(
                            hintText: '192.168.0.217',
                            border: OutlineInputBorder(),
                            contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          ),
                          style: const TextStyle(fontSize: 12),
                        ),
                      ),
                      const SizedBox(width: 10),
                      ElevatedButton(
                        onPressed: _saveServerIp,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        ),
                        child: const Text('Save', style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.settings, size: 30, color: Colors.orange),
                      SizedBox(width: 10),
                      Text(
                        'Application Mode',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.orange,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  Row(
                    children: [
                      Radio<String>(
                        value: 'Tours',
                        groupValue: _selectedMode,
                        onChanged: (value) => _saveSelectedMode(value!),
                      ),
                      const Text('Tours'),
                      const SizedBox(width: 30),
                      Radio<String>(
                        value: 'Audio',
                        groupValue: _selectedMode,
                        onChanged: (value) => _saveSelectedMode(value!),
                      ),
                      const Text('Audio'),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.phone_android, size: 30, color: Colors.green),
                      SizedBox(width: 10),
                      Text(
                        'Device Information',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.green,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  _buildInfoRow('Device', _deviceModel),
                  _buildInfoRow('OS', _androidVersion),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Column(
              children: [
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _syncUserToDatabase,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3498db),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: const Text('Sync User to Database'),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _viewDebugLogs,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF27ae60),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                    ),
                    child: const Text('View Debug Logs'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 30),
            Center(
              child: Text(
                '© 2024 Audio Tour Generator\nPowered by AI',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey.shade600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _syncUserToDatabase() async {
    try {
      await DebugLogHelper.addDebugLog('Starting user sync: $_userId');
      
      final prefs = await SharedPreferences.getInstance();
      String? userId = prefs.getString('user_id');
      
      if (userId == null) {
        userId = 'USER-${DateTime.now().millisecondsSinceEpoch}';
        await prefs.setString('user_id', userId);
      }
      
      // Get current location
      Position? position;
      try {
        position = await Geolocator.getCurrentPosition();
        await DebugLogHelper.addDebugLog('Got location: ${position.latitude}, ${position.longitude}');
      } catch (e) {
        await DebugLogHelper.addDebugLog('Location error: $e');
      }
      
      // Use the correct user-api service on port 5003
      final userData = {
        'user_id': userId,
        'created_at': DateTime.now().toIso8601String(),
        'latitude': position?.latitude,
        'longitude': position?.longitude,
        'app_version': _appVersion,
        'build_number': _buildNumber,
      };
      
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/user'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'secret_id': userId,
          'app_version': '$_appVersion+$_buildNumber',
          'coordinates': {
            'lat': position?.latitude,
            'lng': position?.longitude,
          }
        }),
      );
      
      await DebugLogHelper.addDebugLog('Sync response: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('Sync body: ${response.body}');
      
      if (response.statusCode == 200 || response.statusCode == 201) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('User synced to database successfully!'),
            backgroundColor: Colors.green,
          ),
        );
      } else if (response.statusCode == 409) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('User already exists in database'),
            backgroundColor: Colors.blue,
          ),
        );
      } else {
        throw Exception('Server returned ${response.statusCode}: ${response.body}');
      }
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('Sync error: $e');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Sync failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _viewDebugLogs() async {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const DebugLogViewerScreen(),
      ),
    );
  }
  


  Future<void> _saveServerIp() async {
    final newIp = _serverIpController.text.trim();
    if (newIp.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter a valid IP address'),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_ip', newIp);
    
    setState(() {
      _currentServerIp = newIp;
    });
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Server IP updated to: $newIp'),
        backgroundColor: Colors.green,
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 80,
            child: Text(
              '$label:',
              style: const TextStyle(
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 14,
                fontFamily: 'monospace',
              ),
            ),
          ),
        ],
      ),
    );
  }
  

  
  Future<void> _testServerConnectivity() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      
      await DebugLogHelper.addDebugLog('Testing connectivity to: $serverIp');
      
      final response = await http.get(
        Uri.parse('http://$serverIp:5003/health'),
      ).timeout(Duration(seconds: 5));
      
      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('✅ Server connectivity: OK');
      } else {
        await DebugLogHelper.addDebugLog('❌ Server connectivity: HTTP ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('❌ Server connectivity: FAILED - $e');
    }
  }

  @override
  void dispose() {
    _serverIpController.dispose();
    super.dispose();
  }
}