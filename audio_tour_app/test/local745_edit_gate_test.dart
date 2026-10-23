// test/local745_edit_gate_test.dart — LOCAL-745 requirement 2 (app side, RED first).
//
// Michael: members must never see Edit on a community tour; only the community
// organiser does. A non-community (ordinary) tour keeps today's rule — anyone
// may edit.
//
// The decision is a pure top-level function canEditTour(tour, ownedCommunityIds)
// in my_tours_screen.dart (same pattern as tourVersionLabel /
// applyTourEditToSavedTours), so the My Tours menu can gate the Edit item on it
// and this test exercises the exact production rule without pumping the whole
// screen.
//
// Run: flutter test test/local745_edit_gate_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';

void main() {
  group('LOCAL-745 canEditTour — organiser-only on community tours', () {
    test('member does NOT see Edit on a community tour they do not own', () {
      final tour = {'title': 'Salem TV show funs', 'community_id': 10};
      expect(
        canEditTour(tour, ownedCommunityIds: const <int>{}),
        isFalse,
        reason: 'a member (owns no communities) must not get Edit on a '
            'community tour',
      );
    });

    test('member who owns OTHER communities still cannot edit this one', () {
      final tour = {'title': 'Salem', 'community_id': 10};
      expect(
        canEditTour(tour, ownedCommunityIds: const <int>{7, 99}),
        isFalse,
      );
    });

    test('organiser (owns this community) DOES see Edit', () {
      final tour = {'title': 'Salem', 'community_id': 10};
      expect(
        canEditTour(tour, ownedCommunityIds: const <int>{10}),
        isTrue,
      );
    });

    test('ordinary (non-community) tour is editable by anyone', () {
      final tour = {'title': 'My private tour'};
      expect(canEditTour(tour, ownedCommunityIds: const <int>{}), isTrue);
    });

    test('community_id as a String is handled', () {
      final tour = {'title': 'Salem', 'community_id': '10'};
      expect(canEditTour(tour, ownedCommunityIds: const <int>{10}), isTrue);
      expect(canEditTour(tour, ownedCommunityIds: const <int>{}), isFalse);
    });
  });
}
