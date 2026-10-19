// [LOCAL-716] Tests for the "downloaded" snackbar wording and the View button
// that opens the Listen tab (optionally on a single tour).
//
// Three things are pinned:
//   1. downloadedMessage() — every count agrees with its number. These are the
//      goldens Michael's Pixel-7 bug (1 tour → "...are available") would fail.
//   2. PendingListenOpen — offer/consume is a one-shot; two offers of the SAME
//      id both notify (a plain String? would de-dupe and the second View would
//      silently do nothing).
//   3. MainScreen switches to the Listen tab when the notifier fires, and
//      MyToursScreen opens the pending tour exactly once.
//
// NOTE: these can FAIL. Revert downloaded_message.dart to the old
// "...now are available" string and the agreement goldens go red; drop the
// token in PendingListenOpenRequest and the "same id twice" test goes red; drop
// the MainScreen listener and the tab-switch test goes red.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/utils/downloaded_message.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_player_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('downloadedMessage — singular/plural agreement goldens', () {
    test('1 tour, no translations → "is now"', () {
      expect(
        downloadedMessage(downloaded: 1),
        '1 tour downloaded and is now on your Listen page',
      );
    });

    test('2 tours, no translations → "are now"', () {
      expect(
        downloadedMessage(downloaded: 2),
        '2 tours downloaded and are now on your Listen page',
      );
    });

    test('1 tour with 1 translation → both singular', () {
      expect(
        downloadedMessage(downloaded: 1, translations: 1),
        '1 tour downloaded with 1 translation and is now on your Listen page',
      );
    });

    test('2 tours with 3 translations → tours plural, translations plural', () {
      expect(
        downloadedMessage(downloaded: 2, translations: 3),
        '2 tours downloaded with 3 translations and are now on your Listen page',
      );
    });

    test('1 tour + (1 was already downloaded)', () {
      expect(
        downloadedMessage(downloaded: 1, alreadyDownloaded: 1),
        '1 tour downloaded and is now on your Listen page '
        '(1 was already downloaded)',
      );
    });

    test('2 tours + (3 were already downloaded)', () {
      expect(
        downloadedMessage(downloaded: 2, alreadyDownloaded: 3),
        '2 tours downloaded and are now on your Listen page '
        '(3 were already downloaded)',
      );
    });

    test('none downloaded, some already → the "all already" line', () {
      expect(
        downloadedMessage(downloaded: 0, alreadyDownloaded: 2),
        'No new tours downloaded - all selected tours were already on your '
        'phone',
      );
    });

    test('none at all → the "all already" line (never an empty snackbar)', () {
      expect(
        downloadedMessage(downloaded: 0),
        'No new tours downloaded - all selected tours were already on your '
        'phone',
      );
    });

    test('failures are appended after a success', () {
      expect(
        downloadedMessage(
          downloaded: 1,
          failures: {'Freedom Trail': ['French', 'German']},
        ),
        '1 tour downloaded and is now on your Listen page. '
        'Some translations failed: Freedom Trail: French, German',
      );
    });
  });

  group('PendingListenOpen — one-shot offer/consume', () {
    setUp(() => PendingListenOpen.instance.consume());

    test('offer(id) parks a request carrying that id', () {
      PendingListenOpen.instance.offer('42');
      final req = PendingListenOpen.instance.request.value;
      expect(req, isNotNull);
      expect(req!.tourId, '42');
    });

    test('offer() with no id parks a request with a null id ("just Listen")',
        () {
      PendingListenOpen.instance.offer();
      final req = PendingListenOpen.instance.request.value;
      expect(req, isNotNull);
      expect(req!.tourId, isNull);
    });

    test('offer("") is treated as no id', () {
      PendingListenOpen.instance.offer('');
      expect(PendingListenOpen.instance.request.value!.tourId, isNull);
    });

    test('consume clears the request', () {
      PendingListenOpen.instance.offer('7');
      PendingListenOpen.instance.consume();
      expect(PendingListenOpen.instance.request.value, isNull);
    });

    test('two offers of the SAME id both notify (distinct tokens)', () {
      var notifications = 0;
      void listener() => notifications++;
      PendingListenOpen.instance.request.addListener(listener);
      addTearDown(() =>
          PendingListenOpen.instance.request.removeListener(listener));

      PendingListenOpen.instance.offer('9');
      PendingListenOpen.instance.offer('9');

      // A plain String? ValueNotifier would fire once (value unchanged); the
      // token makes each request distinct, so both fire.
      expect(notifications, 2);
    });
  });

  group('MainScreen — View switches to the Listen tab', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      PendingListenOpen.instance.consume();
    });

    testWidgets('firing PendingListenOpen shows the Listen (MyTours) screen',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: MainScreen()));
      await tester.pump();

      // Starts on Home, not Listen.
      expect(find.byType(MyToursScreen), findsNothing);

      // A download's View button fires the notifier.
      PendingListenOpen.instance.offer('123');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      // MainScreen switched to index 2 → the Listen tab builds MyToursScreen.
      expect(find.byType(MyToursScreen), findsOneWidget);
    });
  });

  group('MyToursScreen — consumes the pending tour id exactly once', () {
    // _loadTours → _healTourPaths calls getApplicationDocumentsDirectory()
    // (path_provider), which has no implementation in the test VM. Mock it so
    // the load completes and _consumePendingListenOpen() runs.
    setUp(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (call) async => '/tmp',
      );
    });
    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
    });

    testWidgets('a matching saved tour opens its player, then the request is '
        'consumed', (tester) async {
      // One saved tour whose id matches the pending request.
      SharedPreferences.setMockInitialValues({
        'saved_tours': [
          '{"title":"Test Tour","path":"/tmp/does-not-exist","created":"2026-10-19T00:00:00Z","tour_id":"555"}',
        ],
        'app_mode': 'Tours',
      });
      PendingListenOpen.instance.consume();
      PendingListenOpen.instance.offer('555');

      // A NavigatorObserver captures the push deterministically — the player
      // screen does its own async (file) load, so asserting it is *present*
      // after settle is flaky; asserting it was *pushed* is exact.
      final observer = _RecordingNavigatorObserver();
      await tester.pumpWidget(MaterialApp(
        home: const MyToursScreen(),
        navigatorObservers: [observer],
      ));
      // Let _loadTours + the post-frame open run.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // The request was consumed (opened or not, it fires at most once).
      expect(PendingListenOpen.instance.request.value, isNull);
      // The player screen was pushed for the matching tour.
      expect(observer.pushedTourPlayer, isTrue);
    });

    testWidgets('no matching tour → request is still consumed, no player',
        (tester) async {
      SharedPreferences.setMockInitialValues({
        'saved_tours': [
          '{"title":"Other","path":"/tmp/x","created":"2026-10-19T00:00:00Z","tour_id":"1"}',
        ],
        'app_mode': 'Tours',
      });
      PendingListenOpen.instance.consume();
      PendingListenOpen.instance.offer('999'); // not in saved_tours

      await tester.pumpWidget(const MaterialApp(home: MyToursScreen()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(PendingListenOpen.instance.request.value, isNull);
      expect(find.byType(TourPlayerScreen), findsNothing);
    });
  });
}

/// Records route pushes. Used instead of finding the player in the tree,
/// because [TourPlayerScreen] runs its own async (file) load and asserting its
/// presence after a settle is flaky. The MyToursScreen itself is pushed as the
/// first route; a second push is the tour player opened by the pending request.
class _RecordingNavigatorObserver extends NavigatorObserver {
  int pushCount = 0;
  bool get pushedTourPlayer => pushCount >= 2;

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    pushCount++;
    super.didPush(route, previousRoute);
  }
}
