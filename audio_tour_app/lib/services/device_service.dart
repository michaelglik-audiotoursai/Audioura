import 'package:shared_preferences/shared_preferences.dart';
import 'package:device_info_plus/device_info_plus.dart';

class DeviceService {
  
  /// Get or create user ID (device ID for subscription service)
  static Future<String> getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    String? userId = prefs.getString('user_id');
    
    if (userId == null) {
      // Generate new user ID if not exists
      final deviceInfo = DeviceInfoPlugin();
      final androidInfo = await deviceInfo.androidInfo;
      userId = _generateUserId(androidInfo);
      await prefs.setString('user_id', userId);
    }
    
    return userId;
  }
  
  /// Generate user ID from device info
  static String _generateUserId(AndroidDeviceInfo androidInfo) {
    final deviceId = '${androidInfo.brand}-${androidInfo.model}-${androidInfo.id}'.hashCode.abs();
    return 'USER-${deviceId.toString().padLeft(8, '0')}';
  }
}