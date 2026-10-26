// [LOCAL-774] Live screenshot run on the Android emulator. Drives the REAL
// TourGeneratorScreen through submit -> poll -> error with a MockClient serving
// the L2 by_reference refusal (error_code=by_reference_no_material, a string
// suggestion, two nearby_tours), and photographs the new Free-level refusal
// dialog:
//   01_by_reference_refusal_dialog — title "Not available on the Free level
//     yet", the clean server message (NOT the "Error in tour text generation:"
//     prefix), the suggestion line, the two tappable nearby tours, and the
//     "Buy a pack" button.
//
// Deterministic and $0: no live server, local server mode (no attestation).
//
// Usage:
//   flutter drive \
//     --driver=test_driver/local774_screenshot_driver.dart \
//     --target=integration_test/local774_refusal_dialog_screenshot_test.dart \
//     -d <booted-emulator-id>
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';

Map<String, dynamic> _refusalStatus() => {
      'status': 'error',
      'error': 'Error in tour text generation: '
          "This place hasn't been researched yet on the free level.",
      'error_code': 'by_reference_no_material',
      'message': "This place hasn't been researched yet on the free level.",
      'suggestion': 'Buy a \$10 pack for a freshly researched tour, or pick '
          'one of these nearby tours: West Roxbury Walk (#123); '
          'Roslindale Square (#124).',
      'nearby_tours': [
        {'id': 123, 'name': 'West Roxbury Walk'},
        {'id': 124, 'name': 'Roslindale Square'},
      ],
    };

MockClient _client() => MockClient((request) async {
      final path = request.url.path;
      final jsonHdr = {'content-type': 'application/json'};
      if (request.method == 'POST' && path.endsWith('/generate-complete-tour')) {
        return http.Response(jsonEncode({'job_id': 'job_1'}), 200,
            headers: jsonHdr);
      }
      if (request.method == 'GET' && path.contains('/status/')) {
        return http.Response(jsonEncode(_refusalStatus()), 200,
            headers: jsonHdr);
      }
      return http.Response(jsonEncode({'ok': true, 'rows_affected': 1}), 200,
          headers: jsonHdr);
    });

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
  }

  Future<void> shot(WidgetTester tester, String name) async {
    await settle(tester);
    await binding.convertFlutterSurfaceToImage();
    await settle(tester);
    await binding.takeScreenshot(name);
  }

  testWidgets('by_reference refusal dialog on the Free level', (tester) async {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local774_emulator',
      'narrative_tone': 'general',
    });

    await http.runWithClient(() async {
      await tester.binding.setSurfaceSize(const Size(1200, 2600));
      await tester.pumpWidget(const MaterialApp(home: TourGeneratorScreen()));
      await settle(tester);

      await tester.enterText(
          find.byType(TextField).first, 'Gyms near me, West Roxbury, MA');
      final numeric = find.byWidgetPredicate((w) =>
          w is TextField && w.keyboardType == TextInputType.number);
      await tester.enterText(numeric, '2');
      await settle(tester);

      final generate = find.text('🎯 Generate Now');
      await tester.ensureVisible(generate);
      await settle(tester);

      // Real async: the submit -> poll loop runs on wall-clock timers on the
      // device, so let it actually elapse before settling the frames.
      await tester.runAsync(() async {
        await tester.tap(generate);
        await Future<void>.delayed(const Duration(seconds: 3));
      });
      await settle(tester);
      await shot(tester, '01_by_reference_refusal_dialog');

      // The new Free-level refusal dialog is up.
      expect(find.text('Not available on the Free level yet'), findsOneWidget);
      expect(find.widgetWithText(ElevatedButton, 'Buy a pack'), findsOneWidget);
      expect(find.textContaining('Error in tour text generation:'),
          findsNothing);
    }, _client);
  });
}
