import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geolocator/geolocator.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:convert';
import 'dart:io' show Platform, Directory;

import 'debug_log_viewer_screen.dart';
import '../config/endpoints.dart';

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
  final TextEditingController _cloudBaseUrlController = TextEditingController();
  final TextEditingController _apiKeyController = TextEditingController();
  String _currentServerIp = '192.168.0.218';
  String _serverMode = 'local';
  bool _usePathPrefixes = false;
  String _selectedMode = 'Tours';

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
        if (kIsWeb) {
          userId = 'WEB-USER-${DateTime.now().millisecondsSinceEpoch}';
        } else if (Platform.isAndroid) {
          final deviceInfo = DeviceInfoPlugin();
          final androidInfo = await deviceInfo.androidInfo;
          userId = _generateUserId(androidInfo);
        } else if (Platform.isIOS) {
          final deviceInfo = DeviceInfoPlugin();
          final iosInfo = await deviceInfo.iosInfo;
          userId = _generateUserId(iosInfo);
        } else {
          userId = 'UNKNOWN-USER-${DateTime.now().millisecondsSinceEpoch}';
        }
        await prefs.setString('user_id', userId);
      }
      
      // Load saved server IP and cloud settings
      final savedIp = prefs.getString('server_ip') ?? '192.168.0.218';
      final savedServerMode = prefs.getString('server_mode') ?? 'local';
      final savedCloudBaseUrl = prefs.getString('cloud_base_url') ?? '';
      final savedUsePathPrefixes = prefs.getBool('cloud_use_path_prefixes') ?? false;
      final savedApiKey = prefs.getString('gateway_api_key') ?? '';
      
      await DebugLogHelper.addDebugLog('ABOUT: Checking user: $userId');
      
      // Test server connectivity
      await _testServerConnectivity();
      
      // Platform-specific device info
      String deviceModel = 'Unknown Device';
      String osVersion = 'Unknown OS';
      
      if (kIsWeb) {
        deviceModel = 'Web Browser';
        osVersion = 'Web Platform';
      } else if (Platform.isAndroid) {
        final deviceInfo = DeviceInfoPlugin();
        final androidInfo = await deviceInfo.androidInfo;
        deviceModel = '${androidInfo.brand} ${androidInfo.model}';
        osVersion = 'Android ${androidInfo.version.release}';
      } else if (Platform.isIOS) {
        final deviceInfo = DeviceInfoPlugin();
        final iosInfo = await deviceInfo.iosInfo;
        deviceModel = '${iosInfo.name} ${iosInfo.model}';
        osVersion = 'iOS ${iosInfo.systemVersion}';
      }
      
      setState(() {
        _appVersion = packageInfo.version;
        _buildNumber = packageInfo.buildNumber;
        _userId = userId!;
        _deviceModel = deviceModel;
        _androidVersion = osVersion;
        _currentServerIp = savedIp;
        _serverIpController.text = savedIp;
        _serverMode = savedServerMode;
        _cloudBaseUrlController.text = savedCloudBaseUrl;
        _usePathPrefixes = savedUsePathPrefixes;
        _apiKeyController.text = savedApiKey;
      });
    } catch (e) {
      await DebugLogHelper.addDebugLog('ABOUT: Error loading app info: $e');
      setState(() {
        _appVersion = 'Error loading';
        _buildNumber = 'Error loading';
        _userId = 'Error loading';
        _deviceModel = 'Error loading';
        _androidVersion = 'Error loading';
      });
    }
  }

  String _generateUserId(dynamic deviceInfo) {
    String deviceId;
    if (Platform.isAndroid) {
      deviceId = '${deviceInfo.brand}-${deviceInfo.model}-${deviceInfo.id}'.hashCode.abs().toString();
    } else if (Platform.isIOS) {
      deviceId = '${deviceInfo.name}-${deviceInfo.model}-${deviceInfo.identifierForVendor}'.hashCode.abs().toString();
    } else {
      deviceId = 'WEB-${DateTime.now().millisecondsSinceEpoch}';
    }
    return 'USER-${deviceId.padLeft(8, '0')}';
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
                  // Server mode toggle
                  Row(
                    children: [
                      const Text('Mode:', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                      const SizedBox(width: 10),
                      ChoiceChip(
                        label: const Text('Local WiFi'),
                        selected: _serverMode == 'local',
                        onSelected: (_) => _setServerMode('local'),
                      ),
                      const SizedBox(width: 8),
                      ChoiceChip(
                        label: const Text('Cloud'),
                        selected: _serverMode == 'cloud',
                        selectedColor: Colors.green.shade100,
                        onSelected: (_) => _setServerMode('cloud'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  // Local IP field — shown in local mode
                  if (_serverMode == 'local') Row(
                    children: [
                      const Text(
                        'Server IP:',
                        style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextField(
                          controller: _serverIpController,
                          decoration: const InputDecoration(
                            hintText: '192.168.0.218',
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
                  // Cloud base URL field — shown in cloud mode
                  if (_serverMode == 'cloud') Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Cloud Base URL:',
                        style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _cloudBaseUrlController,
                              decoration: const InputDecoration(
                                hintText: 'https://api.audioura.com',
                                border: OutlineInputBorder(),
                                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                helperText: 'Gateway: https://api.audioura.com',
                              ),
                              style: const TextStyle(fontSize: 12),
                            ),
                          ),
                          const SizedBox(width: 10),
                          ElevatedButton(
                            onPressed: _saveCloudBaseUrl,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.green,
                              foregroundColor: Colors.white,
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            ),
                            child: const Text('Save', style: TextStyle(fontSize: 12)),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        '✅ Cloud mode: tour generation and map delivery live at api.audioura.com. News/newsletters remain local until deployed.',
                        style: TextStyle(fontSize: 11, color: Colors.green),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'API Key:',
                        style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                      ),
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _apiKeyController,
                              obscureText: true,
                              decoration: const InputDecoration(
                                hintText: 'Gateway API key',
                                border: OutlineInputBorder(),
                                contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              ),
                              style: const TextStyle(fontSize: 12),
                            ),
                          ),
                          const SizedBox(width: 10),
                          ElevatedButton(
                            onPressed: _saveApiKey,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.green,
                              foregroundColor: Colors.white,
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            ),
                            child: const Text('Save', style: TextStyle(fontSize: 12)),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Required for cloud generation. Never share or commit this key.',
                        style: TextStyle(fontSize: 11, color: Colors.orange),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Checkbox(
                            value: _usePathPrefixes,
                            onChanged: (val) => _setUsePathPrefixes(val ?? false),
                          ),
                          const Expanded(
                            child: Text(
                              'Use gateway path routing (leave unchecked — api.audioura.com routes by root path)',
                              style: TextStyle(fontSize: 12),
                            ),
                          ),
                        ],
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
            // Account Deletion — App Store / Play Store requirement
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.red.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.warning_amber, size: 30, color: Colors.red),
                      SizedBox(width: 10),
                      Text(
                        'Danger Zone',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Colors.red,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Permanently delete your account and all associated data from our servers. Downloaded tours and articles on this device will also be removed.',
                    style: TextStyle(fontSize: 13),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _confirmDeleteAccount,
                      icon: const Icon(Icons.delete_forever),
                      label: const Text('Delete My Account'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.red,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                ],
              ),
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
      
      final userUri = await Endpoints.url(Service.userDb, '/user');
      final response = await http.post(
        userUri,
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
  


  Future<void> _saveApiKey() async {
    final key = _apiKeyController.text.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('gateway_api_key', key);
    await DebugLogHelper.addDebugLog('ABOUT: API key saved (${key.isEmpty ? "cleared" : "set"})');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(key.isEmpty ? 'API key cleared' : 'API key saved'),
        backgroundColor: Colors.green,
      ),
    );
  }

  Future<void> _setUsePathPrefixes(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('cloud_use_path_prefixes', value);
    setState(() { _usePathPrefixes = value; });
    await DebugLogHelper.addDebugLog('ABOUT: Gateway path routing set to: $value');
  }

  Future<void> _setServerMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('server_mode', mode);
    setState(() { _serverMode = mode; });
    await DebugLogHelper.addDebugLog('ABOUT: Server mode set to: $mode');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Switched to ${mode == 'cloud' ? 'Cloud' : 'Local WiFi'} mode'),
        backgroundColor: mode == 'cloud' ? Colors.green : Colors.blue,
      ),
    );
  }

  Future<void> _saveCloudBaseUrl() async {
    final url = _cloudBaseUrlController.text.trim();
    if (url.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter a cloud base URL'), backgroundColor: Colors.red),
      );
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('cloud_base_url', url);
    await DebugLogHelper.addDebugLog('ABOUT: Cloud base URL saved: $url');
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Cloud base URL saved: $url'), backgroundColor: Colors.green),
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
    
    await DebugLogHelper.addDebugLog('ABOUT: Server IP saved to: $newIp');
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Server IP updated to: $newIp'),
        backgroundColor: Colors.green,
      ),
    );
    
    // Reload app info to refresh the display
    await _loadAppInfo();
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
      final uri = await Endpoints.url(Service.userDb, '/health');
      await DebugLogHelper.addDebugLog('Testing connectivity to: $uri');
      final response = await http.get(uri).timeout(Duration(seconds: 5));
      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('✅ Server connectivity: OK');
      } else {
        await DebugLogHelper.addDebugLog('❌ Server connectivity: HTTP ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('❌ Server connectivity: FAILED - $e');
    }
  }

  Future<void> _confirmDeleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Account?'),
        content: const Text(
          'This will permanently delete your account and all data from our servers. '
          'All downloaded tours and articles on this device will also be removed.\n\n'
          'This action cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
              foregroundColor: Colors.white,
            ),
            child: const Text('Delete Permanently'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await _deleteAccount();
    }
  }

  Future<void> _deleteAccount() async {
    try {
      // Q3 fix: re-read user_id from prefs right before the call — don't use stale _userId
      final prefs = await SharedPreferences.getInstance();
      final currentUserId = prefs.getString('user_id') ?? '';
      if (currentUserId.isEmpty || currentUserId.startsWith('Error')) {
        await DebugLogHelper.addDebugLog('ACCOUNT: Aborting — user_id is empty or invalid: "$currentUserId"');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Cannot delete: no valid user ID found.'), backgroundColor: Colors.red),
          );
        }
        return;
      }

      // Warn if in local mode — deletion hits dev server, not production
      final serverMode = prefs.getString('server_mode') ?? 'local';
      if (serverMode == 'local') {
        final proceedLocal = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Local Mode Warning'),
            content: const Text(
              'You are in Local WiFi mode. This will delete your account from the LOCAL development server, not the production cloud.\n\n'
              'Switch to Cloud mode first if you want to delete your production account.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Cancel'),
              ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Delete from local anyway'),
              ),
            ],
          ),
        );
        if (proceedLocal != true) return;
      }

      await DebugLogHelper.addDebugLog('ACCOUNT: Starting account deletion for $currentUserId');

      // Call server deletion endpoint
      final uri = await Endpoints.url(Service.orchestrator, '/delete-account/$currentUserId');
      final headers = await Endpoints.apiHeaders(Service.orchestrator);
      final response = await http.delete(uri, headers: headers).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('ACCOUNT: Server deletion successful: ${response.body}');
      } else if (response.statusCode == 400) {
        await DebugLogHelper.addDebugLog('ACCOUNT: Server returned 400: ${response.body}');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Invalid request. Please try again.'), backgroundColor: Colors.red),
          );
        }
        return;
      } else {
        await DebugLogHelper.addDebugLog('ACCOUNT: Server deletion failed: ${response.statusCode} ${response.body}');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Server error (${response.statusCode}). Data preserved.'), backgroundColor: Colors.red),
          );
        }
        return;
      }

      // Server succeeded — now wipe local data
      await _wipeLocalData();

      // Q2 fix: close the app entirely. On next launch, initState re-runs from scratch,
      // SharedPreferences is empty, and a new user_id is generated.
      // Note: _generateUserId is deterministic from device hardware, so the same device
      // will get the same user_id — that's fine, the server record is gone.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Account deleted. App will close.'), backgroundColor: Colors.green),
        );
        // Give the snackbar time to show, then exit
        await Future.delayed(const Duration(seconds: 2));
        SystemNavigator.pop();
      }
    } on Exception catch (e) {
      await DebugLogHelper.addDebugLog('ACCOUNT: Deletion error: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not connect to server. Data preserved.\n$e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _wipeLocalData() async {
    final prefs = await SharedPreferences.getInstance();
    // Q1 fix: log before clear
    await DebugLogHelper.addDebugLog('ACCOUNT: Wiping local data (tours + news + prefs)...');
    await prefs.clear();

    // Delete local tours directory
    try {
      final docsDir = await getApplicationDocumentsDirectory();
      final toursDir = Directory('${docsDir.path}/tours');
      if (await toursDir.exists()) {
        await toursDir.delete(recursive: true);
      }
      final newsDir = Directory('${docsDir.path}/news');
      if (await newsDir.exists()) {
        await newsDir.delete(recursive: true);
      }
    } catch (e) {
      // Best-effort — files may be locked; they'll be orphaned but not harmful
      await DebugLogHelper.addDebugLog('ACCOUNT: Error deleting local files: $e');
    }
  }

  @override
  void dispose() {
    _serverIpController.dispose();
    _cloudBaseUrlController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }
}