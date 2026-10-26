// [LOCAL-774] Widget test: a Free-level by_reference refusal must show the
// PLAN/PACK refusal dialog — not the generic red "Tour Generation Failed".
//
// Michael, TestFlight 2.4.32 (79), Subscribed cloud, 2026-10-26 16:07: a fresh
// Free install asked for "Gyms near me, West Roxbury, MA" and got a generic red
// "Tour Generation Failed — Error in tour text generation: This place hasn't
// been researched yet on the free level." dialog with only Dismiss / Try again.
// It is the LOCAL-597 by_reference refusal (error_code=by_reference_no_material,
// a string suggestion "Buy a $10 pack…", and up to 3 nearby_tours). The app must
// instead show the structured refusal dialog with a Buy a pack button and the
// tappable nearby tours, and NEVER the "Error in tour text generation:" prefix.
//
// Drives the REAL TourGeneratorScreen through submit -> poll -> error with http
// intercepted by MockClient (local server mode, no attestation / live server).

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local774_test',
      'narrative_tone': 'general',
    });
  });

  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 2600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const MaterialApp(home: TourGeneratorScreen()));
    await tester.pump();
  }

  late List<String> downloadsRequested;

  MockClient buildClient(Map<String, dynamic> statusBody) {
    downloadsRequested = [];
    var jobCount = 0;
    return MockClient((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path.endsWith('/generate-complete-tour')) {
        jobCount++;
        return http.Response(jsonEncode({'job_id': 'job_$jobCount'}), 200,
            headers: {'content-type': 'application/json'});
      }
      if (request.method == 'GET' && path.contains('/download/')) {
        downloadsRequested.add(path);
        // Return an (empty) 200 so the tap's download path is exercised without
        // needing a real ZIP; the assertion is only that the tap fired a
        // download for the tapped nearby tour id.
        return http.Response('', 200);
      }
      if (request.method == 'GET' && path.contains('/status/')) {
        return http.Response(jsonEncode(statusBody), 200,
            headers: {'content-type': 'application/json'});
      }
      return http.Response(jsonEncode({'ok': true, 'rows_affected': 1}), 200,
          headers: {'content-type': 'application/json'});
    });
  }

  Future<void> setStops(WidgetTester tester, String value) async {
    final numeric = find.byWidgetPredicate((w) =>
        w is TextField && w.keyboardType == TextInputType.number);
    await tester.enterText(numeric, value);
  }

  // The structured refusal the server actually sends for a Free venue with no
  // reusable material (l2_by_reference._refusal with nearby tours present).
  Map<String, dynamic> refusalStatus() => {
        'status': 'error',
        // The legacy prefixed string the orchestrator still raises — the app
        // must NOT show this.
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

  Future<void> submitAndFail(WidgetTester tester) async {
    await pumpScreen(tester);
    await tester.enterText(
        find.byType(TextField).first, 'Gyms near me, West Roxbury, MA');
    await setStops(tester, '2');
    await tester.runAsync(() async {
      await tester.tap(find.text('🎯 Generate Now'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pumpAndSettle();
  }

  testWidgets('by_reference refusal shows the plan dialog, not the red error',
      (tester) async {
    final client = buildClient(refusalStatus());
    await http.runWithClient(() async {
      await submitAndFail(tester);

      // The clean server message is shown.
      expect(
          find.textContaining(
              "This place hasn't been researched yet on the free level"),
          findsOneWidget);

      // The generic red dialog's title and the prefixed string must be ABSENT.
      expect(find.text('Tour Generation Failed'), findsNothing);
      expect(find.textContaining('Error in tour text generation:'),
          findsNothing);

      // The Free-level refusal title is shown.
      expect(find.text('Not available on the Free level yet'), findsOneWidget);
    }, () => client);
  });

  testWidgets('by_reference refusal offers a Buy a pack button', (tester) async {
    final client = buildClient(refusalStatus());
    await http.runWithClient(() async {
      await submitAndFail(tester);
      expect(find.widgetWithText(ElevatedButton, 'Buy a pack'), findsOneWidget);
    }, () => client);
  });

  testWidgets('by_reference refusal lists tappable nearby tours that open',
      (tester) async {
    final client = buildClient(refusalStatus());
    await http.runWithClient(() async {
      await submitAndFail(tester);

      // Both nearby tours are shown by name.
      expect(find.text('West Roxbury Walk'), findsOneWidget);
      expect(find.text('Roslindale Square'), findsOneWidget);

      // Tapping one opens (downloads) that tour by id.
      await tester.runAsync(() async {
        await tester.tap(find.text('West Roxbury Walk'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      expect(downloadsRequested.any((p) => p.contains('/download/123')), isTrue,
          reason: 'tapping a nearby tour must open it (download id 123); '
              'requests=$downloadsRequested');
    }, () => client);
  });
}
