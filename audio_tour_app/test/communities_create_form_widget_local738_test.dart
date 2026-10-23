// [LOCAL-738] Widget tests for the Create-community form (Michael's review
// C2/C2b/C2c). These drive the REAL CreateCommunityScreen with a MockClient so
// the plan gate opens (l2) and the server answers pass-prices, name-available
// and a FAILING create with a specific message.
//
// Covered:
//   * the form (not the plan gate) renders when the device is on a plan;
//   * the server pass prices fill the price chips ($1/$5/$10/$20);
//   * the release-cadence default "Weekly" is shown;
//   * a failing create shows the server's exact message in a SnackBar (the real
//     error, never the old generic guess).
//
// Note: the form runs a debounced live name-check Timer, so we use bounded
// pumps rather than pumpAndSettle (which would never quiesce).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/communities_about_screen.dart';

MockClient _client() => MockClient((req) async {
      final path = req.url.path;
      final json = {'content-type': 'application/json'};
      if (path.endsWith('/entitlements/me')) {
        return http.Response('{"level":"l2","levels":[]}', 200, headers: json);
      }
      if (path.endsWith('/communities/pass-prices')) {
        return http.Response(
            '{"prices":[{"product_id":"audioura.pass.usd1","price_usd":1,"label":"\$1"},'
            '{"product_id":"audioura.pass.usd5","price_usd":5,"label":"\$5"},'
            '{"product_id":"audioura.pass.usd10","price_usd":10,"label":"\$10"},'
            '{"product_id":"audioura.pass.usd20","price_usd":20,"label":"\$20"}]}',
            200,
            headers: json);
      }
      if (path.endsWith('/communities/name-available')) {
        return http.Response('{"name":"x","available":true}', 200,
            headers: json);
      }
      if (path.endsWith('/communities') && req.method == 'POST') {
        return http.Response(
            '{"error":"name_taken","message":"That community name is taken."}',
            409,
            headers: json);
      }
      return http.Response('{}', 200, headers: json);
    });

/// Pump a fixed number of frames with short delays so the plan gate resolves,
/// prices load, and the prefill name-check settles — WITHOUT pumpAndSettle
/// (the debounced name Timer never lets the tree quiesce).
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'cloud',
      'user_id': 'local738-widget-user',
    });
  });

  testWidgets('form renders on a plan, with server price chips + cadence',
      (tester) async {
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: CreateCommunityScreen()));
      await _settle(tester);

      // No "Custom price" field any more (C2b) — visible near the top.
      expect(find.textContaining('Custom price'), findsNothing);

      // Scroll to the month price chips (server prices) and the cadence choice.
      await tester.scrollUntilVisible(
        find.widgetWithText(ChoiceChip, '\$20'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.widgetWithText(ChoiceChip, '\$5'), findsWidgets);
      expect(find.widgetWithText(ChoiceChip, '\$20'), findsWidgets);

      await tester.scrollUntilVisible(
        find.widgetWithText(ChoiceChip, 'Weekly'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.widgetWithText(ChoiceChip, 'Weekly'), findsOneWidget);

      // The submit button lives at the bottom of a lazy ListView — scroll it in.
      await tester.scrollUntilVisible(
        find.widgetWithText(ElevatedButton, 'Create community'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.widgetWithText(ElevatedButton, 'Create community'),
          findsOneWidget);
    }, _client);
  });

  testWidgets('a failing create shows the server message, not a guess',
      (tester) async {
    await http.runWithClient(() async {
      await tester.pumpWidget(const MaterialApp(home: CreateCommunityScreen()));
      await _settle(tester);

      // Accept the Organiser Terms to enable Create — every other required
      // field is prefilled. Scroll the terms row into view, then toggle the
      // checkbox by tapping the 'I accept the' label (NOT the 'Organiser Terms'
      // link, which opens the document).
      await tester.scrollUntilVisible(
        find.text('Organiser Terms'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.textContaining('I accept the'));
      await _settle(tester);

      await tester.scrollUntilVisible(
        find.widgetWithText(ElevatedButton, 'Create community'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.widgetWithText(ElevatedButton, 'Create community'));
      await _settle(tester);

      // The SnackBar carries the SERVER's exact message, not the old generic
      // "the name may be taken, or you may need a plan".
      expect(find.text('That community name is taken.'), findsOneWidget);
      expect(find.textContaining('may need a plan'), findsNothing);
    }, _client);
  });
}
