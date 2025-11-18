import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:crypto/crypto.dart';
import '../screens/debug_log_viewer_screen.dart';

class StoredCredential {
  final String domain;
  final String encryptedUsername;
  final String encryptedPassword;
  final DateTime created;
  final DateTime lastUsed;
  final String status;
  
  StoredCredential({
    required this.domain,
    required this.encryptedUsername,
    required this.encryptedPassword,
    required this.created,
    required this.lastUsed,
    required this.status,
  });
  
  Map<String, dynamic> toJson() {
    return {
      'domain': domain,
      'encrypted_username': encryptedUsername,
      'encrypted_password': encryptedPassword,
      'created': created.toIso8601String(),
      'last_used': lastUsed.toIso8601String(),
      'status': status,
    };
  }
  
  factory StoredCredential.fromJson(Map<String, dynamic> json) {
    return StoredCredential(
      domain: json['domain'] ?? '',
      encryptedUsername: json['encrypted_username'] ?? '',
      encryptedPassword: json['encrypted_password'] ?? '',
      created: DateTime.parse(json['created'] ?? DateTime.now().toIso8601String()),
      lastUsed: DateTime.parse(json['last_used'] ?? DateTime.now().toIso8601String()),
      status: json['status'] ?? 'active',
    );
  }
}

