import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:archive/archive.dart';
import '../screens/debug_log_viewer_screen.dart';

class SubscriptionArticleMetadata {
  final String articleId;
  final String title;
  final String domain;
  final DateTime downloaded;
  final int sizeBytes;
  final DateTime? expires;
  final String status;
  final String author;
  final String articleType;
  
  SubscriptionArticleMetadata({
    required this.articleId,
    required this.title,
    required this.domain,
    required this.downloaded,
    required this.sizeBytes,
    this.expires,
    required this.status,
    required this.author,
    required this.articleType,
  });
  
  Map<String, dynamic> toJson() {
    return {
      'article_id': articleId,
      'title': title,
      'domain': domain,
      'downloaded': downloaded.toIso8601String(),
      'size_bytes': sizeBytes,
      'expires': expires?.toIso8601String(),
      'status': status,
      'author': author,
      'article_type': articleType,
    };
  }
  
  factory SubscriptionArticleMetadata.fromJson(Map<String, dynamic> json) {
    return SubscriptionArticleMetadata(
      articleId: json['article_id'] ?? '',
      title: json['title'] ?? '',
      domain: json['domain'] ?? '',
      downloaded: DateTime.parse(json['downloaded'] ?? DateTime.now().toIso8601String()),
      sizeBytes: json['size_bytes'] ?? 0,
      expires: json['expires'] != null ? DateTime.parse(json['expires']) : null,
      status: json['status'] ?? 'downloaded',
      author: json['author'] ?? '',
      articleType: json['article_type'] ?? 'Others',
    );
  }
}

class SubscriptionArticleStorage {
  static const String _metadataKey = 'subscription_articles_metadata';
  static const int _maxStorageMB = 500; // 500MB limit for subscription articles
  static const int _maxArticlesPerDomain = 50; // Limit articles per domain
  
  /// Store subscription article locally
  static Future<bool> storeArticle({
    required String articleId,
    required String title,
    required String domain,
    required List<int> zipBytes,
    required String author,
    required String articleType,
  }) async {
    try {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Storing subscription article: $articleId for domain: $domain');
      
      // Check storage limits
      final canStore = await _checkStorageLimits(domain, zipBytes.length);
      if (!canStore) {
        await DebugLogHelper.addDebugLog('SUB_STORAGE: Storage limit exceeded, cannot store article $articleId');
        return false;
      }
      
      // Get app directory
      final appDir = await getApplicationDocumentsDirectory();
      final subscriptionDir = Directory('${appDir.path}/subscription_articles');
      await subscriptionDir.create(recursive: true);
      
      // Create domain directory
      final safeDomain = domain.replaceAll(RegExp(r'[^a-zA-Z0-9_.-]'), '_');
      final domainDir = Directory('${subscriptionDir.path}/$safeDomain');
      await domainDir.create(recursive: true);
      
      // Create article directory
      final safeTitle = title.length > 50 ? title.substring(0, 50) : title;
      final safeName = safeTitle.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      final articleDir = Directory('${domainDir.path}/${safeName}_$articleId');
      await articleDir.create(recursive: true);
      
      // Save ZIP file
      final zipFile = File('${articleDir.path}/article.zip');
      await zipFile.writeAsBytes(zipBytes);
      
      // Extract ZIP contents
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.isFile) {
          final extractedFile = File('${articleDir.path}/${file.name}');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(file.content as List<int>);
        }
      }
      
      // Extract and save text content for search
      await _extractTextContent(articleDir.path);
      
      // Create metadata
      final metadata = SubscriptionArticleMetadata(
        articleId: articleId,
        title: title,
        domain: domain,
        downloaded: DateTime.now(),
        sizeBytes: zipBytes.length,
        expires: DateTime.now().add(Duration(days: 30)), // 30 day expiry
        status: 'downloaded',
        author: author,
        articleType: articleType,
      );
      
