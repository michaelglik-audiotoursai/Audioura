import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/widgets/swipe_feedback_widget.dart';
import 'package:audio_tour_app_dev/services/stop_feedback_service.dart';
import 'dart:convert';

/// Widget tests for the swipe feedback (like/dislike) feature.
///
/// Tests run against the SwipeFeedbackWidget in isolation (no WebView needed).
/// SharedPreferences are mocked to provide user_id and the swipe queue.

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'user_id': 'test_user_swipe',
      'server_mode': 'local',
      'server_ip': '192.168.0.218',
      'swipe_feedback_queue': '[]',
    });
    // Prevent network flush and timer leaks in tests
    StopFeedbackService.enableTestMode();
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

      // Both buttons should be visible
      expect(find.text('More like this'), findsOneWidget);
      expect(find.text('Not for me'), findsOneWidget);

      // Thumbs up and down icons
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

      // Tap the like button
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Confirmation message should appear
      expect(find.text('Noted — more like this'), findsOneWidget);

      // Undo button should be visible
      expect(find.text('Undo'), findsOneWidget);

      // Original buttons should be gone
      expect(find.text('More like this'), findsNothing);
      expect(find.text('Not for me'), findsNothing);
    });

    testWidgets('like queues a +1 swipe in SharedPreferences', (tester) async {
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

      // Tap like
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Check the queue in SharedPreferences
      final prefs = await SharedPreferences.getInstance();
      final queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      final queue = jsonDecode(queueRaw) as List<dynamic>;

      expect(queue.length, 1);
      expect(queue[0]['stop_index'], 2);
      expect(queue[0]['swipe'], 1);
      expect(queue[0]['tour_id'], 'tour_abc');
      expect(queue[0]['user_id'], 'test_user_swipe');
      // Neutral defaults when no stop_metrics.json
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

      // Tap the dislike button
      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Confirmation message
      expect(find.text('Noted — less like this'), findsOneWidget);
      expect(find.text('Undo'), findsOneWidget);
    });

    testWidgets('dislike queues a -1 swipe in SharedPreferences', (tester) async {
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

      // Tap dislike
      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Check queue
      final prefs = await SharedPreferences.getInstance();
      final queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      final queue = jsonDecode(queueRaw) as List<dynamic>;

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

      // Tap dislike
      await tester.tap(find.text('Not for me'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Check queue has exactly 1 entry
      final prefs = await SharedPreferences.getInstance();
      final queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      final queue = jsonDecode(queueRaw) as List<dynamic>;
      expect(queue.length, 1);
    });
  });

  group('SwipeFeedbackWidget — Undo', () {
    testWidgets('undo removes swipe from queue', (tester) async {
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

      // Like the stop
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Verify it's queued
      var prefs = await SharedPreferences.getInstance();
      var queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      var queue = jsonDecode(queueRaw) as List<dynamic>;
      expect(queue.length, 1);

      // Tap undo
      await tester.tap(find.text('Undo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // Queue should be empty
      prefs = await SharedPreferences.getInstance();
      queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      queue = jsonDecode(queueRaw) as List<dynamic>;
      expect(queue.length, 0);

      // "Rating removed" message
      expect(find.text('Rating removed'), findsOneWidget);

      // Drain the 2-second "return to idle" timer
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

      // Like, then undo
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Undo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Rating removed'), findsOneWidget);

      // After 2+ seconds, returns to idle
      await tester.pump(const Duration(seconds: 3));

      expect(find.text('More like this'), findsOneWidget);
      expect(find.text('Not for me'), findsOneWidget);
    });
  });

  group('SwipeFeedbackWidget — Offline queue', () {
    testWidgets('swipe persists in queue even without network', (tester) async {
      // Simulate being offline by having no server reachable
      SharedPreferences.setMockInitialValues({
        'user_id': 'offline_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0', // unreachable
        'swipe_feedback_queue': '[]',
      });

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

      // Swipe while "offline"
      await tester.tap(find.text('More like this'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      // The swipe is in the local queue regardless of network
      final prefs = await SharedPreferences.getInstance();
      final queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      final queue = jsonDecode(queueRaw) as List<dynamic>;

      expect(queue.length, 1);
      expect(queue[0]['stop_index'], 5);
      expect(queue[0]['swipe'], 1);
      expect(queue[0]['tour_id'], 'tour_offline');
      expect(queue[0]['user_id'], 'offline_user');
    });

    testWidgets('multiple swipes across stops accumulate in queue', (tester) async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'multi_swipe_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
        'swipe_feedback_queue': '[]',
      });

      // Stop 0 — like
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

      // Stop 1 — dislike (rebuild widget with new stop index)
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

      // Check both are queued
      final prefs = await SharedPreferences.getInstance();
      final queueRaw = prefs.getString('swipe_feedback_queue') ?? '[]';
      final queue = jsonDecode(queueRaw) as List<dynamic>;

      expect(queue.length, 2);
      expect(queue[0]['stop_index'], 0);
      expect(queue[0]['swipe'], 1);
      expect(queue[1]['stop_index'], 1);
      expect(queue[1]['swipe'], -1);
    });
  });

  group('StopFeedbackService — Unit', () {
    test('queue length starts at 0', () async {
      SharedPreferences.setMockInitialValues({
        'swipe_feedback_queue': '[]',
      });
      final service = StopFeedbackService();
      expect(await service.queueLength, 0);
    });

    test('recordSwipe adds to queue', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'unit_test_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
        'swipe_feedback_queue': '[]',
      });

      final service = StopFeedbackService();
      await service.recordSwipe(
        stopIndex: 3,
        swipe: 1,
        tourId: 'unit_tour',
      );

      expect(await service.queueLength, 1);
      final pending = await service.getPendingQueue();
      expect(pending[0]['stop_index'], 3);
      expect(pending[0]['swipe'], 1);
    });

    test('undoLastSwipe removes from queue', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'undo_unit_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
        'swipe_feedback_queue': '[]',
      });

      final service = StopFeedbackService();
      await service.recordSwipe(
        stopIndex: 2,
        swipe: -1,
        tourId: 'undo_tour',
      );
      expect(await service.queueLength, 1);

      final removed = await service.undoLastSwipe(
        stopIndex: 2,
        tourId: 'undo_tour',
      );
      expect(removed, true);
      expect(await service.queueLength, 0);
    });

    test('undoLastSwipe returns false when entry not in queue', () async {
      SharedPreferences.setMockInitialValues({
        'user_id': 'undo_empty_user',
        'server_mode': 'local',
        'server_ip': '0.0.0.0',
        'swipe_feedback_queue': '[]',
      });

      final service = StopFeedbackService();
      final removed = await service.undoLastSwipe(
        stopIndex: 5,
        tourId: 'no_such_tour',
      );
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

      // Check that semantic labels exist via Semantics finder
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
