// [LOCAL-610] Widget tests for Michael's plan-page corrections (2026-10-07):
//
//   req 1  the Free/code card is LEVEL-AWARE:
//            • l1 (Introduction) shows "Get the Free plan" with BOTH the queue
//              action and the code box;
//            • l2 (Free) shows "Have a code?" with the code box ONLY — no
//              "Join the queue" and no "Get the Free plan";
//            • l3, l4 and admin show the small "Have a code?" code row — no
//              queue, no "Get the Free plan".
//   req 2  the buy buttons read "$10 Pack — …" and "Curator ($25) — …", and the
//            word "round" appears nowhere a user sees it.
//   req 3  the plain rules under the levels: the Free inactivity rule takes its
//            day count FROM THE API (plans.inactivity_days), and the pack rule
//            states the one-month / replace-on-early-buy behaviour, with the
//            anniversary date shown when the device holds a pack.
//
// PlanScreen takes an optional initialEntitlements test seam (null in
// production) so these states render with no running user-api.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

/// Build an Entitlements snapshot for [level] with the four visible levels the
/// server would send, including the Free level's inactivity_days so the rules
/// text can read it. [inactivityDays] sets the Free level's window;
/// [anniversary] sets a pack anniversary when non-null.
Entitlements _ent(
  String level, {
  int inactivityDays = 7,
  String? anniversary,
}) {
  return Entitlements.fromJson({
    'level': level,
    'display_name': {
      'l1': 'Introduction',
      'l2': 'Free',
      'l3': '\$10 Pack',
      'l4': 'Curator',
      'admin': 'Administrator',
    }[level] ?? level,
    'inactivity_days': level == 'l2' ? inactivityDays : null,
    'anniversary_at': anniversary,
    'levels': [
      {'plan_id': 'l1', 'display_name': 'Introduction', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 0, 'inactivity_days': null},
      {'plan_id': 'l2', 'display_name': 'Free', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 5, 'inactivity_days': inactivityDays},
      {'plan_id': 'l3', 'display_name': '\$10 Pack', 'price_usd': 10, 'can_sell': false, 'referrals_allowed': 3, 'referral_period': 'lifetime', 'max_stops': 10, 'inactivity_days': null},
      {'plan_id': 'l4', 'display_name': 'Curator', 'price_usd': 25, 'can_sell': true, 'referrals_allowed': 5, 'referral_period': 'month', 'max_stops': 25, 'inactivity_days': null},
    ],
    'allowances_left': {},
  });
}

Future<void> _pump(WidgetTester tester, Entitlements ent) async {
  await tester.pumpWidget(MaterialApp(home: PlanScreen(initialEntitlements: ent)));
  await tester.pumpAndSettle();
}