      // Store metadata
      await _storeMetadata(metadata);
      
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Successfully stored subscription article: $articleId');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error storing subscription article $articleId: $e');
      return false;
    }
  }
  
  /// Check if subscription article is stored locally
  static Future<bool> isArticleStored(String articleId) async {
    try {
      final metadata = await _getStoredMetadata();
      return metadata.any((article) => article.articleId == articleId && article.status == 'downloaded');
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error checking if article $articleId is stored: $e');
      return false;
    }
  }
  
  /// Get stored subscription article path
  static Future<String?> getArticlePath(String articleId) async {
    try {
      final metadata = await _getStoredMetadata();
      final article = metadata.where((a) => a.articleId == articleId && a.status == 'downloaded').firstOrNull;
      
      if (article == null) return null;
      
      final appDir = await getApplicationDocumentsDirectory();
      final safeDomain = article.domain.replaceAll(RegExp(r'[^a-zA-Z0-9_.-]'), '_');
      final safeTitle = article.title.length > 50 ? article.title.substring(0, 50) : article.title;
      final safeName = safeTitle.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
      
      final articlePath = '${appDir.path}/subscription_articles/$safeDomain/${safeName}_$articleId';
      final articleDir = Directory(articlePath);
      
      if (await articleDir.exists()) {
        return articlePath;
      }
      
      return null;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error getting article path for $articleId: $e');
      return null;
    }
  }
  
  /// Get stored articles for a domain
  static Future<List<SubscriptionArticleMetadata>> getArticlesByDomain(String domain) async {
    try {
      final metadata = await _getStoredMetadata();
      return metadata.where((article) => article.domain == domain && article.status == 'downloaded').toList();
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error getting articles for domain $domain: $e');
      return [];
    }
  }
  
  /// Get all stored subscription articles
  static Future<List<SubscriptionArticleMetadata>> getAllStoredArticles() async {
    try {
      final metadata = await _getStoredMetadata();
      return metadata.where((article) => article.status == 'downloaded').toList();
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error getting all stored articles: $e');
      return [];
    }
  }
  
  /// Remove subscription article
  static Future<bool> removeArticle(String articleId) async {
    try {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Removing subscription article: $articleId');
      
      final articlePath = await getArticlePath(articleId);
      if (articlePath != null) {
        final articleDir = Directory(articlePath);
        if (await articleDir.exists()) {
          await articleDir.delete(recursive: true);
        }
      }
      
      // Remove from metadata
      await _removeFromMetadata(articleId);
      
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Successfully removed subscription article: $articleId');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error removing subscription article $articleId: $e');
      return false;
    }
  }
  
  /// Clean up expired articles
  static Future<int> cleanupExpiredArticles() async {
    try {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Starting cleanup of expired subscription articles');
      
      final metadata = await _getStoredMetadata();
      final now = DateTime.now();
      int removedCount = 0;
      
      for (final article in metadata) {
        if (article.expires != null && now.isAfter(article.expires!)) {
          final removed = await removeArticle(article.articleId);
          if (removed) removedCount++;
        }
      }
      
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Cleanup completed, removed $removedCount expired articles');
      return removedCount;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error during cleanup: $e');
      return 0;
    }
  }
  
  /// Get storage statistics
  static Future<Map<String, dynamic>> getStorageStats() async {
    try {
      final metadata = await _getStoredMetadata();
      final activeArticles = metadata.where((a) => a.status == 'downloaded').toList();
      
      int totalSize = 0;
      final domainCounts = <String, int>{};
      final typeCounts = <String, int>{};
      
      for (final article in activeArticles) {
        totalSize += article.sizeBytes;
        domainCounts[article.domain] = (domainCounts[article.domain] ?? 0) + 1;
        typeCounts[article.articleType] = (typeCounts[article.articleType] ?? 0) + 1;
      }
      
      return {
        'total_articles': activeArticles.length,
        'total_size_mb': (totalSize / (1024 * 1024)).round(),
        'domains': domainCounts,
        'types': typeCounts,
        'storage_limit_mb': _maxStorageMB,
        'articles_per_domain_limit': _maxArticlesPerDomain,
      };
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error getting storage stats: $e');
      return {};
    }
  }
  
  /// Clear all subscription articles
  static Future<bool> clearAllArticles() async {
    try {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Clearing all subscription articles');
      
      final appDir = await getApplicationDocumentsDirectory();
      final subscriptionDir = Directory('${appDir.path}/subscription_articles');
      
      if (await subscriptionDir.exists()) {
        await subscriptionDir.delete(recursive: true);
      }
      
      // Clear metadata
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_metadataKey);
      
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Successfully cleared all subscription articles');
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error clearing all articles: $e');
      return false;
    }
  }
  
  // Private helper methods
  
  static Future<bool> _checkStorageLimits(String domain, int newArticleSize) async {
    try {
      final metadata = await _getStoredMetadata();
      final activeArticles = metadata.where((a) => a.status == 'downloaded').toList();
      
      // Check total storage limit
      int totalSize = activeArticles.fold(0, (sum, article) => sum + article.sizeBytes);
      if ((totalSize + newArticleSize) > (_maxStorageMB * 1024 * 1024)) {
        await DebugLogHelper.addDebugLog('SUB_STORAGE: Total storage limit would be exceeded');
        return false;
      }
      
      // Check articles per domain limit
      final domainArticles = activeArticles.where((a) => a.domain == domain).length;
      if (domainArticles >= _maxArticlesPerDomain) {
        await DebugLogHelper.addDebugLog('SUB_STORAGE: Articles per domain limit would be exceeded for $domain');
        return false;
      }
      
      return true;
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error checking storage limits: $e');
      return false;
    }
  }
  
  static Future<void> _extractTextContent(String articlePath) async {
    try {
      final indexFile = File('$articlePath/index.html');
      if (await indexFile.exists()) {
        final htmlContent = await indexFile.readAsString();
        // Simple text extraction - remove HTML tags
        final textContent = htmlContent
            .replaceAll(RegExp(r'<[^>]*>'), ' ')
            .replaceAll(RegExp(r'\\s+'), ' ')
            .trim();
        
        final textFile = File('$articlePath/audiotours_search_content.txt');
        await textFile.writeAsString(textContent);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error extracting text content: $e');
    }
  }
  
  static Future<List<SubscriptionArticleMetadata>> _getStoredMetadata() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final metadataJson = prefs.getStringList(_metadataKey) ?? [];
      
      return metadataJson.map((json) {
        final data = jsonDecode(json) as Map<String, dynamic>;
        return SubscriptionArticleMetadata.fromJson(data);
      }).toList();
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error reading stored metadata: $e');
      return [];
    }
  }
  
  static Future<void> _storeMetadata(SubscriptionArticleMetadata metadata) async {
    try {
      final existingMetadata = await _getStoredMetadata();
      
      // Remove existing entry for same article ID
      existingMetadata.removeWhere((article) => article.articleId == metadata.articleId);
      
      // Add new metadata
      existingMetadata.add(metadata);
      
      // Save to preferences
      final prefs = await SharedPreferences.getInstance();
      final metadataJson = existingMetadata.map((article) => jsonEncode(article.toJson())).toList();
      await prefs.setStringList(_metadataKey, metadataJson);
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error storing metadata: $e');
    }
  }
  
  static Future<void> _removeFromMetadata(String articleId) async {
    try {
      final existingMetadata = await _getStoredMetadata();
      existingMetadata.removeWhere((article) => article.articleId == articleId);
      
      final prefs = await SharedPreferences.getInstance();
      final metadataJson = existingMetadata.map((article) => jsonEncode(article.toJson())).toList();
      await prefs.setStringList(_metadataKey, metadataJson);
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_STORAGE: Error removing from metadata: $e');
    }
  }
}