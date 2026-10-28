// [LOCAL-795] Widget tests for the "Write a review" entry point in
// ReviewsSection (Michael, iPhone 2026-10-27: "no link to leave a note").
//
// The section is collapsible; expanding it must show, for a user who HAS the
// tour downloaded, a "Write a review" button that opens the add-review dialog —
// and for a user who does NOT, the hidden-state line "Download the tour to
// review it". Both states carry the copy line "Notes may be used to improve
// Audioura tours."
//
// The downloaded check is injected via ReviewsSection.downloadedResolver so the
// tests drive both states with no SharedPreferences and no network. The review
// LIST load is best-effort (TourReviewsService.fetchReviews swallows errors and
// returns empty), so with no server reachable the section renders its empty
// state — exactly what we want to assert the button against. SharedPreferences
// is given an empty mock so any incidental read resolves.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/widgets/reviews_section.dart';
import 'package:audio_tour_app_dev/services/tour_reviews_service.dart';

Widget _host(Widget child) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(child: child),
      ),
    );

/// Pump a bounded number of frames so the injected downloaded-resolver Future
/// and the best-effort (empty) reviews load settle, WITHOUT pumpAndSettle.
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('downloaded tour: shows "Write a review" and opens the dialog',
      (tester) async {
    await tester.pumpWidget(_host(ReviewsSection(
      tourId: '42',
      initialCount: 0,
      tourTitle: 'War Remnants Museum',
      downloadedResolver: (_) async => true,
    )));
    await _settle(tester);

    // Expand the section.
    expect(find.text('Reviews (0)'), findsOneWidget);
    await tester.tap(find.text('Reviews (0)'));
    await _settle(tester);

    // The button and the copy line are present; the hidden-state line is not.
    expect(find.text('Write a review'), findsOneWidget);
    expect(find.text('Notes may be used to improve Audioura tours.'),
        findsOneWidget);
    expect(find.text('Download the tour to review it'), findsNothing);

    // Tapping it opens the add-review dialog (reused from LOCAL-672).
    await tester.tap(find.text('Write a review'));
    await _settle(tester);
    expect(find.text('Add a short review'), findsOneWidget);
    expect(find.text('War Remnants Museum'), findsOneWidget);
  });

  testWidgets('not downloaded: shows the hidden-state line, no button',
      (tester) async {
    await tester.pumpWidget(_host(ReviewsSection(
      tourId: '42',
      initialCount: 3,
      tourTitle: 'War Remnants Museum',
      downloadedResolver: (_) async => false,
    )));
    await _settle(tester);

    await tester.tap(find.text('Reviews (3)'));
    await _settle(tester);

    expect(find.text('Download the tour to review it'), findsOneWidget);
    expect(find.text('Write a review'), findsNothing);
    // The copy line is shown in BOTH states.
    expect(find.text('Notes may be used to improve Audioura tours.'),
        findsOneWidget);
  });

  group('savedToursContainTour (pure)', () {
    test('matches on server_tour_id or tour_id, string-compared', () {
      final raw = [
        '{"server_tour_id":"431","tour_id":"abc"}',
        '{"tour_id":"42"}',
        'not json',
      ];
      expect(TourReviewsService.savedToursContainTour(raw, '431'), isTrue);
      expect(TourReviewsService.savedToursContainTour(raw, '42'), isTrue);
      expect(TourReviewsService.savedToursContainTour(raw, '999'), isFalse);
      expect(TourReviewsService.savedToursContainTour(raw, ''), isFalse);
      expect(TourReviewsService.savedToursContainTour(const [], '42'), isFalse);
    });

    test('matches a numeric id stored as a number', () {
      final raw = ['{"server_tour_id":431}'];
      expect(TourReviewsService.savedToursContainTour(raw, '431'), isTrue);
    });
  });
}
