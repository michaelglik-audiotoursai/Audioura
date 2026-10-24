// [LOCAL-756 C] Home map / search / detail: a community tour shows its
// community sign + name and a MEMBERSHIP price line, never "Free".
//
// /tours-near returns community tours (716, 733, 735) with
//   community_id: 10, community_name: "Salem TV show funs",
//   community_visibility: "members"
// but on aeaae8f9 home_screen never read community_name and the detail said the
// tour was free. These tests drive the pure CommunityRules helpers the Home UI
// now uses, so they are RED on aeaae8f9 (the helpers do not exist) and GREEN
// after the fix.
//
// Run: flutter test test/home_community_sign_local756_test.dart

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';

void main() {
  // The exact /tours-near community-tour shape from the ticket.
  Map<String, dynamic> communityTour({String visibility = 'members'}) => {
        'id': 716,
        'name': 'Salem downtown walk',
        'community_id': 10,
        'community_name': 'Salem TV show funs',
        'community_visibility': visibility,
        'price_label': 'Free', // server money label — must NOT be shown
      };

  group('LOCAL-756 C — community sign', () {
    test('community tour shows the community name as its sign', () {
      final sign = CommunityRules.homeTourCommunitySign(communityTour());
      expect(sign, 'Salem TV show funs');
    });

    test('community sign appends the organiser when known', () {
      final t = communityTour()..['community_organiser_name'] = 'Betty';
      expect(CommunityRules.homeTourCommunitySign(t),
          'Salem TV show funs — Betty');
    });

    test('a plain Audioura tour has no community sign', () {
      final sign = CommunityRules.homeTourCommunitySign({
        'id': 1,
        'name': 'City walk',
        'price_label': '\$4.99',
      });
      expect(sign, '');
    });
  });

  group('LOCAL-756 C / D706 — price line', () {
    test('MEMBER of the community → "Included with membership", never Free', () {
      final line = CommunityRules.homeTourPriceLine(
        communityTour(),
        isMember: true,
        moneyPriceLabel: 'Free',
      );
      expect(line, 'Included with membership');
      expect(line, isNot(contains('Free')));
    });

    test('NON-MEMBER, members-only community → "Members only — join <name>"', () {
      final line = CommunityRules.homeTourPriceLine(
        communityTour(visibility: 'members'),
        isMember: false,
        moneyPriceLabel: 'Free',
      );
      expect(line, 'Members only — join Salem TV show funs');
      expect(line, isNot(equals('Free')));
    });

    test('public community tour (D706) → "Community tour — join to download"', () {
      final line = CommunityRules.homeTourPriceLine(
        communityTour(visibility: 'listed'),
        isMember: false,
        moneyPriceLabel: 'Free',
      );
      expect(line, 'Community tour — join to download');
      expect(line, isNot(equals('Free')));
    });

    test('plain Audioura tour keeps its money price line', () {
      final paid = CommunityRules.homeTourPriceLine(
        {'id': 2, 'name': 'Paid walk'},
        isMember: false,
        moneyPriceLabel: '\$4.99',
      );
      expect(paid, '\$4.99');

      final free = CommunityRules.homeTourPriceLine(
        {'id': 3, 'name': 'Free walk'},
        isMember: false,
        moneyPriceLabel: null,
      );
      expect(free, 'Free');
    });
  });

  group('LOCAL-756 C — isCommunityTour', () {
    test('true for a tour carrying a community id / name', () {
      expect(CommunityRules.isCommunityTour(communityTour()), isTrue);
    });
    test('false for a plain Audioura tour', () {
      expect(
          CommunityRules.isCommunityTour({'id': 9, 'name': 'Plain'}), isFalse);
    });
  });
}