class CredentialStorageService {
  static const String _credentialsKey = 'subscription_credentials';
  static const FlutterSecureStorage _secureStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(
      encryptedSharedPreferences: true,
    ),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock_this_device,
    ),
  );
  
  /// Store credentials for a domain securely
  static Future<bool> storeCredentials({
    required String domain,
    required String username,
    required String password,
  }) async {
    try {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Storing credentials for domain: $domain');
      
      // Get existing credentials
      final existingCredentials = await _getStoredCredentials();
      
      // Create device-specific encryption key
      final deviceKey = await _getDeviceEncryptionKey();
      
      // Encrypt credentials
      final encryptedUsername = _encryptString(username, deviceKey);
      final encryptedPassword = _encryptString(password, deviceKey);
      
      // Create credential object
      final credential = StoredCredential(
        domain: domain,
        encryptedUsername: encryptedUsername,
        encryptedPassword: encryptedPassword,
        created: DateTime.now(),
        lastUsed: DateTime.now(),
        status: 'active',
      );
      
      // Update credentials map
      existingCredentials[domain] = credential;
      
      // Store securely
      final credentialsJson = json.encode(
        existingCredentials.map((key, value) => MapEntry(key, value.toJson()))
      );
      
      await _secureStorage.write(key: _credentialsKey, value: credentialsJson);
      
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Successfully stored credentials for $domain');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error storing credentials for $domain: $e');
      return false;
    }
  }
  
  /// Retrieve credentials for a domain
  static Future<Map<String, String>?> getCredentials(String domain) async {
    try {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Retrieving credentials for domain: $domain');
      
      final credentials = await _getStoredCredentials();
      final credential = credentials[domain];
      
      if (credential == null) {
        await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: No credentials found for $domain');
        return null;
      }
      
      // Check if credentials are expired (30 days)
      final now = DateTime.now();
      final daysSinceCreated = now.difference(credential.created).inDays;
      if (daysSinceCreated > 30) {
        await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Credentials for $domain are expired ($daysSinceCreated days old)');
        await removeCredentials(domain);
        return null;
      }
      
      // Decrypt credentials
      final deviceKey = await _getDeviceEncryptionKey();
      final username = _decryptString(credential.encryptedUsername, deviceKey);
      final password = _decryptString(credential.encryptedPassword, deviceKey);
      
      // Update last used timestamp
      await _updateLastUsed(domain);
      
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Successfully retrieved credentials for $domain');
      return {
        'username': username,
        'password': password,
        'domain': domain,
      };
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error retrieving credentials for $domain: $e');
      return null;
    }
  }
  
  /// Check if credentials exist for a domain
  static Future<bool> hasCredentials(String domain) async {
    try {
      final credentials = await _getStoredCredentials();
      final credential = credentials[domain];
      
      if (credential == null) return false;
      
      // Check expiry
      final now = DateTime.now();
      final daysSinceCreated = now.difference(credential.created).inDays;
      if (daysSinceCreated > 30) {
        await removeCredentials(domain);
        return false;
      }
      
      return credential.status == 'active';
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error checking credentials for $domain: $e');
      return false;
    }
  }
  
  /// Get list of domains with stored credentials
  static Future<List<String>> getStoredDomains() async {
    try {
      final credentials = await _getStoredCredentials();
      final activeDomains = <String>[];
      
      final now = DateTime.now();
      for (final entry in credentials.entries) {
        final credential = entry.value;
        final daysSinceCreated = now.difference(credential.created).inDays;
        
        if (daysSinceCreated <= 30 && credential.status == 'active') {
          activeDomains.add(entry.key);
        }
      }
      
      return activeDomains;
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error getting stored domains: $e');
      return [];
    }
  }
  
  /// Remove credentials for a domain
  static Future<bool> removeCredentials(String domain) async {
    try {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Removing credentials for domain: $domain');
      
      final credentials = await _getStoredCredentials();
      credentials.remove(domain);
      
      final credentialsJson = json.encode(
        credentials.map((key, value) => MapEntry(key, value.toJson()))
      );
      
      await _secureStorage.write(key: _credentialsKey, value: credentialsJson);
      
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Successfully removed credentials for $domain');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error removing credentials for $domain: $e');
      return false;
    }
  }
  
  /// Clear all stored credentials
  static Future<bool> clearAllCredentials() async {
    try {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Clearing all stored credentials');
      await _secureStorage.delete(key: _credentialsKey);
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Successfully cleared all credentials');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error clearing credentials: $e');
      return false;
    }
  }
  
  /// Get credential statistics
  static Future<Map<String, dynamic>> getCredentialStats() async {
    try {
      final credentials = await _getStoredCredentials();
      final now = DateTime.now();
      
      int activeCount = 0;
      int expiredCount = 0;
      DateTime? oldestCreated;
      DateTime? newestCreated;
      
      for (final credential in credentials.values) {
        final daysSinceCreated = now.difference(credential.created).inDays;
        
        if (daysSinceCreated > 30) {
          expiredCount++;
        } else if (credential.status == 'active') {
          activeCount++;
        }
        
        if (oldestCreated == null || credential.created.isBefore(oldestCreated)) {
          oldestCreated = credential.created;
        }
        if (newestCreated == null || credential.created.isAfter(newestCreated)) {
          newestCreated = credential.created;
        }
      }
      
      return {
        'total_domains': credentials.length,
        'active_domains': activeCount,
        'expired_domains': expiredCount,
        'oldest_created': oldestCreated?.toIso8601String(),
        'newest_created': newestCreated?.toIso8601String(),
      };
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error getting credential stats: $e');
      return {};
    }
  }
  
  // Private helper methods
  
  static Future<Map<String, StoredCredential>> _getStoredCredentials() async {
    try {
      final credentialsJson = await _secureStorage.read(key: _credentialsKey);
      if (credentialsJson == null) return {};
      
      final credentialsMap = json.decode(credentialsJson) as Map<String, dynamic>;
      return credentialsMap.map(
        (key, value) => MapEntry(key, StoredCredential.fromJson(value))
      );
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error reading stored credentials: $e');
      return {};
    }
  }
  
  static Future<void> _updateLastUsed(String domain) async {
    try {
      final credentials = await _getStoredCredentials();
      final credential = credentials[domain];
      
      if (credential != null) {
        final updatedCredential = StoredCredential(
          domain: credential.domain,
          encryptedUsername: credential.encryptedUsername,
          encryptedPassword: credential.encryptedPassword,
          created: credential.created,
          lastUsed: DateTime.now(),
          status: credential.status,
        );
        
        credentials[domain] = updatedCredential;
        
        final credentialsJson = json.encode(
          credentials.map((key, value) => MapEntry(key, value.toJson()))
        );
        
        await _secureStorage.write(key: _credentialsKey, value: credentialsJson);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('CREDENTIAL_STORAGE: Error updating last used for $domain: $e');
    }
  }
  
  static Future<String> _getDeviceEncryptionKey() async {
    const keyName = 'device_credential_key';
    
    String? existingKey = await _secureStorage.read(key: keyName);
    if (existingKey != null) {
      return existingKey;
    }
    
    // Generate new device-specific key
    final timestamp = DateTime.now().millisecondsSinceEpoch.toString();
    final keyMaterial = 'audioura_credential_key_$timestamp';
    final bytes = utf8.encode(keyMaterial);
    final digest = sha256.convert(bytes);
    final deviceKey = digest.toString();
    
    await _secureStorage.write(key: keyName, value: deviceKey);
    return deviceKey;
  }
  
  static String _encryptString(String plaintext, String key) {
    // Simple XOR encryption with key (for demo - in production use proper AES)
    final keyBytes = utf8.encode(key);
    final plaintextBytes = utf8.encode(plaintext);
    final encrypted = <int>[];
    
    for (int i = 0; i < plaintextBytes.length; i++) {
      encrypted.add(plaintextBytes[i] ^ keyBytes[i % keyBytes.length]);
    }
    
    return base64.encode(encrypted);
  }
  
  static String _decryptString(String encrypted, String key) {
    // Simple XOR decryption with key (for demo - in production use proper AES)
    final keyBytes = utf8.encode(key);
    final encryptedBytes = base64.decode(encrypted);
    final decrypted = <int>[];
    
    for (int i = 0; i < encryptedBytes.length; i++) {
      decrypted.add(encryptedBytes[i] ^ keyBytes[i % keyBytes.length]);
    }
    
    return utf8.decode(decrypted);
  }
}