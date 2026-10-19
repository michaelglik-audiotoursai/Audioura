// [LOCAL-714 / D675 part 2] The ONE quiet local notification for new community
// tours, and the notification-permission request that is asked ONLY when the
// member says Yes to auto-download (D675 part 2 §3).
//
// This wraps flutter_local_notifications (already a dependency, 17.2.2). The
// Android init already exists in the app (NotificationService); this adds the
// iOS init + the Darwin permission request and the "quiet" (no sound, low
// importance) presentation for the new-tours notification. Quiet-hours
// scheduling is handled by the PURE quietHoursGate in community_background.dart;
// this file just posts now or schedules the zoned notification for the morning.
//
// Everything is wrapped so a test host (no plugin) degrades to a no-op rather
// than crashing — the policy (what text, when) is tested on the pure helpers.

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

import 'community_background.dart' show kNewToursNotificationTitle;

class CommunityNotifications {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static bool _inited = false;
  static bool _tzInited = false;

  /// A stable id for the single new-tours notification, so a later post or a
  /// scheduled morning post REPLACES the previous one (never a pile-up).
  static const int _newToursNotificationId = 714001;

  /// The quiet channel (Android): low importance, no sound — it must not buzz.
  static const AndroidNotificationDetails _androidQuiet =
      AndroidNotificationDetails(
    'community_new_tours',
    'New community tours',
    channelDescription:
        'A quiet heads-up when your communities have new tours to download.',
    importance: Importance.low,
    priority: Priority.low,
    playSound: false,
    enableVibration: false,
  );

  /// iOS presentation: show it, but no sound (quiet).
  static const DarwinNotificationDetails _iosQuiet = DarwinNotificationDetails(
    presentAlert: true,
    presentBadge: true,
    presentSound: false,
  );

  static const NotificationDetails _quietDetails = NotificationDetails(
    android: _androidQuiet,
    iOS: _iosQuiet,
  );

  /// Initialise the plugin (Android + iOS). Safe to call repeatedly. Does NOT
  /// request any permission — permission is requested only in
  /// [requestPermissionOnOptIn], which is called when the member says Yes.
  static Future<void> ensureInitialized() async {
    if (_inited) return;
    try {
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      // requestXxxPermission:false — we do NOT ask at init; only on opt-in.
      const ios = DarwinInitializationSettings(
        requestAlertPermission: false,
        requestBadgePermission: false,
        requestSoundPermission: false,
      );
      await _plugin.initialize(
        const InitializationSettings(android: android, iOS: ios),
      );
      _inited = true;
    } catch (_) {
      // No plugin on this host (tests) — stay uninitialised; posts no-op.
    }
  }

  /// Ask for notification permission — called ONLY when the member answers Yes
  /// to the auto-download join question (D675 part 2 §3: "Notification
  /// permission is asked only when the member says Yes to auto-download").
  /// Returns true if granted (or already granted); false/unknown otherwise.
  static Future<bool> requestPermissionOnOptIn() async {
    try {
      await ensureInitialized();
      // iOS / macOS.
      final ios = _plugin.resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin>();
      if (ios != null) {
        final granted = await ios.requestPermissions(
            alert: true, badge: true, sound: false);
        return granted ?? false;
      }
      // Android 13+ runtime POST_NOTIFICATIONS.
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      if (android != null) {
        final granted = await android.requestNotificationsPermission();
        return granted ?? true; // pre-13 returns null and is granted by default
      }
    } catch (_) {}
    return false;
  }

  /// Post the ONE new-tours notification now, or schedule it for [deferUntil]
  /// (the morning) when quiet hours are in effect. Uses a stable id so a new
  /// call replaces any pending/visible one. No-ops on a host without the plugin.
  static Future<void> postOrScheduleNewTours({
    required String body,
    required bool mayNotifyNow,
    DateTime? deferUntil,
  }) async {
    try {
      await ensureInitialized();
      if (mayNotifyNow || deferUntil == null) {
        await _plugin.show(
          _newToursNotificationId,
          kNewToursNotificationTitle,
          body,
          _quietDetails,
        );
        return;
      }
      // Quiet hours — schedule the single notification for the morning.
      await _ensureTimezone();
      final when = tz.TZDateTime.from(deferUntil, tz.local);
      await _plugin.zonedSchedule(
        _newToursNotificationId,
        kNewToursNotificationTitle,
        body,
        when,
        _quietDetails,
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
    } catch (_) {
      // Missing plugin / tz on a test host — nothing to do.
    }
  }

  static Future<void> _ensureTimezone() async {
    if (_tzInited) return;
    try {
      tzdata.initializeTimeZones();
      _tzInited = true;
    } catch (_) {}
  }
}
