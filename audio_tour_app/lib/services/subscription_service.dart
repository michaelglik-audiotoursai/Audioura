import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'subscription_encryption_service.dart';
import 'credential_storage_service.dart';
import 'subscription_article_storage.dart';
import '../screens/debug_log_viewer_screen.dart';

class CredentialResponse {
  final String status;
  final String message;
  final int? reprocessedArticles;
  final bool refreshRequired;
  final String? articleId;
  final String? articleTitle;
  final String? subscriptionDomain;
  
  CredentialResponse({
    required this.status,
    required this.message,
    this.reprocessedArticles,
    this.refreshRequired = false,
    this.articleId,
    this.articleTitle,
    this.subscriptionDomain,
  });
  
  factory CredentialResponse.fromJson(Map<String, dynamic> json) {
    return CredentialResponse(
      status: json['status'] ?? '',
      message: json['message'] ?? '',
      reprocessedArticles: json['reprocessed_articles'],
      refreshRequired: json['refresh_required'] ?? false,
      articleId: json['article_id'],
      articleTitle: json['article_title'],
      subscriptionDomain: json['subscription_domain'],
    );
  }
}

class SubscriptionService {
  
  /// Submit encrypted credentials for subscription article
  static Future<CredentialResponse?> submitCredentials({
    required String articleId,
    required String username,
    required String password,
    required String deviceId,
    required String domain,
    int? newsletterId, // Add newsletter_id parameter for consistency
  }) async {
    try {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Starting credential submission for article: $articleId');
      
      // Encrypt credentials (GitHub approach - no pre-check)
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: About to call encryptCredentials');
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Calling SubscriptionEncryptionService.encryptCredentials with username="$username", password="$password", domain="$domain"');
      
      // Test if the class and method exist
      try {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Testing class accessibility...');
        final testResult = await SubscriptionEncryptionService.testMethod();
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Test method result: $testResult');
        
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Testing encryptCredentials method call...');
        final encryptedCreds = await SubscriptionEncryptionService.encryptCredentials(username, password, domain);
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: encryptCredentials returned: ${encryptedCreds != null}');
        if (encryptedCreds != null) {
          await DebugLogHelper.addDebugLog('SUBSCRIPTION: Encryption successful, keys: ${encryptedCreds.keys.toList()}');
        }
      } catch (e, stackTrace) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: CRITICAL ERROR calling encryptCredentials: $e');
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Stack trace: $stackTrace');
        return CredentialResponse(
          status: 'error',
          message: 'Encryption method failed: $e',
        );
      }
      
      final encryptedCreds = await SubscriptionEncryptionService.encryptCredentials(username, password, domain);
      if (encryptedCreds == null) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Failed to encrypt credentials');
        return CredentialResponse(
          status: 'error',
          message: 'Failed to encrypt credentials. Please try again.',
        );
      }
      
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Credentials encrypted successfully');
      
      // Get mobile public key for services decryption
      final mobilePublicKey = await SubscriptionEncryptionService.getClientPublicKey();
      if (mobilePublicKey == null) {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: No mobile public key available');
        return null;
      }
      
      final prefs = await SharedPreferences.getInstance();
      final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
      final url = 'http://$serverIp:5017/submit_credentials';
      
      final requestBody = <String, dynamic>{
        'article_id': articleId,
        'mobile_public_key': mobilePublicKey,
        'encrypted_username': encryptedCreds['encrypted_username'],
        'encrypted_password': encryptedCreds['encrypted_password'],
        'device_id': deviceId,
        'domain': encryptedCreds['domain'],
      };
      
      // Include newsletter_id for consistent key usage (Services fix)
      if (newsletterId != null) {
        requestBody['newsletter_id'] = newsletterId;
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Including newsletter_id: $newsletterId for consistent decryption');
      }
      
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
        final credentialResponse = CredentialResponse.fromJson(data);
        
        // Phase 3: Store credentials locally if successful
        if (credentialResponse.status == 'success') {
          await CredentialStorageService.storeCredentials(
            domain: domain,
            username: username,
            password: password,
          );
          await DebugLogHelper.addDebugLog('SUBSCRIPTION: Credentials stored locally for domain: $domain');
        }
        
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Credential submission ${credentialResponse.status == 'success' ? 'successful' : 'failed'}');
        return credentialResponse;
      } else {
        await DebugLogHelper.addDebugLog('SUBSCRIPTION: Server error: ${response.statusCode}');
        return CredentialResponse(
          status: 'error',
          message: 'Server error: ${response.statusCode}',
        );
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUBSCRIPTION: Exception during credential submission: $e');
      return null;
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
  
  /// Phase 3: Check if article is available locally
  static Future<bool> isArticleStoredLocally(String articleId) async {
    return await SubscriptionArticleStorage.isArticleStored(articleId);
  }
  
  /// Phase 3: Get stored article path for offline access
  static Future<String?> getStoredArticlePath(String articleId) async {
    return await SubscriptionArticleStorage.getArticlePath(articleId);
  }
  
  /// Phase 3: Store subscription article after successful download
  static Future<bool> storeSubscriptionArticle({
    required String articleId,
    required String title,
    required String domain,
    required List<int> zipBytes,
    required String author,
    required String articleType,
  }) async {
    return await SubscriptionArticleStorage.storeArticle(
      articleId: articleId,
      title: title,
      domain: domain,
      zipBytes: zipBytes,
      author: author,
      articleType: articleType,
    );
  }
  
  /// Phase 3: Get stored credentials for auto-retry
  static Future<Map<String, String>?> getStoredCredentials(String domain) async {
    return await CredentialStorageService.getCredentials(domain);
  }
  
  /// Phase 3: Check if credentials exist for domain
  static Future<bool> hasStoredCredentials(String domain) async {
    return await CredentialStorageService.hasCredentials(domain);
  }
  
  /// Phase 3: Get subscription storage statistics
  static Future<Map<String, dynamic>> getSubscriptionStats() async {
    final articleStats = await SubscriptionArticleStorage.getStorageStats();
    final credentialStats = await CredentialStorageService.getCredentialStats();
    
    return {
      'articles': articleStats,
      'credentials': credentialStats,
    };
  }
  
  /// Phase 3: Clean up expired articles and credentials
  static Future<Map<String, int>> performCleanup() async {
    final expiredArticles = await SubscriptionArticleStorage.cleanupExpiredArticles();
    
    return {
      'expired_articles_removed': expiredArticles,
    };
  }
}