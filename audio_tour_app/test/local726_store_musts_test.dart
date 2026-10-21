// [LOCAL-726] Flutter-side unit tests for the two App Store must-haves that
// have app logic to test without a network or a running app:
//
//   item 10 (block): the new models parse the server's JSON shapes defensively —
//     CommunityMember, CommunityBlock, and Community.ownerUserId — and the
//     block-kind predicates read correctly.
//   item 2 (first-run notice): InformationalNoticeScreen.seen()/markSeen() gate
//     once per device under a VERSIONED key; a device that has not acked returns
//     false (shown) and returns true forever after markSeen (not shown again).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/screens/informational_notice_screen.dart';

void main() {
  group('LOCAL-726 item 10 — block model parsing', () {
    test('Community parses owner_user_id (the block target)', () {
      final c = Community.fromJson({
        'id': 7,
        'name': 'Walking Club',
        'owner_user_id': 'USER-owner',
        'organiser': {'name': 'Jane'},
        'has_waiver': false,
        'is_paid': true,
        'is_owner': false,
        'my_status': {'is_member': true, 'active': true},
      });
      expect(c.ownerUserId, 'USER-owner');
      expect(c.isOwner, false);
    });

    test('Community tolerates a missing owner_user_id (older payload)', () {
      final c = Community.fromJson({
        'id': 1,
        'name': 'X',
        'organiser': <String, dynamic>{},
        'has_waiver': false,
        'is_paid': true,
        'is_owner': true,
        'my_status': <String, dynamic>{'is_member': false, 'active': false},
      });
      expect(c.ownerUserId, isNull);
    });

    test('CommunityMember parses user/active/barred', () {
      final m = CommunityMember.fromJson({
        'user_id': 'USER-123',
        'expires_at': '2026-12-31T00:00:00',
        'active': true,
        'barred': false,
      });
      expect(m.userId, 'USER-123');
      expect(m.active, isTrue);
      expect(m.barred, isFalse);
    });

    test('CommunityMember defaults are safe when fields are missing', () {
      final m = CommunityMember.fromJson({'user_id': 'U'});
      expect(m.active, isFalse);
      expect(m.barred, isFalse);
      expect(m.expiresAt, isNull);
    });

    test('CommunityBlock parses both kinds and the isOrganiserBar predicate', () {
      final memberBlock = CommunityBlock.fromJson({
        'community_id': 3,
        'community_name': 'Book Club',
        'blocked_user_id': 'USER-org',
        'kind': 'member_block',
        'created_at': '2026-10-21T00:00:00',
      });
      expect(memberBlock.communityId, 3);
      expect(memberBlock.communityName, 'Book Club');
      expect(memberBlock.blockedUserId, 'USER-org');
      expect(memberBlock.isOrganiserBar, isFalse);

      final bar = CommunityBlock.fromJson({
        'community_id': 3,
        'blocked_user_id': 'USER-member',
        'kind': 'organiser_bar',
      });
      expect(bar.isOrganiserBar, isTrue);
      expect(bar.communityName, isNull);
    });
  });

  group('LOCAL-726 item 2 — first-run informational notice ack', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('a fresh device has NOT seen the notice (shown once)', () async {
      expect(await InformationalNoticeScreen.seen(), isFalse);
    });

    test('markSeen makes seen() true forever after (not shown again)', () async {
      expect(await InformationalNoticeScreen.seen(), isFalse);
      await InformationalNoticeScreen.markSeen();
      expect(await InformationalNoticeScreen.seen(), isTrue);
      // A second markSeen is idempotent.
      await InformationalNoticeScreen.markSeen();
      expect(await InformationalNoticeScreen.seen(), isTrue);
    });

    test('an existing install that already set onboarding_complete still '
        'has not seen the notice (shown once after the update)', () async {
      // Simulate an existing install: onboarding done, but no notice ack key.
      SharedPreferences.setMockInitialValues({'onboarding_complete': true});
      expect(await InformationalNoticeScreen.seen(), isFalse,
          reason: 'existing installs must see the notice once after updating');
    });

    test('the ack key is versioned and the Terms URL is the published one', () {
      expect(InformationalNoticeScreen.ackKey, 'info_notice_ack_v1');
      expect(InformationalNoticeScreen.termsUrl, 'https://audioura.com/terms');
    });

    testWidgets('the notice renders the four required points and a Got it '
        'button that acks', (tester) async {
      SharedPreferences.setMockInitialValues({});
      var acked = false;
      await tester.pumpWidget(MaterialApp(
        home: InformationalNoticeScreen(onAcknowledged: () => acked = true),
      ));
      await tester.pumpAndSettle();
      // The four required messages (AI/errors, info-not-navigation, own risk,
      // Terms link).
      expect(find.textContaining('written with AI'), findsOneWidget);
      expect(find.textContaining('not'), findsWidgets);
      expect(find.textContaining('your own risk'), findsOneWidget);
      expect(find.text('Read the Terms'), findsOneWidget);
      // Tapping "Got it" acks and marks seen.
      await tester.tap(find.byKey(const Key('info_notice_got_it')));
      await tester.pumpAndSettle();
      expect(acked, isTrue);
      expect(await InformationalNoticeScreen.seen(), isTrue);
    });
  });
}
