import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();

  // [LOCAL-853] iOS throw fix. GCloud_Storied_1 failure_events, Michael's
  // iPhone (ios 2.4.40+88), 12 × "Invalid argument(s): iOS settings must be set
  // when targeting iOS platform." — FlutterLocalNotificationsPlugin.initialize
  // ← NotificationService.initialize. The old code built
  // InitializationSettings(android: …) ONLY, so on iOS the plugin threw because
  // its `iOS`/`macOS` DarwinInitializationSettings were null. Pass Darwin
  // settings for both Apple platforms so initialize never throws on iOS.
  //
  // Extracted as a pure builder so a unit test can assert the iOS settings are
  // present without needing the platform plugin.
  static InitializationSettings buildInitializationSettings() {
    const AndroidInitializationSettings androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    // Request no permissions at init time (the app prompts separately where it
    // already handles permission_handler); just satisfy the platform contract
    // so the plugin initialises. Defaults are safe.
    const DarwinInitializationSettings darwinSettings =
        DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
    );
    return const InitializationSettings(
      android: androidSettings,
      iOS: darwinSettings,
      macOS: darwinSettings,
    );
  }

  static Future<void> initialize(Function(NotificationResponse) onNotificationTap) async {
    final InitializationSettings settings = buildInitializationSettings();

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
    
    const NotificationDetails notificationDetails = NotificationDetails(
      android: androidDetails,
      // [LOCAL-853] iOS/macOS presentation options so the tour-ready
      // notification actually appears on Apple platforms (the old code passed
      // Android details only).
      iOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
      macOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      ),
    );
    
    await _notifications.show(
      DateTime.now().millisecondsSinceEpoch ~/ 1000,
      '🎵 Tour Ready!',
      'Your tour "$location" is ready to download and play!',
      notificationDetails,
      payload: location, // Add payload to identify which tour was completed
    );
  }
}