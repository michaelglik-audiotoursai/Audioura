import 'dart:io';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:device_info_plus/device_info_plus.dart';

class DeviceService {
  
  /// Get or create user ID (device ID for subscription service)
  static Future<String> getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    String? userId = prefs.getString('user_id');
    
    if (userId == null) {
      final deviceInfo = DeviceInfoPlugin();
      if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        userId = _generateUserIdFromString('${iosInfo.name}-${iosInfo.model}-${iosInfo.identifierForVendor}');
      } else {
        final androidInfo = await deviceInfo.androidInfo;
        userId = _generateUserIdFromString('${androidInfo.brand}-${androidInfo.model}-${androidInfo.id}');
      }
      await prefs.setString('user_id', userId);
    }
    
    return userId;
  }
  
  static String _generateUserIdFromString(String input) {
    final deviceId = input.hashCode.abs();
    return 'USER-${deviceId.toString().padLeft(8, '0')}';
  }
}