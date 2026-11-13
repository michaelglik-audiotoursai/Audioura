// [LOCAL-908] Lock-screen / notification-shade entry to the "On the way" menu.
//
// While the listener is on the way between stops, an ongoing notification says
// where they are heading and what (if anything) is playing, with a "Topics"
// action. Tapping the action raises [menuRequests]; the player listens and
// opens the same sheet the player button opens. The notification is removed as
// soon as a stop starts or the player closes.
//
// Everything here is best-effort: a notification failure must never affect
// playback, so every call swallows errors.
library on_the_way_notification;

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class OnTheWayNotification {
  OnTheWayNotification._();

  static const int notificationId = 90801;
  static const String actionId = 'otw_menu';
  static const String payload = 'otw_menu';
  static const String androidChannelId = 'on_the_way_channel';
  static const String iosCategory = 'otw_category';

  /// Bumped each time the listener taps the notification or its action.
  static final ValueNotifier<int> menuRequests = ValueNotifier<int>(0);

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  /// True for a response that belongs to this feature (so MainScreen's generic
  /// "open the Listen tab" handler must NOT run and tear down the player).
  static bool isMenuResponse(NotificationResponse r) =>
      r.actionId == actionId || r.payload == payload;

  static void requestMenu() => menuRequests.value++;

  static Future<void> show({required String title, required String body}) async {
    try {
      await _plugin.show(
        notificationId,
        title,
        body,
        const NotificationDetails(
          android: AndroidNotificationDetails(
            androidChannelId,
            'On the way',
            channelDescription: 'What is playing between stops',
            importance: Importance.low,
            priority: Priority.low,
            ongoing: true,
            playSound: false,
            enableVibration: false,
            visibility: NotificationVisibility.public,
            actions: [
              AndroidNotificationAction(actionId, 'Topics',
                  showsUserInterface: true),
            ],
          ),
          iOS: DarwinNotificationDetails(
            presentAlert: false,
            presentSound: false,
            categoryIdentifier: iosCategory,
          ),
        ),
        payload: payload,
      );
    } catch (_) {}
  }

  static Future<void> clear() async {
    try {
      await _plugin.cancel(notificationId);
    } catch (_) {}
  }
}