/// Scroll the plan ListView to its bottom so the lazily-built "The plans" card
/// (and the rules text under it) is laid out and findable.
Future<void> _scrollToRules(WidgetTester tester) async {
  await tester.drag(find.byType(Scrollable).first, const Offset(0, -1200));
  await tester.pumpAndSettle();
  await tester.drag(find.byType(Scrollable).first, const Offset(0, -1200));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('req 1 — level-aware Free/code card', () {
    testWidgets('l1 Introduction: "Get the Free plan" with queue AND code',
        (tester) async {
      await _pump(tester, _ent('l1'));
      expect(find.text('Get the Free plan'), findsOneWidget);
      expect(find.text('Join the queue'), findsOneWidget);
      // The code box is present on l1 too.
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);
      expect(find.text('Use code'), findsOneWidget);
      // No "Have a code?" title on l1.
      expect(find.text('Have a code?'), findsNothing);
    });

    testWidgets('l2 Free: "Have a code?", code box ONLY, no queue, no "Get the Free plan"',
        (tester) async {
      await _pump(tester, _ent('l2'));
      expect(find.text('Have a code?'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);
      expect(find.text('Use code'), findsOneWidget);
      // The things a Free user must NOT be invited to.
      expect(find.text('Get the Free plan'), findsNothing);
      expect(find.text('Join the queue'), findsNothing);
      expect(find.text('Update my queue email'), findsNothing);
    });

    testWidgets('l3 Pack: small "Have a code?" row, no queue / no "Get the Free plan"',
        (tester) async {
      await _pump(tester, _ent('l3'));
      expect(find.text('Have a code?'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);
      expect(find.text('Get the Free plan'), findsNothing);
      expect(find.text('Join the queue'), findsNothing);
    });

    testWidgets('l4 Curator: small "Have a code?" row, no queue / no "Get the Free plan"',
        (tester) async {
      await _pump(tester, _ent('l4'));
      expect(find.text('Have a code?'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);
      expect(find.text('Get the Free plan'), findsNothing);
      expect(find.text('Join the queue'), findsNothing);
    });

    testWidgets('admin: small "Have a code?" row, no queue / no "Get the Free plan"',
        (tester) async {
      await _pump(tester, _ent('admin'));
      expect(find.text('Have a code?'), findsOneWidget);
      expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget);
      expect(find.text('Get the Free plan'), findsNothing);
      expect(find.text('Join the queue'), findsNothing);
    });

    testWidgets('the code box is reachable from EVERY level',
        (tester) async {
      for (final lvl in ['l1', 'l2', 'l3', 'l4', 'admin']) {
        await _pump(tester, _ent(lvl));
        expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget,
            reason: 'code box must be present at level $lvl');
        expect(find.text('Use code'), findsOneWidget,
            reason: 'Use code button must be present at level $lvl');
      }
    });
  });

  group('req 2 — buy button labels, no user-facing "round"', () {
    testWidgets('shows the "\$10 Pack" and "Curator (\$25)" labels', (tester) async {
      await _pump(tester, _ent('l1'));
      expect(
          find.text('\$10 Pack — 5 new tours + 5 edits, up to 10 stops'),
          findsOneWidget);
      expect(
          find.text('Curator (\$25) — 25 tours or edits, up to 25 stops, sell your tours'),
          findsOneWidget);
    });

    testWidgets('no visible Text widget contains the word "round"', (tester) async {
      await _pump(tester, _ent('l1'));
      final roundText = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').toLowerCase().contains('round'));
      expect(roundText, findsNothing);
    });
  });

  group('req 3 — plain rules under the levels', () {
    testWidgets('Free inactivity rule uses the day count from the API', (tester) async {
      // Server sends inactivity_days = 9 on the Free level; the copy must read
      // "After 9 days", never a hardcoded 7.
      await _pump(tester, _ent('l1', inactivityDays: 9));
      await _scrollToRules(tester);
      final rule = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('After 9 days without a visit') &&
          (w.data ?? '').contains('returns to Introduction'));
      expect(rule, findsOneWidget);
      // The default 7 must NOT appear when the API said 9.
      final seven = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').contains('After 7 days'));
      expect(seven, findsNothing);
    });

    testWidgets('pack/Curator one-month rule is shown in plain words', (tester) async {
      await _pump(tester, _ent('l2'));
      await _scrollToRules(tester);
      final rule = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('good for one month') &&
          (w.data ?? '').contains('Buying early') &&
          (w.data ?? '').contains('Nothing renews'));
      expect(rule, findsOneWidget);
    });

    testWidgets('anniversary date is shown when the device holds a pack',
        (tester) async {
      await _pump(tester, _ent('l3', anniversary: '2026-11-07T00:00:00'));
      await _scrollToRules(tester);
      final ann = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').contains('Your current month ends on'));
      expect(ann, findsOneWidget);
    });

    testWidgets('no anniversary line when the device has no pack', (tester) async {
      await _pump(tester, _ent('l1'));
      await _scrollToRules(tester);
      final ann = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').contains('Your current month ends on'));
      expect(ann, findsNothing);
    });
  });
}
