import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();
  
  static Future<void> initialize(Function(NotificationResponse) onNotificationTap) async {
    const AndroidInitializationSettings androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    const InitializationSettings settings = InitializationSettings(android: androidSettings);
    
    await _notifications.initialize(
      settings,
      onDidReceiveNotificationResponse: onNotificationTap,
    );
  }
  
  static Future<void> showTourReadyNotification(String location) async {
    const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
      'tour_ready_channel',
      'Tour Ready Notifications',
      channelDescription: 'Notifications when tours are ready',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
      enableVibration: true,
      visibility: NotificationVisibility.public,
    );
    
    const NotificationDetails notificationDetails = NotificationDetails(android: androidDetails);
    
    await _notifications.show(
      DateTime.now().millisecondsSinceEpoch ~/ 1000,
      '🎵 Tour Ready!',
      'Your tour "$location" is ready to download and play!',
      notificationDetails,
      payload: location, // Add payload to identify which tour was completed
    );
  }
}