import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'subscription_encryption_service.dart';
import '../screens/debug_log_viewer_screen.dart';

class SubscriptionService {
  
  /// Submit encrypted credentials for subscription article
  static Future<bool> submitCredentials({
    required String articleId,
    required String username,
    required String password,
    required String deviceId,
    required String domain,
  }) async {
    try {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Starting credential submission for article: $articleId');
      
      // Encrypt credentials
      final encryptedCreds = await SubscriptionEncryptionService.encryptCredentials(username, password, domain);
      if (encryptedCreds == null) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Failed to encrypt credentials');
        return false;
      }
      
      // Get mobile public key for services decryption
      final mobilePublicKey = await SubscriptionEncryptionService.getClientPublicKey();
      if (mobilePublicKey == null) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: No mobile public key available');
        return false;
      }
      
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final url = 'http://$serverIp:5017/submit_credentials';
      
      final requestBody = {
        'article_id': articleId,
        'mobile_public_key': mobilePublicKey,
        'encrypted_username': encryptedCreds['encrypted_username'],
        'encrypted_password': encryptedCreds['encrypted_password'],
        'device_id': deviceId,
        'domain': encryptedCreds['domain'],
      };
      
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Submitting to: $url');
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Request body: ${json.encode(requestBody)}');
      
      final response = await http.post(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(requestBody),
      ).timeout(Duration(seconds: 30));
      
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Response status: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Response body: ${response.body}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final success = data['status'] == 'success';
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Credential submission ${success ? 'successful' : 'failed'}');
        return success;
      } else {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Server error: ${response.statusCode}');
        return false;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Exception during credential submission: $e');
      return false;
    }
  }
  
  /// Handle Diffie-Hellman key exchange with server
  static Future<void> handleKeyExchange(String? serverPublicKey) async {
    if (serverPublicKey != null && serverPublicKey.isNotEmpty) {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Performing Diffie-Hellman key exchange');
      
      final result = await SubscriptionEncryptionService.performKeyExchange(serverPublicKey);
      if (result != null) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Key exchange successful');
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Client public key: ${result['client_public_key']}');
      } else {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Key exchange failed');
      }
    }
  }
  
  /// Submit client public key to server for key exchange
  static Future<String?> submitPublicKey(String clientPublicKey, String deviceId) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final url = 'http://$serverIp:5017/key_exchange';
      
      final requestBody = {
        'device_id': deviceId,
        'client_public_key': clientPublicKey,
      };
      
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Submitting public key to: $url');
      
      final response = await http.post(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
        body: json.encode(requestBody),
      ).timeout(Duration(seconds: 30));
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data['server_public_key'];
      } else {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Key exchange server error: ${response.statusCode}');
        return null;
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Key exchange exception: $e');
      return null;
    }
  }
  
  /// Check if device has encryption key
  static Future<bool> hasEncryptionKey() async {
    return await SubscriptionEncryptionService.hasStoredKey();
  }
  
  /// Get Diffie-Hellman parameters
  static Map<String, String> getDHParameters() {
    return SubscriptionEncryptionService.getDiffieHellmanParameters();
  }
}