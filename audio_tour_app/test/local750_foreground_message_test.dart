import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:audio_tour_app_dev/services/foreground_community_messages.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';

/// LOCAL-750 (C1) — members must SEE the message.
///
/// Before this change a new/updated community tour produced ONLY a silent,
/// low-importance SYSTEM notification (channel `community_new_tours`,
/// Importance.low). It never popped up and nothing showed in the app, so
/// Michael saw nothing while using the app (2026-10-23 retest). Now a FOREGROUND
/// message shows IN THE APP (a SnackBar via the global messenger) with a "View"
/// action; a BACKGROUND message keeps the system notification.
void main() {
  group('CommunityMessageRouter.target (pure policy)', () {
    test('foreground → in-app', () {
      expect(CommunityMessageRouter.target(isForeground: true),
          CommunityMessageTarget.inApp);
    });
    test('background → system notification', () {
      expect(CommunityMessageRouter.target(isForeground: false),
          CommunityMessageTarget.systemNotification);
    });
  });

  group('routeCommunityMessage', () {
    test('background posts the system notification (fallback), not in-app', () {
      var systemPosted = 0;
      final target = routeCommunityMessage(
        'New tour in Salem Bikes: Harbor Loop',
        tourId: 716,
        isForeground: false,
        postSystem: () => systemPosted++,
      );
      expect(target, CommunityMessageTarget.systemNotification);
      expect(systemPosted, 1);
    });

    test(
        'foreground with no messenger mounted falls back to the system '
        'notification (message is never dropped)', () {
      var systemPosted = 0;
      // No MaterialApp pumped → communityScaffoldMessengerKey.currentState is
      // null, so the in-app show cannot happen and we must fall back.
      final target = routeCommunityMessage(
        'Harbor Loop was updated by the organiser.',
        tourId: 716,
        isForeground: true,
        postSystem: () => systemPosted++,
      );
      expect(target, CommunityMessageTarget.systemNotification);
      expect(systemPosted, 1);
    });
  });

  group('in-app SnackBar', () {
    testWidgets(
        'foreground message shows IN THE APP with a working View action',
        (tester) async {
      PendingListenOpen.instance.consume();
      ForegroundCommunityMessages.instance.setForeground(true);

      await tester.pumpWidget(MaterialApp(
        scaffoldMessengerKey: communityScaffoldMessengerKey,
        home: const Scaffold(body: Text('home')),
      ));

      var systemPosted = 0;
      final target = routeCommunityMessage(
        'New tour in Salem Bikes: Harbor Loop',
        tourId: 716,
        isForeground: true,
        postSystem: () => systemPosted++,
      );
      await tester.pump(); // let the SnackBar appear
      await tester.pump(const Duration(milliseconds: 750)); // finish its entrance

      // Delivered in-app, NOT via the system notification.
      expect(target, CommunityMessageTarget.inApp);
      expect(systemPosted, 0);

      // The message text and a View action are on screen.
      expect(find.text('New tour in Salem Bikes: Harbor Loop'), findsOneWidget);
      expect(find.text('View'), findsOneWidget);

      // Tapping View asks PendingListenOpen to open tour 716.
      await tester.tap(find.widgetWithText(SnackBarAction, 'View'));
      await tester.pump();
      expect(PendingListenOpen.instance.request.value?.tourId, '716');

      PendingListenOpen.instance.consume();
    });

    testWidgets('a message with no tour id shows without a View action',
        (tester) async {
      await tester.pumpWidget(MaterialApp(
        scaffoldMessengerKey: communityScaffoldMessengerKey,
        home: const Scaffold(body: Text('home')),
      ));
      final shown = ForegroundCommunityMessages.instance
          .show('A community message', tourId: null);
      await tester.pump();
      expect(shown, isTrue);
      expect(find.text('A community message'), findsOneWidget);
      expect(find.text('View'), findsNothing);
    });
  });
}
