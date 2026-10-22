// [LOCAL-733 / D703] Widget tests for "show members what is left" now that a
// new pack ADDS to the old one (same level) or converts 1:1 (different level).
//
// Covers:
//   • the current-plan card headline line, for $10 Pack, Free and Introduction
//     (Introduction shows none);
//   • the new rules sentence ("Buying another pack adds it to what's left …");
//   • the short grey line on the Generate screen (paid pack, Free, and hidden
//     on Introduction).
//
// Both screens take an optional initialEntitlements test seam (null in
// production) so these states render with no running user-api.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';
import 'package:audio_tour_app_dev/services/pass_expiry_format.dart';

/// An Entitlements snapshot for [level] with the given allowances-left and an
/// optional pack anniversary. The four visible levels are included so the plan
/// screen renders in full.
Entitlements _ent(
  String level, {
  Map<String, dynamic> allowances = const {},
  String? anniversary,
}) {
  return Entitlements.fromJson({
    'level': level,
    'display_name': {
      'l1': 'Introduction',
      'l2': 'Free',
      'l3': '\$10 Pack',
      'l4': 'Curator',
    }[level] ?? level,
    'anniversary_at': anniversary,
    'allowances_left': allowances,
    'levels': [
      {'plan_id': 'l1', 'display_name': 'Introduction', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 0, 'inactivity_days': null},
      {'plan_id': 'l2', 'display_name': 'Free', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 5, 'inactivity_days': 7},
      {'plan_id': 'l3', 'display_name': '\$10 Pack', 'price_usd': 10, 'can_sell': false, 'referrals_allowed': 3, 'referral_period': 'lifetime', 'max_stops': 10, 'inactivity_days': null},
      {'plan_id': 'l4', 'display_name': 'Curator', 'price_usd': 25, 'can_sell': true, 'referrals_allowed': 5, 'referral_period': 'month', 'max_stops': 25, 'inactivity_days': null},
    ],
  });
}

String? _lineText(WidgetTester tester, Key key) {
  final finder = find.byKey(key);
  if (finder.evaluate().isEmpty) return null;
  return (tester.widget<Text>(finder)).data;
}

// The screen formats the anniversary in LOCAL time via PassExpiryFormat, so the
// expected date is computed the same way to stay timezone-independent in CI.
const String _annIso = '2026-11-22T00:00:00';
final String _annDate =
    PassExpiryFormat.formatDate(PassExpiryFormat.parse(_annIso)!);

Future<void> _pumpPlan(WidgetTester tester, Entitlements ent) async {
  await tester.pumpWidget(
      MaterialApp(home: PlanScreen(initialEntitlements: ent, initialStubMode: true)));
  await tester.pumpAndSettle();
}

Future<void> _pumpGenerate(WidgetTester tester, Entitlements ent) async {
  await tester.pumpWidget(
      MaterialApp(home: TourGeneratorScreen(initialEntitlements: ent)));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('plan card — what is left + end date', () {
    testWidgets('\$10 Pack shows "N new tours and M stop-adding edits left · until <date>"',
        (tester) async {
      await _pumpPlan(
        tester,
        _ent('l3',
            allowances: {'fresh_left': 8, 'edits_left': 6},
            anniversary: _annIso),
      );
      final line = _lineText(tester, const Key('plan_left_line'));
      expect(line, isNotNull);
      expect(
        line,
        '\$10 Pack · 8 new tours and 6 stop-adding edits left · until $_annDate',
      );
    });

    testWidgets('singular reads "1 new tour and 1 stop-adding edit"',
        (tester) async {
      await _pumpPlan(
        tester,
        _ent('l3',
            allowances: {'fresh_left': 1, 'edits_left': 1},
            anniversary: _annIso),
      );
      expect(_lineText(tester, const Key('plan_left_line')),
          '\$10 Pack · 1 new tour and 1 stop-adding edit left · until $_annDate');
    });

    testWidgets('Curator shows operations left', (tester) async {
      await _pumpPlan(
        tester,
        _ent('l4', allowances: {'ops_left': 29}, anniversary: _annIso),
      );
      expect(_lineText(tester, const Key('plan_left_line')),
          'Curator · 29 operations (new tours or edits) left · until $_annDate');
    });

    testWidgets('Free shows "N new tours left today"', (tester) async {
      await _pumpPlan(tester, _ent('l2', allowances: {'tours_today_left': 1}));
      expect(_lineText(tester, const Key('plan_left_line')),
          'Free · 1 new tour left today');
    });

    testWidgets('Introduction shows NO what-is-left line', (tester) async {
      await _pumpPlan(tester, _ent('l1'));
      expect(find.byKey(const Key('plan_left_line')), findsNothing);
    });
  });

  group('plan card — new rules sentence', () {
    testWidgets('states that another pack ADDS to what is left', (tester) async {
      await _pumpPlan(tester, _ent('l2'));
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -1400));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -1400));
      await tester.pumpAndSettle();
      final rule = find.byWidgetPredicate((w) =>
          w is Text &&
          (w.data ?? '')
              .contains('Buying another pack adds it to what\u2019s left and '
                  'starts a new month'));
      expect(rule, findsOneWidget);
      // The replaced sentence is gone.
      final old = find.byWidgetPredicate((w) =>
          w is Text && (w.data ?? '').contains('replaces what'));
      expect(old, findsNothing);
    });
  });

  group('generate screen — grey tours-left line', () {
    testWidgets('\$10 Pack shows "N new tours left in your pack"',
        (tester) async {
      await _pumpGenerate(tester, _ent('l3', allowances: {'fresh_left': 3}));
      expect(_lineText(tester, const Key('generate_tours_left_line')),
          '3 new tours left in your pack');
    });

    testWidgets('Free shows "1 new tour left today"', (tester) async {
      await _pumpGenerate(tester, _ent('l2', allowances: {'tours_today_left': 1}));
      expect(_lineText(tester, const Key('generate_tours_left_line')),
          '1 new tour left today');
    });

    testWidgets('Introduction shows NO generate line', (tester) async {
      await _pumpGenerate(tester, _ent('l1'));
      expect(find.byKey(const Key('generate_tours_left_line')), findsNothing);
    });
  });
}
