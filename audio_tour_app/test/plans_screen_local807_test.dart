// [LOCAL-807 / D734] Widget tests for the one-page Plans screen reveal flow:
//
//   • the two big choices (Pass, Tour pack) render, and neither option panel is
//     shown until a choice is tapped;
//   • tapping "Pass" reveals the segmented Day/Week/Month/Year control, the
//     "N new tours" line, a price, and ONE Buy button;
//   • the auto-renewal terms show for Week/Month/Year but NOT for the Day pass;
//   • tapping "Tour pack" reveals the one-time 5-tour pack (no renewal terms);
//   • the active-plan banner renders for a subscription level;
//   • Restore + Manage links are present;
//   • the Buy button drives buySubscription for the SELECTED option (via the
//     buyOverride test seam — no store).
//
// PlansScreen is fully test-seamed: initialEntitlements (no user-api),
// buyOverride (no store) and priceOverride (deterministic price).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plans_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';
import 'package:audio_tour_app_dev/services/iap_service.dart';

Entitlements _ent(String level, {String? displayName, String? anniversary,
    Map<String, dynamic>? allowances}) {
  return Entitlements.fromJson({
    'level': level,
    'display_name': displayName ?? level,
    'levels': const [],
    'anniversary_at': anniversary,
    'allowances_left': allowances ?? const {},
  });
}

Future<void> _pump(WidgetTester tester, {
  required Entitlements ent,
  Future<IapResult> Function(IapSubscription)? buyOverride,
  String? Function(String)? priceOverride,
}) async {
  await tester.pumpWidget(MaterialApp(
    home: PlansScreen(
      initialEntitlements: ent,
      initialStubMode: false,
      buyOverride: buyOverride,
      priceOverride: priceOverride ??
          (id) => {
                'audioura.sub.day': '\$2.99',
                'audioura.sub.weekly': '\$4.99',
                'audioura.sub.monthly': '\$9.99',
                'audioura.sub.annual': '\$79.99',
              }[id],
    ),
  ));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('two choices render; no option panel until a choice is tapped',
      (tester) async {
    await _pump(tester, ent: _ent('l1'));
    expect(find.byKey(const Key('choice_pass')), findsOneWidget);
    expect(find.byKey(const Key('choice_pack')), findsOneWidget);
    // Nothing revealed yet.
    expect(find.byKey(const Key('pass_options')), findsNothing);
    expect(find.byKey(const Key('pack_option')), findsNothing);
    // The Buy button only appears once a choice is revealed.
    expect(find.byKey(const Key('plans_buy_button')), findsNothing);
  });

  testWidgets('tapping Pass reveals the segmented control, tours line, price, Buy',
      (tester) async {
    await _pump(tester, ent: _ent('l1'));
    await tester.tap(find.byKey(const Key('choice_pass')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pass_options')), findsOneWidget);
    expect(find.byKey(const Key('pass_tours_line')), findsOneWidget);
    expect(find.byKey(const Key('pass_price')), findsOneWidget);
    expect(find.byKey(const Key('plans_buy_button')), findsOneWidget);
    // Default option is Month -> 10 new tours a month, $9.99.
    expect(find.text('10 new tours a month'), findsOneWidget);
    expect(find.text('\$9.99'), findsWidgets);
  });

  testWidgets('auto-renew terms show for Month but NOT for the Day pass',
      (tester) async {
    await _pump(tester, ent: _ent('l1'));
    await tester.tap(find.byKey(const Key('choice_pass')));
    await tester.pumpAndSettle();

    // Default (Month) is auto-renewing -> renewal terms present, day terms absent.
    expect(find.byKey(const Key('renewal_terms')), findsOneWidget);
    expect(find.byKey(const Key('day_pass_terms')), findsNothing);

    // Switch to Day -> renewal terms gone, day terms shown.
    await tester.tap(find.text('Day'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('renewal_terms')), findsNothing);
    expect(find.byKey(const Key('day_pass_terms')), findsOneWidget);
    expect(find.text('3 new tours'), findsOneWidget);
  });

  testWidgets('auto-renew terms also show for Week and Year', (tester) async {
    await _pump(tester, ent: _ent('l1'));
    await tester.tap(find.byKey(const Key('choice_pass')));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Week'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('renewal_terms')), findsOneWidget);
    expect(find.text('5 new tours a week'), findsOneWidget);

    await tester.tap(find.text('Year'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('renewal_terms')), findsOneWidget);
    expect(find.text('\$79.99'), findsWidgets);
  });

  testWidgets('tapping Tour pack reveals the one-time pack with no renewal terms',
      (tester) async {
    await _pump(tester, ent: _ent('l1'));
    await tester.tap(find.byKey(const Key('choice_pack')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pack_option')), findsOneWidget);
    expect(find.byKey(const Key('pack_terms')), findsOneWidget);
    expect(find.byKey(const Key('plans_buy_pack_button')), findsOneWidget);
    // No auto-renewal terms anywhere for the pack.
    expect(find.byKey(const Key('renewal_terms')), findsNothing);
  });

  testWidgets('active subscription banner renders with renews + tours left',
      (tester) async {
    await _pump(
      tester,
      ent: _ent('sub_week',
          displayName: 'Weekly',
          anniversary: '2026-11-05T00:00:00Z',
          allowances: {'tours_this_month_left': 3}),
    );
    expect(find.byKey(const Key('plans_active_banner')), findsOneWidget);
    final text = tester
        .widget<Text>(find.byKey(const Key('plans_active_banner_text')))
        .data!;
    expect(text, contains('Weekly'));
    expect(text, contains('3 new tours left'));
  });

  testWidgets('no active subscription shows the gentle prompt, not the banner',
      (tester) async {
    await _pump(tester, ent: _ent('l2', displayName: 'Free'));
    expect(find.byKey(const Key('plans_no_active_sub')), findsOneWidget);
    expect(find.byKey(const Key('plans_active_banner')), findsNothing);
  });

  testWidgets('Restore + Manage links are present', (tester) async {
    await _pump(tester, ent: _ent('l1'));
    expect(find.byKey(const Key('plans_restore')), findsOneWidget);
    expect(find.byKey(const Key('plans_manage')), findsOneWidget);
  });

  testWidgets('Buy drives buySubscription for the SELECTED option', (tester) async {
    IapSubscription? bought;
    await _pump(
      tester,
      ent: _ent('l1'),
      buyOverride: (sub) async {
        bought = sub;
        return const IapResult(IapResultStatus.granted);
      },
    );
    await tester.tap(find.byKey(const Key('choice_pass')));
    await tester.pumpAndSettle();
    // Select Year, then Buy.
    await tester.tap(find.text('Year'));
    await tester.pumpAndSettle();
    final buyBtn = find.byKey(const Key('plans_buy_button'));
    await tester.ensureVisible(buyBtn);
    await tester.pumpAndSettle();
    await tester.tap(buyBtn);
    await tester.pumpAndSettle();
    expect(bought, IapSubscription.annual);
  });
}
