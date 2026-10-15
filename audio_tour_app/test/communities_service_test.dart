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
        'is_paid': true, 'badge': 'community', 'member_count': 12
      });
      expect(p.badge, 'community');
      expect(p.isPaid, isTrue);
      // [LOCAL-704 / D665] the map pin sheet carries the member count.
      expect(p.memberCount, 12);
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

  // [LOCAL-690C / LOCAL-704] The pass catalogue is ONE store product per PRICE;
  // the LENGTH is sent separately. No length in the product id. LOCAL-704 added
  // a $1 floor (the commitment fee, D665), so the ladder is now 35 prices.
  group('community pass product ids (one per price)', () {
    test('35 ladder prices with a \$1 floor, ids audioura.pass.usd<N>', () {
      expect(kPassLadderDollars.length, 35);
      expect(kPassStoreIds.length, 35);
      // The $1 commitment-fee floor (D665) and the top of the ladder.
      expect(kPassLadderDollars.first, 1);
      expect(kPassStoreIds.contains('audioura.pass.usd1'), isTrue);
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

  // ── [LOCAL-700] round-1 copy + create-form logic (pure, Flutter-free) ───────
  group('CommunityCopy — §1 description text', () {
    test('about text names BOTH kinds of content', () {
      const t = CommunityCopy.aboutContent;
      // Owner's own audio (links / RSS feed, not stored, not checked).
      expect(t.contains('Your own audio'), isTrue);
      expect(t.toLowerCase().contains('rss feed'), isTrue);
      expect(t.toLowerCase().contains('does not store'), isTrue);
      // Tours made with Audioura, checked (content rating), members-only.
      expect(t.contains('made with Audioura'), isTrue);
      expect(t.toLowerCase().contains('content rating'), isTrue);
    });

    test('create intro also covers both kinds', () {
      final t = CommunityCopy.createIntro.toLowerCase();
      expect(t.contains('your own audio'), isTrue);
      expect(t.contains('made with audioura'), isTrue);
    });

    test('close warning: cannot be closed, can step down', () {
      final w = CommunityCopy.closeWarning.toLowerCase();
      expect(w.contains('cannot be closed'), isTrue);
      expect(w.contains('step down'), isTrue);
    });
  });

  group('CommunityCopy — §4 prefill pools (≥ 8 variants each)', () {
    test('every pool has at least 8 non-empty variants', () {
      final pools = <String, List<String>>{
        'namePrefixes': CommunityCopy.namePrefixes,
        'descriptions': CommunityCopy.descriptions,
        'organiserNames': CommunityCopy.organiserNames,
        'bios': CommunityCopy.bios,
        'rules': CommunityCopy.rules,
      };
      pools.forEach((name, pool) {
        expect(pool.length, greaterThanOrEqualTo(8), reason: name);
        for (final v in pool) {
          expect(v.trim().isNotEmpty, isTrue, reason: '$name has an empty item');
        }
      });
    });
  });

  group('CommunityCopy.uniqueName — §4 unique generated name', () {
    test('attempt 0 is the plain "<stem> of <place>"', () {
      expect(CommunityCopy.uniqueName('The Wandering Owls', 'Lisbon'),
          'The Wandering Owls of Lisbon');
    });
    test('a later attempt appends a short suffix', () {
      final a1 = CommunityCopy.uniqueName('The Owls', 'Porto', attempt: 1);
      expect(a1.startsWith('The Owls of Porto'), isTrue);
      expect(a1 == 'The Owls of Porto', isFalse); // a suffix was added
    });
    test('empty place drops the " of ..." tail', () {
      expect(CommunityCopy.uniqueName('The Owls', ''), 'The Owls');
    });
  });

  group('CommunityCopy.emailInviteBody — §4 email contains code + install', () {
    test('ALWAYS contains the code and the install line', () {
      final body = CommunityCopy.emailInviteBody(
        communityName: 'Night Owls',
        description: 'We walk at night.',
        organiserName: 'Sam',
        code: 'AB12CD34',
      );
      // The exact join instruction with the code.
      expect(body.contains('AB12CD34'), isTrue);
      expect(body.contains('Search'), isTrue);
      // The install line (App Store / Google Play via audioura.com for now).
      expect(body.contains(CommunityCopy.installUrl), isTrue);
      // Carries the name, description and organiser.
      expect(body.contains('Night Owls'), isTrue);
      expect(body.contains('We walk at night.'), isTrue);
      expect(body.contains('Sam'), isTrue);
    });

    test('code + install present even with no description / organiser', () {
      final body = CommunityCopy.emailInviteBody(
        communityName: 'Minimal',
        code: 'ZZ99ZZ99',
      );
      expect(body.contains('ZZ99ZZ99'), isTrue);
      expect(body.contains(CommunityCopy.installUrl), isTrue);
    });
  });

  group('CommunityCopy — §4 required-field gating', () {
    test('all required present (non-listed) -> filled', () {
      expect(
        CommunityCopy.requiredFieldsFilled(
          name: 'C', description: 'D', organiserName: 'O', rules: 'R',
          listed: false,
        ),
        isTrue,
      );
    });
    test('any missing required field -> not filled', () {
      expect(
        CommunityCopy.requiredFieldsFilled(
          name: '', description: 'D', organiserName: 'O', rules: 'R',
          listed: false,
        ),
        isFalse,
      );
      expect(
        CommunityCopy.requiredFieldsFilled(
          name: 'C', description: 'D', organiserName: 'O', rules: '   ',
          listed: false,
        ),
        isFalse,
      );
    });
    test('listed requires a location; private does not', () {
      expect(
        CommunityCopy.requiredFieldsFilled(
          name: 'C', description: 'D', organiserName: 'O', rules: 'R',
          listed: true,
        ),
        isFalse,
      );
      expect(
        CommunityCopy.requiredFieldsFilled(
          name: 'C', description: 'D', organiserName: 'O', rules: 'R',
          listed: true, latitude: '42.0', longitude: '-71.0',
        ),
        isTrue,
      );
    });

    test('createEnabled needs filled + terms; known-taken name blocks', () {
      // Not enabled until the terms are accepted.
      expect(
        CommunityCopy.createEnabled(requiredFilled: true, termsAccepted: false),
        isFalse,
      );
      // Enabled when filled + terms, name unknown (null) does NOT block.
      expect(
        CommunityCopy.createEnabled(
            requiredFilled: true, termsAccepted: true, nameAvailable: null),
        isTrue,
      );
      // A known-taken name (false) blocks even when everything else is ready.
      expect(
        CommunityCopy.createEnabled(
            requiredFilled: true, termsAccepted: true, nameAvailable: false),
        isFalse,
      );
      // A confirmed-free name (true) is fine.
      expect(
        CommunityCopy.createEnabled(
            requiredFilled: true, termsAccepted: true, nameAvailable: true),
        isTrue,
      );
    });
  });

  group('LOCAL-702 hand-over state parsing (D663 §1)', () {
    test('active community defaults — accepts new members, not looking', () {
      final c = Community.fromJson({
        'id': 1,
        'name': 'Active One',
        'status': 'active',
      });
      expect(c.status, 'active');
      expect(c.lookingForOrganiser, isFalse);
      expect(c.archived, isFalse);
      expect(c.acceptsNewMembers, isTrue);
      expect(c.myOffer, isNull);
      expect(c.organiserOffers, isEmpty);
    });

    test('older payload with no status still parses as active', () {
      final c = Community.fromJson({'id': 2, 'name': 'Legacy'});
      expect(c.status, 'active');
      expect(c.acceptsNewMembers, isTrue);
      expect(c.lookingForOrganiser, isFalse);
    });

    test('handover community — looking, closed, offers parsed', () {
      final c = Community.fromJson({
        'id': 3,
        'name': 'Handing Over',
        'status': 'handover',
        'looking_for_organiser': true,
        'accepts_new_members': false,
        'stepped_down_at': '2026-10-15T00:00:00',
        'my_offer': {'status': 'picked', 'picked': true},
        'organiser_offers': [
          {'member_user_id': 'u-1', 'status': 'offered'},
          {'member_user_id': 'u-2', 'status': 'picked', 'picked_at': 'x'},
        ],
      });
      expect(c.lookingForOrganiser, isTrue);
      expect(c.acceptsNewMembers, isFalse);
      expect(c.steppedDownAt, isNotNull);
      expect(c.myOffer, isNotNull);
      expect(c.myOffer!.picked, isTrue);
      expect(c.organiserOffers.length, 2);
      expect(c.organiserOffers[1].isPicked, isTrue);
    });

    test('archived community — archived flags set, closed to new members', () {
      final c = Community.fromJson({
        'id': 4,
        'name': 'Archived',
        'status': 'archived',
        'archived': true,
        'accepts_new_members': false,
        'archived_at': '2026-11-15T00:00:00',
      });
      expect(c.archived, isTrue);
      expect(c.acceptsNewMembers, isFalse);
      expect(c.lookingForOrganiser, isFalse);
      expect(c.archivedAt, isNotNull);
    });

    test('MyOffer null-safe parsing', () {
      expect(MyOffer.fromJson(null).status, 'none');
      expect(MyOffer.fromJson(null).picked, isFalse);
      final o = MyOffer.fromJson({'status': 'offered', 'picked': false});
      expect(o.status, 'offered');
      expect(o.picked, isFalse);
    });
  });

  // ── [LOCAL-704 / D665] member count everywhere ──────────────────────────────
  group('LOCAL-704 member count (D665)', () {
    test('Community.fromJson parses member_count', () {
      final c = Community.fromJson(
          {'id': 1, 'name': 'C', 'member_count': 7});
      expect(c.memberCount, 7);
    });

    test('member_count defaults to 0 when absent', () {
      expect(Community.fromJson({'id': 1, 'name': 'C'}).memberCount, 0);
    });

    test('JoinedCommunity parses member_count', () {
      final j = JoinedCommunity.fromJson(
          {'id': 1, 'name': 'C', 'active': true, 'member_count': 3});
      expect(j.memberCount, 3);
    });

    test('memberCountLabel: singular vs plural', () {
      expect(CommunityCopy.memberCountLabel(0), '0 members');
      expect(CommunityCopy.memberCountLabel(1), '1 member');
      expect(CommunityCopy.memberCountLabel(12), '12 members');
    });

    test('invite email carries the member count ("12 members")', () {
      final body = CommunityCopy.emailInviteBody(
        communityName: 'Owls',
        organiserName: 'Alex',
        code: 'AB12CD34',
        memberCount: 12,
      );
      expect(body.contains('12 members'), isTrue);
      expect(body.contains('AB12CD34'), isTrue);
    });

    test('about text no longer offers free communities (D665)', () {
      // Every community is paid now — the "free (like a book club)" line is gone.
      expect(CommunityCopy.aboutContent.contains('free (like a book club)'),
          isFalse);
      expect(CommunityCopy.aboutContent.contains('at least \$1'), isTrue);
    });
  });
}
