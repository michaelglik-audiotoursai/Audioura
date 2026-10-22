/// [LOCAL-735] Live screenshot run on the iOS simulator against the ISOLATED
/// local735 user-api (project -p local735, host port 5103 → container :5000).
///
/// Renders the REAL PlanScreen — the exact reordered markup this ticket ships
/// (current plan → Upgrade your plan → Apply for the Free plan on Introduction
/// only → Buy a pack → The plans) — on the booted simulator, driven by the LIVE
/// /entitlements/me payload fetched over HTTP from the local735 user-api. No
/// in-widget stubbing of the plan: the screen fetches from the server exactly
/// as it does in production (local server mode, forced by
/// --dart-define=DEBUG_SERVER_IP=127.0.0.1 so every service resolves to
/// 127.0.0.1:<local port>).
///
/// Two states are captured:
///   * Introduction (l1): shows the Upgrade card AND the Apply-for-the-Free-plan
///     card with the live generation allowance (l2 max_stops from the server);
///   * $10 Pack (l3): shows the Upgrade card and NO Apply card, plus the
///     LOCAL-733 "what's left" line (3 new tours and 2 edits) from live data.
///
/// Server writes by THIS test: 0. The l1 device is read-only; the l3 device's
/// state was seeded once out-of-band before the run (documented in the
/// submission). GET /entitlements/me is a pure read. Budget: $0 (no tour
/// generation, no paid API).
///
/// Usage:
///   flutter drive \
///     --driver=test_driver/local735_screenshot_driver.dart \
///     --target=integration_test/plan_screen_order_screenshot_test.dart \
///     -d <booted-simulator-id> \
///     --dart-define=DEBUG_SERVER_IP=127.0.0.1
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plan_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> dump(WidgetTester tester, String name) async {
    await tester.pumpAndSettle();
    await binding.convertFlutterSurfaceToImage();
    await tester.pumpAndSettle();
    await binding.takeScreenshot(name);
  }

  // Render the REAL PlanScreen for [userId]. With DEBUG_SERVER_IP baked in the
  // screen is in local mode, so PlanScreen() (no seam) fetches /entitlements/me
  // live from the local735 user-api for this user_id.
  Future<void> openPlan(WidgetTester tester, String userId) async {
    SharedPreferences.setMockInitialValues({'user_id': userId});
    await tester.pumpWidget(const MaterialApp(home: PlanScreen()));
    // Allow the live network fetch to complete and the ListView to lay out.
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 300));
    }
    await tester.pumpAndSettle();
  }

  testWidgets('Introduction (l1) — Upgrade + Apply for the Free plan', (tester) async {
    await openPlan(tester, 'LIVE735-intro');
    // Prove we are rendering the live l1 screen with the new structure.
    expect(find.text('Current plan: Introduction'), findsOneWidget);
    expect(find.text('Upgrade your plan'), findsOneWidget);
    expect(find.text('Apply for the Free plan'), findsOneWidget);
    await dump(tester, 'local735_introduction');
  });

  testWidgets('\$10 Pack (l3) — Upgrade, no Apply card, what-is-left line',
      (tester) async {
    await openPlan(tester, 'LIVE735-pack');
    expect(find.text('Current plan: \$10 Pack'), findsOneWidget);
    expect(find.text('Upgrade your plan'), findsOneWidget);
    // The Apply card is Introduction-only — it must be absent on the paid level.
    expect(find.text('Apply for the Free plan'), findsNothing);
    await dump(tester, 'local735_10_pack');
  });
}
