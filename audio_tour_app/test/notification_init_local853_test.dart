// [LOCAL-853] The iOS notifications throw: GCloud_Storied_1 failure_events,
// Michael's iPhone, 12 × "Invalid argument(s): iOS settings must be set when
// targeting iOS platform." The plugin threw because NotificationService built
// InitializationSettings with Android settings ONLY. This test asserts the
// settings builder now carries iOS (and macOS) DarwinInitializationSettings so
// FlutterLocalNotificationsPlugin.initialize can never throw on iOS.
//
// Run: flutter test test/notification_init_local853_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:audio_tour_app_dev/services/notification_service.dart';

void main() {
  group('LOCAL-853 NotificationService init settings', () {
    final settings = NotificationService.buildInitializationSettings();

    test('iOS DarwinInitializationSettings are set (the throw fix)', () {
      expect(
        settings.iOS,
        isA<DarwinInitializationSettings>(),
        reason: 'iOS settings MUST be set or the plugin throws on iOS',
      );
    });

    test('macOS DarwinInitializationSettings are set', () {
      expect(settings.macOS, isA<DarwinInitializationSettings>());
    });

    test('Android settings are still set (unchanged behaviour)', () {
      expect(settings.android, isA<AndroidInitializationSettings>());
    });
  });
}
