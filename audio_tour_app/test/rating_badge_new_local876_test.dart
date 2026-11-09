// [LOCAL-876] Tour-544 finding 2: a tour with NO ratings must show "New" with
// NO number. map_delivery's RANK_PRIOR_SCORE = 7.5 is a sort device, not a
// rating; "★ 7.5 · New" read as an evaluation (Michael). The badge shows the
// number ONLY once the tour has real ratings (display_rating != null, count > 0).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/widgets/rate_tour_dialog.dart';
import 'package:audio_tour_app_dev/services/tour_rating_service.dart';

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: Center(child: child))));
}

void main() {
  group('[LOCAL-876] TourRating.badgeText', () {
    test('unrated (display_rating null) → "New", no number', () {
      final r = TourRating.fromJson(
          {'display_rating': null, 'rating_count': 0, 'rating_label': 'New'});
      expect(r.isUnrated, isTrue);
      expect(r.badgeText, 'New');
      expect(r.badgeText.contains('7.5'), isFalse);
      expect(r.badgeText.contains('·'), isFalse);
    });

    test('count 0 with a prior score still reads as unrated "New"', () {
      // An older server that omits display_rating but sends rating_score 7.5 +
      // count 0 must still read as "New", never "7.5 · New".
      final r = TourRating.fromJson(
          {'rating_score': 7.5, 'rating_count': 0, 'rating_label': 'New'});
      expect(r.isUnrated, isTrue);
      expect(r.badgeText, 'New');
    });

    test('rated → "<score> · <label>"', () {
      final r = TourRating.fromJson(
          {'display_rating': 8.3, 'rating_count': 2, 'rating_label': '2 ratings'});
      expect(r.isUnrated, isFalse);
      expect(r.badgeText, '8.3 · 2 ratings');
    });

    test('unrated const shows "New"', () {
      expect(TourRating.unrated.isUnrated, isTrue);
      expect(TourRating.unrated.badgeText, 'New');
    });
  });

  group('[LOCAL-876] TourRatingBadge widget', () {
    testWidgets('unrated tour map → shows "New", not 7.5', (tester) async {
      await _pump(
        tester,
        TourRatingBadge.fromTour(const {
          'id': 544,
          'display_rating': null,
          'rating_count': 0,
          'rating_label': 'New',
          // the 7.5 prior is still on the record (sort/placeholder) but must
          // NOT be shown.
          'rating_score': 7.5,
        }),
      );
      expect(find.text('New'), findsOneWidget);
      expect(find.textContaining('7.5'), findsNothing);
      expect(find.textContaining('·'), findsNothing);
    });

    testWidgets('legacy server (no display_rating) unrated → "New"',
        (tester) async {
      await _pump(
        tester,
        TourRatingBadge.fromTour(const {
          'id': 544,
          'rating_score': 7.5,
          'rating_count': 0,
          'rating_label': 'New',
        }),
      );
      expect(find.text('New'), findsOneWidget);
      expect(find.textContaining('7.5'), findsNothing);
    });

    testWidgets('rated tour map → shows "8.3 · 2 ratings"', (tester) async {
      await _pump(
        tester,
        TourRatingBadge.fromTour(const {
          'id': 544,
          'display_rating': 8.3,
          'rating_count': 2,
          'rating_label': '2 ratings',
          'rating_score': 8.3,
        }),
      );
      expect(find.text('8.3 · 2 ratings'), findsOneWidget);
    });

    testWidgets('default badge (no fields) → "New", no number', (tester) async {
      await _pump(tester, const TourRatingBadge());
      expect(find.text('New'), findsOneWidget);
      expect(find.textContaining('7.5'), findsNothing);
    });
  });
}
