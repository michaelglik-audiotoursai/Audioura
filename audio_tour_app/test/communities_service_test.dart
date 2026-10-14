// [LOCAL-690] Communities client — pure helper + parsing unit tests.
//
// These cover the Flutter-side rules without a running app or network:
//   * origin label: "Audioura" for no community; the community name, and
//     "name — organiser" when an organiser is known (D658 addendum 2 §3).
//   * join framing: the exact "This tour belongs to <X>. Join to listen" copy.
//   * forced visibility: a waiver community is always Private (D658/D656).
//   * download-by-default for a community tour (D658 addendum §).
//   * defensive JSON parsing: missing fields never throw; a pass product id is
//     recognised; the community page payload maps every field.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/iap_service.dart';

void main() {
  group('CommunityRules.originLabel', () {
    test('no community -> Audioura', () {
      expect(CommunityRules.originLabel(), 'Audioura');
      expect(CommunityRules.originLabel(communityName: ''), 'Audioura');
    });

    test('community only -> name', () {
      expect(CommunityRules.originLabel(communityName: 'Walking Club'),
          'Walking Club');
    });

    test('community + organiser -> name — organiser', () {
      expect(
          CommunityRules.originLabel(
              communityName: 'Walking Club', organiserName: 'Jane'),
          'Walking Club — Jane');
    });
  });

  group('CommunityRules.joinFraming', () {
    test('exact server wording', () {
      expect(CommunityRules.joinFraming('Book Club'),
          'This tour belongs to Book Club. Join to listen.');
    });
  });

  group('CommunityRules.forcedVisibility', () {
    test('a waiver community is always private', () {
      expect(
          CommunityRules.forcedVisibility(hasWaiver: true, requested: 'listed'),
          'private');
    });
    test('no waiver keeps the requested visibility', () {
      expect(
          CommunityRules.forcedVisibility(hasWaiver: false, requested: 'listed'),
          'listed');
      expect(
          CommunityRules.forcedVisibility(hasWaiver: false, requested: 'private'),
          'private');
    });
  });

  test('community tours download by default', () {
    expect(CommunityRules.downloadByDefault(), isTrue);
  });

  group('Community.fromJson (defensive)', () {
    test('maps a full page payload', () {
      final c = Community.fromJson({
        'id': 7,
        'name': 'Walking Club',
        'description': 'A club',
        'organiser': {'name': 'Jane', 'bio': 'guide', 'contact': 'j@x.com'},
        'rules_text': 'Be kind',
        'waiver_text': null,
        'has_waiver': false,
        'is_paid': true,
        'visibility': 'listed',
        'disabled': false,
        'latitude': 42.0,
        'longitude': -71.0,
        'passes': [
          {
            'product_id': 'audioura.pass.usd5',
            'length': 'month',
            'duration_days': 30,
            'price_usd': 5.0,
            'label': r'$5 / month'
          }
        ],
        'episodes': [
          {
            'position': 1,
            'title': 'Stop 1',
            'audio_url': 'https://h/1.mp3',
            'guid': 'g1',
            'source': 'feed'
          }
        ],
        'episode_count': 1,
        'is_owner': false,
        'my_status': {'is_member': true, 'active': true, 'expires_at': '2026-12-01T00:00:00'},
      });
      expect(c.id, 7);
      expect(c.name, 'Walking Club');
      expect(c.organiser.name, 'Jane');
      expect(c.isPaid, isTrue);
      expect(c.visibility, 'listed');
      expect(c.passes.single.label, r'$5 / month');
      expect(c.passes.single.productId, 'audioura.pass.usd5');
      expect(c.passes.single.length, 'month');
      expect(c.passes.single.durationDays, 30);
      expect(c.episodes.single.position, 1);
      expect(c.episodes.single.source, 'feed');
      expect(c.myStatus.isMember, isTrue);
      expect(c.myStatus.active, isTrue);
    });

    test('missing fields never throw and fall back safely', () {
      final c = Community.fromJson({'id': 1, 'name': 'X'});
      expect(c.description, isNull);
      expect(c.passes, isEmpty);
      expect(c.episodes, isEmpty);
      expect(c.hasWaiver, isFalse);
      expect(c.isPaid, isFalse);
      expect(c.visibility, 'private');
      expect(c.myStatus.isMember, isFalse);
    });
  });

  group('CommunityMapPin / JoinedCommunity parsing', () {
    test('map pin carries the community badge', () {
      final p = CommunityMapPin.fromJson({
        'id': 3, 'name': 'C', 'latitude': 1.0, 'longitude': 2.0,
        'is_paid': true, 'badge': 'community'
      });
      expect(p.badge, 'community');
      expect(p.isPaid, isTrue);
    });

    test('joined community active flag', () {
      final j = JoinedCommunity.fromJson({
        'id': 4, 'name': 'C', 'organiser_name': 'O', 'active': true,
        'expires_at': '2026-12-01T00:00:00'
      });
      expect(j.active, isTrue);
      expect(j.organiserName, 'O');
    });
  });

  // [LOCAL-690C] The pass catalogue is ONE store product per PRICE (the 34
  // ladder prices); the LENGTH is sent separately. No length in the product id.
  group('community pass product ids (one per price)', () {
    test('34 ladder prices, ids audioura.pass.usd<N>, no length suffix', () {
      expect(kPassLadderDollars.length, 34);
      expect(kPassStoreIds.length, 34);
      // The lowest and highest ladder steps.
      expect(kPassStoreIds.contains('audioura.pass.usd2'), isTrue);
      expect(kPassStoreIds.contains('audioura.pass.usd200'), isTrue);
      // No id carries a length suffix (one product per price).
      for (final id in kPassStoreIds) {
        expect(id.startsWith('audioura.pass.usd'), isTrue);
        expect(id.contains('.day') || id.contains('.week') ||
            id.contains('.month') || id.contains('.year'), isFalse);
      }
    });

    test('passProductForDollars + isCommunityPassProduct', () {
      expect(passProductForDollars(5), 'audioura.pass.usd5');
      expect(isCommunityPassProduct('audioura.pass.usd5'), isTrue);
      expect(isCommunityPassProduct('audioura.tour.usd5'), isFalse);
    });

    test('the four lengths are day/week/month/year', () {
      expect(kPassLengths, ['day', 'week', 'month', 'year']);
    });
  });
}
