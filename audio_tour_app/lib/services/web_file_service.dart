import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class WebFileService {
  // Get blob URL for web platform file access
  static Future<String?> getWebFileBlobUrl(String tourPath, String fileName) async {
    if (!kIsWeb) return null;
    
    final prefs = await SharedPreferences.getInstance();
    // Extract the tour identifier from the path
    final pathParts = tourPath.split('/');
    final tourId = pathParts.isNotEmpty ? pathParts.last : tourPath;
    
    final key = 'tour_file_${tourId}_$fileName';
    final base64Content = prefs.getString(key);
    final mimeType = prefs.getString('${key}_mime') ?? 'application/octet-stream';
    
    if (base64Content != null) {
      // Return data URL that browsers can access directly
      return 'data:$mimeType;base64,$base64Content';
    }
    
    return null;
  }
  
  // Get tour file path (platform-specific)
  static Future<String> getTourFilePath(String tourPath, String fileName) async {
    if (kIsWeb) {
      // Web platform: return blob URL for direct browser access
      final blobUrl = await getWebFileBlobUrl(tourPath, fileName);
      if (blobUrl != null) {
        return blobUrl;
      }
      // Fallback: return a placeholder that won't crash
      return 'data:text/html;base64,PGh0bWw+PGJvZHk+PGgxPkZpbGUgbm90IGZvdW5kPC9oMT48L2JvZHk+PC9odG1sPg==';
    } else {
      // Mobile platform: return actual file path
      return '$tourPath/$fileName';
    }
  }
  
  // Get file content for web platform
  static Future<String?> getWebFileContent(String tourPath, String fileName) async {
    if (!kIsWeb) return null;
    
    final prefs = await SharedPreferences.getInstance();
    // Extract the tour identifier from the path
    final pathParts = tourPath.split('/');
    final tourId = pathParts.isNotEmpty ? pathParts.last : tourPath;
    
    final key = 'tour_file_${tourId}_$fileName';
    final base64Content = prefs.getString(key);
    
    if (base64Content != null) {
      final bytes = base64Decode(base64Content);
      return utf8.decode(bytes);
    }
    
    return null;
  }
}