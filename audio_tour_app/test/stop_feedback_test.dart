import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/widgets/swipe_feedback_widget.dart';
import 'package:audio_tour_app_dev/services/stop_feedback_service.dart';
import 'package:audio_tour_app_dev/services/outbox_service.dart';

/// Widget + unit tests for the swipe feedback (like/dislike) feature.
///
/// LOCAL-670C: per-stop thumbs moved OFF their own `swipe_feedback_queue` and
/// into the single offline [OutboxService] as `thumb` items (so they share the
/// one durable queue, connectivity/lifecycle sync, backoff and 90-day expiry).
/// These tests therefore read the PENDING QUEUE through the service's
/// [StopFeedbackService.getPendingQueue] (which returns the flat
/// stop_index/swipe/tour_id/user_id shape), not the retired raw key. The thumb
/// is an INTERNAL signal (D650) — these tests assert it is QUEUED, nothing about
/// the tour score.
///
/// Tests run against the SwipeFeedbackWidget in isolation (no WebView needed).
/// SharedPreferences are mocked to provide user_id; test mode disables the
/// outbox's network flush and timers.

Future<List<Map<String, dynamic>>> pendingThumbs() =>
    StopFeedbackService().getPendingQueue();

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'test_user_swipe',
      'server_mode': 'local',
      'server_ip': '192.168.0.218',
    });
    // Prevent network flush and timer leaks in tests.
    StopFeedbackService.enableTestMode();
    await OutboxService.instance.resetForTest();
  });

  group('SwipeFeedbackWidget — Like', () {
    testWidgets('shows like and dislike buttons in idle state', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'test_tour_123',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      expect(find.text('More like this'), findsOneWidget);
      expect(find.text('Not for me'), findsOneWidget);
      expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
      expect(find.byIcon(Icons.thumb_down_outlined), findsOneWidget);
    });

    testWidgets('tapping like shows confirmation with undo', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'test_tour_123',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // The confirmation names the stop (LOCAL-670: "…for this stop").
      expect(find.textContaining('Noted — more like this'), findsOneWidget);
      expect(find.text('Undo'), findsOneWidget);
      expect(find.text('More like this'), findsNothing);
      expect(find.text('Not for me'), findsNothing);
    });

    testWidgets('like queues a +1 thumb in the outbox', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 2,
            tourId: 'tour_abc',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final queue = await pendingThumbs();
      expect(queue.length, 1);
      expect(queue[0]['stop_index'], 2);
      expect(queue[0]['swipe'], 1);
      expect(queue[0]['tour_id'], 'tour_abc');
      expect(queue[0]['user_id'], 'test_user_swipe');
      // Each item carries a client UUID and a created_at (idempotency + expiry).
      expect(queue[0]['client_uuid'], isNotNull);
      expect(queue[0]['created_at'], isNotNull);
      // Neutral class defaults when no stop_metrics.json.
      expect(queue[0]['class_details'], closeTo(0.333, 0.001));
      expect(queue[0]['class_historic'], closeTo(0.333, 0.001));
      expect(queue[0]['class_social'], closeTo(0.333, 0.001));
      expect(queue[0]['i_con'], 3.0);
    });
  });

  group('SwipeFeedbackWidget — Dislike', () {
    testWidgets('tapping dislike shows negative confirmation', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 1,
            tourId: 'test_tour_456',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.textContaining('Noted — less like this'), findsOneWidget);
      expect(find.text('Undo'), findsOneWidget);
    });

    testWidgets('dislike queues a -1 thumb in the outbox', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 3,
            tourId: 'tour_def',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final queue = await pendingThumbs();
      expect(queue.length, 1);
      expect(queue[0]['stop_index'], 3);
      expect(queue[0]['swipe'], -1);
      expect(queue[0]['tour_id'], 'tour_def');
    });

    testWidgets('cannot double-swipe the same stop', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'tour_no_double',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final queue = await pendingThumbs();
      expect(queue.length, 1);
    });
  });

  group('SwipeFeedbackWidget — Undo', () {
    testWidgets('undo removes the thumb from the outbox', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'tour_undo_test',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect((await pendingThumbs()).length, 1);

      await tester.tap(find.text('Undo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect((await pendingThumbs()).length, 0);
      expect(find.text('Rating removed'), findsOneWidget);

      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('undo shows confirmation then returns to idle', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'tour_undo_ui',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Undo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Rating removed'), findsOneWidget);

      await tester.pump(const Duration(seconds: 3));

      expect(find.text('More like this'), findsOneWidget);
      expect(find.text('Not for me'), findsOneWidget);
    });
  });

  group('SwipeFeedbackWidget — Offline queue', () {
    testWidgets('swipe persists in the outbox even without network', (tester) async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'offline_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0', // unreachable
      });
      StopFeedbackService.enableTestMode();
      await OutboxService.instance.resetForTest();

      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 5,
            tourId: 'tour_offline',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final queue = await pendingThumbs();
      expect(queue.length, 1);
      expect(queue[0]['stop_index'], 5);
      expect(queue[0]['swipe'], 1);
      expect(queue[0]['tour_id'], 'tour_offline');
      expect(queue[0]['user_id'], 'offline_user');
    });

    testWidgets('multiple swipes across stops accumulate in the outbox', (tester) async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'multi_swipe_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
      });
      StopFeedbackService.enableTestMode();
      await OutboxService.instance.resetForTest();

      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'tour_multi',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 1,
            tourId: 'tour_multi',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();
      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final queue = await pendingThumbs();
      expect(queue.length, 2);
      // Order preserved (append order within the same kind).
      expect(queue[0]['stop_index'], 0);
      expect(queue[0]['swipe'], 1);
      expect(queue[1]['stop_index'], 1);
      expect(queue[1]['swipe'], -1);
    });
  });

  group('StopFeedbackService — Unit', () {
    test('queue length starts at 0', () async {
      SharedPreferences.setMockInitialValues({});
      await OutboxService.instance.resetForTest();
      final service = StopFeedbackService();
      expect(await service.queueLength, 0);
    });

    test('recordSwipe adds a thumb to the outbox', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'unit_test_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
      });
      StopFeedbackService.enableTestMode();
      await OutboxService.instance.resetForTest();

      final service = StopFeedbackService();
      await service.recordSwipe(stopIndex: 3, swipe: 1, tourId: 'unit_tour');

      expect(await service.queueLength, 1);
      final pending = await service.getPendingQueue();
      expect(pending[0]['stop_index'], 3);
      expect(pending[0]['swipe'], 1);
    });

    test('undoLastSwipe removes the thumb', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'undo_unit_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
      });
      StopFeedbackService.enableTestMode();
      await OutboxService.instance.resetForTest();

      final service = StopFeedbackService();
      await service.recordSwipe(stopIndex: 2, swipe: -1, tourId: 'undo_tour');
      expect(await service.queueLength, 1);

      final removed =
          await service.undoLastSwipe(stopIndex: 2, tourId: 'undo_tour');
      expect(removed, true);
      expect(await service.queueLength, 0);
    });

    test('undoLastSwipe returns false when entry not in queue', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'undo_empty_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
      });
      StopFeedbackService.enableTestMode();
      await OutboxService.instance.resetForTest();

      final service = StopFeedbackService();
      final removed =
          await service.undoLastSwipe(stopIndex: 5, tourId: 'no_such_tour');
      expect(removed, false);
    });
  });

  group('SwipeFeedbackWidget — Accessibility', () {
    testWidgets('buttons have semantic labels', (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: 0,
            tourId: 'a11y_tour',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();

      final likeButton = find.byWidgetPredicate(
        (w) => w is Semantics && w.properties.label == 'Like this stop',
      );
      final dislikeButton = find.byWidgetPredicate(
        (w) => w is Semantics && w.properties.label == 'Dislike this stop',
      );
      expect(likeButton, findsOneWidget);
      expect(dislikeButton, findsOneWidget);
    });
  });
}
