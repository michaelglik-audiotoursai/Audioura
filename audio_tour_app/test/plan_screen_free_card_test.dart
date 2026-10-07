// [LOCAL-604 D619] Widget + parsing tests for the plan page's Free card and the
// server-driven visible-levels list.
//
// The Free card must offer "Join the queue" and a single "I have a code" box,
// with the explanation text from Michael's request 2 (code by email, valid 10
// minutes, or a friend's invitation). The level table must render ONLY the
// visible levels the server sent, by display name, and never show the hidden
// Tester/Administrator levels. Curator's first bullet must be "Create tours for
// sale", and Pack/Curator must show the invitations line.
//
// PlanScreen.me() reads SharedPreferences for the device id; with the mock set
// to empty it returns Entitlements.unknown without any network call, so the
// screen builds deterministically offline.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // Empty prefs -> no user_id -> EntitlementsService.me() returns unknown
    // immediately (no network), so the screen loads offline.
    SharedPreferences.setMockInitialValues({});
  });

  group('Entitlements.fromJson — LOCAL-604 display name + visible levels', () {
    test('parses display_name and the visible levels list in order', () {
      final e = Entitlements.fromJson({
        'level': 'l1',
        'display_name': 'Introduction',
        'levels': [
          {'plan_id': 'l1', 'display_name': 'Introduction', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 0},
          {'plan_id': 'l2', 'display_name': 'Free', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 5},
          {'plan_id': 'l3', 'display_name': '\$10 Pack', 'price_usd': 10, 'can_sell': false, 'referrals_allowed': 3, 'referral_period': 'lifetime', 'max_stops': 10},
          {'plan_id': 'l4', 'display_name': 'Curator', 'price_usd': 25, 'can_sell': true, 'referrals_allowed': 5, 'referral_period': 'month', 'max_stops': 25},
        ],
        'allowances_left': {},
      });
      expect(e.displayName, 'Introduction');
      expect(e.levels.map((l) => l.displayName).toList(),
          ['Introduction', 'Free', '\$10 Pack', 'Curator']);
      // Hidden levels are never sent, so they are never present.
      expect(e.levels.any((l) => l.planId == 'tester'), isFalse);
      expect(e.levels.any((l) => l.planId == 'admin'), isFalse);
      // Curator is the only can_sell level and carries referral allowance.
      final curator = e.levels.firstWhere((l) => l.planId == 'l4');
      expect(curator.canSell, isTrue);
      expect(curator.referralsAllowed, 5);
    });

    test('older payload without levels -> empty list, safe display name', () {
      final e = Entitlements.fromJson({'level': 'l3', 'allowances_left': {}});
      expect(e.levels, isEmpty);
      expect(e.displayName, 'l3'); // falls back to the level id
    });

    test('malformed levels entries are skipped, never throw', () {
      final e = Entitlements.fromJson({
        'level': 'l1',
        'levels': ['nope', 42, {'display_name': 'no id'}],
        'allowances_left': {},
      });
      expect(e.levels, isEmpty); // the entry with no plan_id is dropped
    });

    test('pending_offer code and queue_position parse', () {
      final e = Entitlements.fromJson({
        'level': 'l1',
        'queue_position': 7,
        'pending_offer': {'code': 'L2OF-ABC123', 'expires_at': null},
        'allowances_left': {},
      });
      expect(e.queuePosition, 7);
      expect(e.pendingOfferCode, 'L2OF-ABC123');
    });
  });

  group('PlanScreen Free card', () {
    testWidgets('shows Join the queue, a single code box, and the explanation',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PlanScreen()));
      await tester.pumpAndSettle();

      // The Free card title and its two actions.
      expect(find.text('Get the Free plan'), findsOneWidget);
      expect(find.text('Join the queue'), findsOneWidget);
      expect(find.text('I have a code'), findsOneWidget);
      expect(find.text('Use code'), findsOneWidget);

      // Exactly one code text box on the card.
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);

      // The explanation text (request 2): email + 10 minutes + friend's invite.
      final explanation = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('by email') &&
          (w.data ?? '').contains('10 minutes') &&
          (w.data ?? '').contains('invitation from a friend'));
      expect(explanation, findsOneWidget);
    });

    testWidgets('empty code shows a prompt, does not crash', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PlanScreen()));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use code'));
      await tester.pump();
      expect(find.text('Enter a code first.'), findsOneWidget);
    });
  });
}
