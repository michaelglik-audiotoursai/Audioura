// [LOCAL-699] Widget tests for the plan-page Buy buttons:
//
//   • the \$10 Pack and Curator Buy buttons are ALWAYS visible on BOTH iOS and
//     Android — never gated on platform or a billing flag (the Pixel-4 report
//     was buttons hidden on Android);
//   • the TEST PURCHASE banner shows ONLY in stub mode (a stub-verification
//     server) and is absent on a real-verification server, driven by the
//     server-reported mode (here via the initialStubMode test seam);
//   • the buy buttons stay visible in both modes.
//
// PlanScreen takes two test seams (both null in production): initialEntitlements
// renders a snapshot with no user-api, and initialStubMode fixes the purchase
// mode so no GET /purchases/mode call is made.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

/// A minimal entitlements snapshot at [level] with the four visible levels, so
/// the buy card and level table render without a running user-api.
Entitlements _ent(String level) {
  return Entitlements.fromJson({
    'level': level,
    'display_name': {
      'l1': 'Introduction',
      'l2': 'Free',
      'l3': '\$10 Pack',
      'l4': 'Curator',
    }[level] ?? level,
    'levels': [
      {'plan_id': 'l1', 'display_name': 'Introduction', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 0, 'inactivity_days': null},
      {'plan_id': 'l2', 'display_name': 'Free', 'price_usd': 0, 'can_sell': false, 'referrals_allowed': 0, 'referral_period': null, 'max_stops': 5, 'inactivity_days': 7},
      {'plan_id': 'l3', 'display_name': '\$10 Pack', 'price_usd': 10, 'can_sell': false, 'referrals_allowed': 3, 'referral_period': 'lifetime', 'max_stops': 10, 'inactivity_days': null},
      {'plan_id': 'l4', 'display_name': 'Curator', 'price_usd': 25, 'can_sell': true, 'referrals_allowed': 5, 'referral_period': 'month', 'max_stops': 25, 'inactivity_days': null},
    ],
    'allowances_left': {},
  });
}

Future<void> _pump(WidgetTester tester,
    {required bool stub, String level = 'l2', TargetPlatform? platform}) async {
  await tester.pumpWidget(MaterialApp(
    theme: platform == null ? null : ThemeData(platform: platform),
    home: PlanScreen(initialEntitlements: _ent(level), initialStubMode: stub),
  ));
  await tester.pumpAndSettle();
}

final Finder _packButton =
    find.text('\$10 Pack — 5 new tours + 5 edits, up to 10 stops');
final Finder _curatorButton = find.text(
    'Curator (\$25) — 25 tours or edits, up to 25 stops, sell your tours');
const String _bannerStart = 'TEST PURCHASE — no real charge.';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('buy buttons always visible on BOTH platforms', () {
    for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
      testWidgets('both pack buttons show on $platform (real-verification server)',
          (tester) async {
        await _pump(tester, stub: false, platform: platform);
        expect(_packButton, findsOneWidget,
            reason: '\$10 Pack button must be visible on $platform');
        expect(_curatorButton, findsOneWidget,
            reason: 'Curator button must be visible on $platform');
        // No old "coming to Android soon" copy anywhere.
        expect(
            find.byWidgetPredicate((w) =>
                w is Text && (w.data ?? '').contains('coming to Android')),
            findsNothing);
      });

      testWidgets('both pack buttons show on $platform (stub server)',
          (tester) async {
        await _pump(tester, stub: true, platform: platform);
        expect(_packButton, findsOneWidget);
        expect(_curatorButton, findsOneWidget);
      });
    }
  });

  group('TEST PURCHASE banner follows the server mode', () {
    testWidgets('stub server shows the TEST PURCHASE banner', (tester) async {
      await _pump(tester, stub: true);
      final banner = find.byWidgetPredicate(
          (w) => w is Text && (w.data ?? '').startsWith(_bannerStart));
      expect(banner, findsOneWidget);
      // Buttons still present alongside the banner.
      expect(_packButton, findsOneWidget);
      expect(_curatorButton, findsOneWidget);
    });

    testWidgets('real-verification server shows NO TEST PURCHASE banner',
        (tester) async {
      await _pump(tester, stub: false);
      final banner = find.byWidgetPredicate(
          (w) => w is Text && (w.data ?? '').startsWith(_bannerStart));
      expect(banner, findsNothing);
      // Buttons still present without the banner.
      expect(_packButton, findsOneWidget);
      expect(_curatorButton, findsOneWidget);
    });
  });
}
