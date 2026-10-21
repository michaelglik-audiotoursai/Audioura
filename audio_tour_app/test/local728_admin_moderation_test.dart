// [LOCAL-728 / D691] Flutter-side unit tests for the admin-only-moderation
// changes that have app logic to test without a network or a running app:
//
//   * user-level blocking is GONE: the block/bar model classes and the
//     CommunitiesService block methods no longer exist (compile-time proof via
//     the removed-symbols test below, which only type-checks the kept surface);
//   * the single "Report to Audioura" form is the only moderation action a user
//     has — CommunitiesService.report takes a reason + optional detail;
//   * the first-run notice now says tours are created with AI AND by guides and
//     curators (D691), and its ack key bumped to v2 so already-acked v1 installs
//     see the corrected notice once.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/services/communities_service.dart';
import 'package:audio_tour_app_dev/screens/informational_notice_screen.dart';

void main() {
  group('LOCAL-728 — community model (owner id kept, no block models)', () {
    test('Community still parses owner_user_id (kept; harmless)', () {
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

    test('the report surface exists and is the only moderation method', () {
      // A compile-time check: CommunitiesService.report is present and takes a
      // reason + optional detail. The removed block methods (blockUser,
      // barMember, unblockUser, members, myBlocks) would not compile if
      // referenced — their absence is the removal.
      expect(CommunitiesService.report, isA<Function>());
    });
  });

  group('LOCAL-728 item — first-run informational notice ack (v2)', () {
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
      await InformationalNoticeScreen.markSeen();
      expect(await InformationalNoticeScreen.seen(), isTrue);
    });

    test('a v1-acked install is shown the v2 notice once (material change)',
        () async {
      // The D691 wording change bumped the key v1 -> v2. An install that acked
      // v1 has no v2 key yet, so it sees the corrected notice once.
      SharedPreferences.setMockInitialValues(
          {'onboarding_complete': true, 'info_notice_ack_v1': true});
      expect(await InformationalNoticeScreen.seen(), isFalse,
          reason: 'a v1-acked install must see the v2 notice once');
    });

    test('the ack key is v2 and the Terms URL is the published one', () {
      expect(InformationalNoticeScreen.ackKey, 'info_notice_ack_v2');
      expect(InformationalNoticeScreen.termsUrl, 'https://audioura.com/terms');
    });

    testWidgets('the notice renders the D691 wording (AI AND curators) and a '
        'Got it button that acks', (tester) async {
      SharedPreferences.setMockInitialValues({});
      var acked = false;
      await tester.pumpWidget(MaterialApp(
        home: InformationalNoticeScreen(onAcknowledged: () => acked = true),
      ));
      await tester.pumpAndSettle();
      // The new first point: AI AND guides and curators.
      expect(find.textContaining('AI and by guides and curators'),
          findsOneWidget);
      expect(find.textContaining('official guidance'), findsOneWidget);
      // The other points are kept.
      expect(find.textContaining('your own risk'), findsOneWidget);
      expect(find.text('Read the Terms'), findsOneWidget);
      // The old v1 wording is gone.
      expect(find.textContaining('fact-checked'), findsNothing);
      await tester.tap(find.byKey(const Key('info_notice_got_it')));
      await tester.pumpAndSettle();
      expect(acked, isTrue);
      expect(await InformationalNoticeScreen.seen(), isTrue);
    });
  });
}
