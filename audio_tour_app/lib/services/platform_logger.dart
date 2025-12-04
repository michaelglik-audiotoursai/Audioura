import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:io' show Platform;

// Platform-specific logging architecture
abstract class PlatformLogger {
  Future<void> log(String message);
  
  static PlatformLogger get instance {
    if (kIsWeb) {
      return WebLogger();
    } else if (Platform.isAndroid) {
      return AndroidLogger();
    } else if (Platform.isIOS) {
      return IOSLogger();
    } else {
      return AndroidLogger(); // Fallback
    }
  }
}

// Android Logger - Full functionality (unchanged behavior)
class AndroidLogger extends PlatformLogger {
  @override
  Future<void> log(String message) async {
    final timestamp = DateTime.now().toString().substring(11, 19);
    
    try {
      final prefs = await SharedPreferences.getInstance();
      final logs = prefs.getStringList('debug_logs') ?? [];
      logs.add('[$timestamp] $message');
      
      // Keep only last 75 logs
      if (logs.length > 75) {
        logs.removeAt(0);
      }
      
      await prefs.setStringList('debug_logs', logs);
      print(message); // Full console logging
    } catch (e) {
      print('[$timestamp] $message'); // Fallback
    }
  }
}

// Web Logger - Restricted for browser performance
class WebLogger extends PlatformLogger {
  @override
  Future<void> log(String message) async {
    final timestamp = DateTime.now().toString().substring(11, 19);
    
    // Block binary data and very long messages
    if (message.contains('base64') || 
        message.contains('data:') ||
        message.length > 500) {
      return; // Skip binary data and massive messages
    }
    
    // Log all non-binary messages to console (truncated)
    final truncatedMessage = message.length > 100 ? message.substring(0, 100) + '...' : message;
    print('[$timestamp] $truncatedMessage');
    
    // No storage on web platform
  }
}

// iOS Logger - Future implementation (same as Android for now)
class IOSLogger extends PlatformLogger {
  @override
  Future<void> log(String message) async {
    final timestamp = DateTime.now().toString().substring(11, 19);
    
    try {
      final prefs = await SharedPreferences.getInstance();
      final logs = prefs.getStringList('debug_logs') ?? [];
      logs.add('[$timestamp] $message');
      
      // Keep only last 75 logs
      if (logs.length > 75) {
        logs.removeAt(0);
      }
      
      await prefs.setStringList('debug_logs', logs);
      print(message); // Full console logging
    } catch (e) {
      print('[$timestamp] $message'); // Fallback
    }
  }
}