// [LOCAL-610 / LOCAL-735] Widget tests for the plan page's structure.
//
// LOCAL-735 (Michael, 2026-10-22) reorganised "Your plan". Top to bottom:
//   1. the current-plan card (unchanged, incl. the LOCAL-733 "what's left" line);
//   2. "Upgrade your plan" — shown on EVERY level: a short line + the single
//      code box (the old "Get the Free plan" / "Have a code?" framing is gone);
//   3. "Apply for the Free plan" — shown ONLY on Introduction (l1): the Free
//      generation allowance (from the plan data, not hard-coded) + the queue
//      action. Hidden on Free, paid, tester and admin;
//   4. "Buy a pack", then "The plans" — unchanged.
//
// Also kept from LOCAL-610:
//   req 2  the buy buttons read "$10 Pack — …" and "Curator ($25) — …", and the
//            word "round" appears nowhere a user sees it.
//   req 3  the plain rules under the levels: the Free inactivity rule takes its
//            day count FROM THE API (plans.inactivity_days), and the pack rule
//            states the one-month / carry-over behaviour, with the anniversary
//            date shown when the device holds a pack.
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
/// [anniversary] sets a pack anniversary when non-null; [freeMaxStops] sets the
/// Free (l2) level's max_stops so the allowance copy can read it.
Entitlements _ent(
  String level, {
  int inactivityDays = 7,
  String? anniversary,
  int freeMaxStops = 5,
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
      {'plan_id': 'l2', 'display_name': 'Free', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': freeMaxStops, 'inactivity_days': inactivityDays},
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

/// The vertical position of a widget's centre, used to assert section order.
double _dy(WidgetTester tester, Finder f) => tester.getCenter(f).dy;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('LOCAL-735 — "Upgrade your plan" card on EVERY level', () {
    for (final lvl in ['l1', 'l2', 'l3', 'l4', 'admin']) {
      testWidgets('level $lvl shows "Upgrade your plan" with the code box',
          (tester) async {
        await _pump(tester, _ent(lvl));
        expect(find.text('Upgrade your plan'), findsOneWidget,
            reason: 'Upgrade card must be present at level $lvl');
        expect(find.widgetWithText(TextField, 'Enter your code'), findsOneWidget,
            reason: 'code box must be present at level $lvl');
        expect(find.text('Use code'), findsOneWidget,
            reason: 'Use code button must be present at level $lvl');
        // The old framing is gone everywhere.
        expect(find.text('Get the Free plan'), findsNothing);
        expect(find.text('Have a code?'), findsNothing);
      });
    }

    testWidgets('the upgrade line explains the three code kinds', (tester) async {
      await _pump(tester, _ent('l3'));
      final line = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('a friend') &&
          (w.data ?? '').contains('Free-plan queue') &&
          (w.data ?? '').contains('switch your plan'));
      expect(line, findsOneWidget);
    });
  });

  group('LOCAL-735 — "Apply for the Free plan" card ONLY on Introduction', () {
    testWidgets('l1 Introduction shows the Apply card with the queue action',
        (tester) async {
      await _pump(tester, _ent('l1'));
      expect(find.text('Apply for the Free plan'), findsOneWidget);
      expect(find.text('Join the queue'), findsOneWidget);
    });

    testWidgets('the Apply card states the Free generation allowance from the data',
        (tester) async {
      // Server sends Free max_stops = 6; the copy must read "up to 6 stops"
      // and "1 new tour a day, 3 a month", not a hard-coded number.
      await _pump(tester, _ent('l1', freeMaxStops: 6));
      final text = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('generate your own tours') &&
          (w.data ?? '').contains('1 new tour a day, 3 a month') &&
          (w.data ?? '').contains('up to 6 stops'));
      expect(text, findsOneWidget);
    });

    for (final lvl in ['l2', 'l3', 'l4', 'admin']) {
      testWidgets('level $lvl does NOT show "Apply for the Free plan"',
          (tester) async {
        await _pump(tester, _ent(lvl));
        expect(find.text('Apply for the Free plan'), findsNothing,
            reason: 'Apply card must be hidden at level $lvl');
        // The queue action lives only on the Apply card, so it is gone too.
        expect(find.text('Join the queue'), findsNothing);
        expect(find.text('Update my queue email'), findsNothing);
      });
    }

    // RED test: if the Apply card were ever shown on a paid level, this fails.
    // It pins the l1-only rule — on the $10 Pack there must be no Apply card.
    testWidgets('RED: Apply card must not appear on a paid level (l3)',
        (tester) async {
      await _pump(tester, _ent('l3'));
      expect(find.text('Apply for the Free plan'), findsNothing,
          reason:
              'showing "Apply for the Free plan" on a paid level is the bug this guards');
    });
  });

  group('LOCAL-735 — section order on Introduction', () {
    testWidgets('current → Upgrade → Apply, then Buy a pack below',
        (tester) async {
      await _pump(tester, _ent('l1'));
      // The three cards at the top of the list are all laid out in the first
      // viewport — assert their vertical order directly.
      final current = _dy(tester, find.textContaining('Current plan:'));
      final upgrade = _dy(tester, find.text('Upgrade your plan'));
      final apply = _dy(tester, find.text('Apply for the Free plan'));
      expect(current < upgrade, isTrue,
          reason: 'current plan card is above the Upgrade card');
      expect(upgrade < apply, isTrue,
          reason: 'Upgrade card is above the Apply card');
      // "Buy a pack" is further down the (lazy) list; scroll to bring it into
      // view and confirm it exists below the Apply card.
      expect(find.text('Buy a pack'), findsNothing,
          reason: 'Buy a pack sits below the fold on Introduction');
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -600));
      await tester.pumpAndSettle();
      expect(find.text('Buy a pack'), findsOneWidget);
    });

    testWidgets('on a paid level the order is current → Upgrade → Buy a pack',
        (tester) async {
      await _pump(tester, _ent('l3'));
      final current = _dy(tester, find.textContaining('Current plan:'));
      final upgrade = _dy(tester, find.text('Upgrade your plan'));
      final buy = _dy(tester, find.text('Buy a pack'));
      expect(current < upgrade, isTrue);
      expect(upgrade < buy, isTrue);
      expect(find.text('Apply for the Free plan'), findsNothing);
    });
  });

  group('req 2 — buy button labels, no user-facing "round"', () {
    testWidgets('shows the "\$10 Pack" and "Curator (\$25)" labels', (tester) async {
      // l2 has no Apply card, so the Buy buttons sit within the first viewport.
      await _pump(tester, _ent('l2'));
      expect(
          find.text('\$10 Pack — 5 new tours + 5 edits, up to 10 stops'),
          findsOneWidget);
      expect(
          find.text('Curator (\$25) — 25 tours or edits, up to 25 stops, sell your tours'),
          findsOneWidget);
    });

    testWidgets('no visible Text widget contains the word "round"', (tester) async {
      await _pump(tester, _ent('l2'));
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
      // [LOCAL-733 / D703] The rule now states that buying another pack ADDS to
      // what is left (carry-over), not that it replaces it.
      final rule = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '').contains('good for one month') &&
          (w.data ?? '').contains('Buying another pack adds it to what') &&
          (w.data ?? '').contains('Nothing renews'));
      expect(rule, findsOneWidget);
      // The OLD "Buying early … replaces what's left" wording must be gone.
      final old = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').contains('Buying early'));
      expect(old, findsNothing);
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
