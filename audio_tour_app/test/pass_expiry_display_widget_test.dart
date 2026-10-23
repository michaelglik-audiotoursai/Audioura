// [LOCAL-731 / D701] Widget tests for the member-facing pass-expiry UI.
//
// These build the extracted widgets (CommunityMyStatus, JoinedCommunitySubtitle)
// directly with an injectable `now`, so they are deterministic and need no
// network. The screens embed these SAME widgets, so the tests exercise the real
// markup.
//
// Includes the required RED test: it asserts the raw ISO `expiresAt` is NOT
// printed. Re-introducing the old `Text('Expires: ${expiresAt}')` line makes it
// fail.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/communities_models.dart';
import 'package:audio_tour_app_dev/widgets/pass_expiry_display.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  // A fixed "now" and an expiry ~30 days out (UTC, zone-less like the server).
  final now = DateTime.parse('2026-10-22T15:16:15Z');
  const activeExpiry = '2026-11-21T18:16:15.422467';

  group('CommunityMyStatus (community page)', () {
    testWidgets('active member shows formatted expiry + adds-days note',
        (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(
            isMember: true, active: true, expiresAt: activeExpiry),
        isPaid: true,
        now: now,
      )));
      await tester.pump();

      expect(find.text('Active member'), findsOneWidget);
      // The readable expiry line (not the raw ISO).
      final expiry = tester.widget<Text>(find.byKey(const Key('my_status_expiry')));
      expect(expiry.data, startsWith('Member until '));
      expect(expiry.data, contains('days left'));
      expect(expiry.data, contains('Nov 2026'));
      // The D701 "renewing adds days" note.
      expect(find.byKey(const Key('adds_days_note')), findsOneWidget);
      expect(
          find.text('Buying another pass adds its days to your remaining time.'),
          findsOneWidget);
    });

    testWidgets('non-member shows neither expiry nor adds-days note',
        (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(isMember: false, active: false),
        isPaid: true,
        now: now,
      )));
      await tester.pump();

      expect(find.text('Not a member'), findsOneWidget);
      expect(find.byKey(const Key('my_status_expiry')), findsNothing);
      expect(find.byKey(const Key('adds_days_note')), findsNothing);
    });

    testWidgets('owner sees "You are the organizer", no expiry and no note',
        (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(
            isMember: false, active: false, expiresAt: activeExpiry),
        isPaid: true,
        isOwner: true,
        now: now,
      )));
      await tester.pump();

      // [LOCAL-736] The organiser's own status says they are the organiser,
      // never "Not a member".
      expect(find.text('You are the organizer'), findsOneWidget);
      expect(find.text('Not a member'), findsNothing);
      expect(find.byKey(const Key('my_status_expiry')), findsNothing);
      expect(find.byKey(const Key('adds_days_note')), findsNothing);
    });

    testWidgets('[LOCAL-736] a non-member (not owner) still sees "Not a member"',
        (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(isMember: false, active: false),
        isPaid: true,
        isOwner: false,
        now: now,
      )));
      await tester.pump();

      expect(find.text('Not a member'), findsOneWidget);
      expect(find.text('You are the organizer'), findsNothing);
    });

    testWidgets('RED: the raw ISO expiresAt is never printed', (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(
            isMember: true, active: true, expiresAt: activeExpiry),
        isPaid: true,
        now: now,
      )));
      await tester.pump();

      // The raw string, and the old "Expires: <iso>" line, must be absent.
      expect(find.text(activeExpiry), findsNothing);
      expect(find.text('Expires: $activeExpiry'), findsNothing);
      expect(find.textContaining('422467'), findsNothing);
      expect(find.textContaining('T18:16:15'), findsNothing);
    });

    testWidgets('free community (not paid) active member: no adds-days note',
        (tester) async {
      await tester.pumpWidget(_wrap(CommunityMyStatus(
        myStatus: const MyStatus(isMember: true, active: true),
        isPaid: false,
        now: now,
      )));
      await tester.pump();
      // No expiry (null) and no renewal note for a free community.
      expect(find.byKey(const Key('my_status_expiry')), findsNothing);
      expect(find.byKey(const Key('adds_days_note')), findsNothing);
    });
  });

  group('JoinedCommunitySubtitle (My communities row)', () {
    testWidgets('active row shows member count then grey expiry',
        (tester) async {
      await tester.pumpWidget(_wrap(JoinedCommunitySubtitle(
        community: const JoinedCommunity(
          id: 7,
          name: 'Harbourside Walks',
          organiserName: 'Jo',
          active: true,
          expiresAt: activeExpiry,
          memberCount: 12,
        ),
        now: now,
      )));
      await tester.pump();

      expect(find.textContaining('Active member'), findsOneWidget);
      final expiry =
          tester.widget<Text>(find.byKey(const Key('my_communities_expiry_7')));
      expect(expiry.data, startsWith('Member until '));
      expect((expiry.style?.color), Colors.grey);
      // Raw ISO not shown.
      expect(find.textContaining('422467'), findsNothing);
    });

    testWidgets('expired row shows expiry in the error colour', (tester) async {
      await tester.pumpWidget(_wrap(Builder(builder: (context) {
        return JoinedCommunitySubtitle(
          community: const JoinedCommunity(
            id: 9,
            name: 'Old Town Tales',
            active: false,
            expiresAt: '2026-09-01T10:00:00Z',
            memberCount: 3,
          ),
          now: now,
        );
      })));
      await tester.pump();

      final expiry =
          tester.widget<Text>(find.byKey(const Key('my_communities_expiry_9')));
      expect(expiry.data, startsWith('Expired on '));
      // The error colour is the ColorScheme default (red-ish), not grey.
      expect(expiry.style?.color, isNot(Colors.grey));
    });
  });
}
