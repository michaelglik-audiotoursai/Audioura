// [LOCAL-739 / SUBSCRIBED C0] Tests for the single Communities page and its
// four entry points (About for everyone; Home chip / Generate link / Listen
// row for members only), plus the members-only tour → join → download → Listen
// flow.
//
// These run OFFLINE: the Communities HTTP calls fail transport-side and return
// their safe defaults, and the pure helpers / extracted widgets need no network
// at all. The members-only ENTRY-POINT widgets are driven directly (the hub,
// and the extracted ListenMyCommunitiesRow / Generate link) so the "members see
// it, non-members do not" contract is deterministic.
//
// Includes the required RED test: the Listen "My communities" row is HIDDEN for
// a non-member (count 0) and SHOWN for a member (count > 0). Re-introducing the
// always-present row (ignoring the count) makes the non-member case fail.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/screens/communities_hub_screen.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // Empty prefs → no user_id → Communities calls return safe defaults; the
    // screens build deterministically.
    SharedPreferences.setMockInitialValues({});
  });

  group('CommunityRules.hasAnyCommunity (§2 members-only gate)', () {
    test('a user with no joined and no owned community is NOT a member', () {
      expect(
          CommunityRules.hasAnyCommunity(joinedCount: 0, ownedCount: 0),
          isFalse);
    });
    test('a user who joined ≥ 1 community IS a member', () {
      expect(
          CommunityRules.hasAnyCommunity(joinedCount: 1, ownedCount: 0),
          isTrue);
    });
    test('an organiser (owns ≥ 1) with no membership row IS a member', () {
      expect(
          CommunityRules.hasAnyCommunity(joinedCount: 0, ownedCount: 2),
          isTrue);
    });
  });

  group('CommunityRules.membersOnlyTourGate (§3)', () {
    test('names the community when known', () {
      expect(CommunityRules.membersOnlyTourGate('The Owls'),
          'This tour is for members of The Owls.');
    });
    test('falls back to a generic wording when the name is unknown', () {
      expect(CommunityRules.membersOnlyTourGate(null),
          'This tour is for members of a community.');
      expect(CommunityRules.membersOnlyTourGate(''),
          'This tour is for members of a community.');
    });
  });

  group('CommunityRules.yourCommunitiesCount (Listen row N)', () {
    test('counts distinct ids across joined and owned', () {
      expect(
          CommunityRules.yourCommunitiesCount(
              joinedIds: [1, 2], ownedIds: [3]),
          3);
    });
    test('a community in BOTH lists is counted once', () {
      expect(
          CommunityRules.yourCommunitiesCount(
              joinedIds: [1, 2], ownedIds: [2, 3]),
          3);
    });
    test('no communities → 0', () {
      expect(
          CommunityRules.yourCommunitiesCount(joinedIds: [], ownedIds: []),
          0);
    });
  });

  group('YourCommunity.merge (§1 one list, no second copy)', () {
    test('organiser rows come first, member-only rows after, de-duplicated', () {
      final joined = [
        const JoinedCommunity(id: 1, name: 'Joined A', active: true),
        const JoinedCommunity(id: 2, name: 'Both', active: true),
      ];
      final owned = [
        const OwnedCommunityRef(id: 2, name: 'Both'),
        const OwnedCommunityRef(id: 3, name: 'Owned C'),
      ];
      final merged = YourCommunity.merge(joined: joined, owned: owned);

      // 3 distinct communities (id 2 appears once).
      expect(merged.map((e) => e.id).toList(), [2, 3, 1]);
      // id 2 and 3 are organiser rows; id 1 is a member-only row.
      expect(merged[0].isOrganiser, isTrue); // id 2 (also joined)
      expect(merged[0].joined, isNotNull); // keeps the membership/expiry
      expect(merged[1].isOrganiser, isTrue); // id 3 owned-only
      expect(merged[1].joined, isNull);
      expect(merged[2].isOrganiser, isFalse); // id 1 member-only
      expect(merged[2].joined, isNotNull);
    });

    test('empty on both sides → empty list', () {
      expect(YourCommunity.merge(joined: const [], owned: const []), isEmpty);
    });
  });

  group('CommunitiesHubScreen (§1 the single page)', () {
    testWidgets('shows the four sections and the empty Your-communities state',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: CommunitiesHubScreen()));
      // Let _load() resolve (offline → empty lists).
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      // (1) Your communities — header + empty state (no communities offline).
      expect(find.byKey(const Key('hub_your_communities_header')),
          findsOneWidget);
      expect(find.byKey(const Key('hub_your_communities_empty')),
          findsOneWidget);
      // (2) Join with a code.
      expect(find.text('Join with a code'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Invite code'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Join'), findsOneWidget);
      // (3) Start a community.
      expect(find.widgetWithText(ElevatedButton, 'Start a community'),
          findsOneWidget);
      // (4) About communities (behind a link at the bottom).
      expect(find.byKey(const Key('hub_about_communities')), findsOneWidget);
    });
  });

  group('ListenMyCommunitiesRow (§2 Listen row) — RED TEST', () {
    testWidgets('RED: hidden for a non-member (count 0), shown for a member',
        (tester) async {
      // Non-member: the row must NOT be shown. (Fails if an always-present row
      // ignoring the count is re-introduced.)
      await tester.pumpWidget(_wrap(
          ListenMyCommunitiesRow(count: 0, onTap: () {})));
      await tester.pump();
      expect(find.byKey(const Key('listen_my_communities_row')), findsNothing);

      // Member: the row IS shown, with the count in its label.
      await tester.pumpWidget(_wrap(
          ListenMyCommunitiesRow(count: 3, onTap: () {})));
      await tester.pump();
      expect(
          find.byKey(const Key('listen_my_communities_row')), findsOneWidget);
      expect(find.text('My communities (3)'), findsOneWidget);
    });

    testWidgets('tapping the member row fires its onTap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_wrap(
          ListenMyCommunitiesRow(count: 1, onTap: () => tapped = true)));
      await tester.pump();
      await tester.tap(find.byKey(const Key('listen_my_communities_row')));
      expect(tapped, isTrue);
    });
  });

  group('§3 members-only tour → after a granted pass, Listen opens on it', () {
    setUp(() => PendingListenOpen.instance.consume());

    test(
        'PendingListenOpen.offer(tourId) arms a Listen-open request for that tour',
        () {
      // This is the exact mechanism CommunityPageScreen._maybeDownloadPendingTour
      // uses after a granted pass + a successful download to open the Listen tab
      // on the just-downloaded tour — the same path every other download uses.
      PendingListenOpen.instance.consume();
      expect(PendingListenOpen.instance.request.value, isNull);

      PendingListenOpen.instance.offer('4242');

      final req = PendingListenOpen.instance.request.value;
      expect(req, isNotNull);
      expect(req!.tourIds, contains('4242'));
      expect(req.tourId, '4242');

      PendingListenOpen.instance.consume();
    });
  });
}
