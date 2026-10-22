// [LOCAL-604 / LOCAL-735] Parsing tests for the server-driven visible-levels
// list, plus widget tests for the plan page's Upgrade + Apply cards.
//
// LOCAL-735 reorganised "Your plan": "Upgrade your plan" (the single code box)
// shows on every level, and "Apply for the Free plan" (the queue action and the
// Free generation allowance) shows ONLY on Introduction. The level table must
// render ONLY the visible levels the server sent, by display name, and never
// show the hidden Tester/Administrator levels. Curator's first bullet must be
// "Create tours for sale", and Pack/Curator must show the invitations line.
//
// PlanScreen.me() reads SharedPreferences for the device id; with the mock set
// to empty it returns Entitlements.unknown (level l1) without any network call,
// so the screen builds deterministically offline.

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

  group('PlanScreen Upgrade + Apply cards (LOCAL-735)', () {
    testWidgets(
        'Introduction shows the Upgrade card (code box) and the Apply card (queue)',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(home: PlanScreen()));
      await tester.pumpAndSettle();

      // "Upgrade your plan" — the single code box, on every level including l1.
      expect(find.text('Upgrade your plan'), findsOneWidget);
      expect(find.text('Use code'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);

      // "Apply for the Free plan" — only on Introduction (the default unknown
      // snapshot is l1): the queue action and the generation allowance.
      expect(find.text('Apply for the Free plan'), findsOneWidget);
      expect(find.text('Join the queue'), findsOneWidget);
      final allowance = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('generate your own tours') &&
          (w.data ?? '').contains('a queue'));
      expect(allowance, findsOneWidget);

      // The old framing is gone.
      expect(find.text('Get the Free plan'), findsNothing);
      expect(find.text('Have a code?'), findsNothing);
      expect(find.text('I have a code'), findsNothing);
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
