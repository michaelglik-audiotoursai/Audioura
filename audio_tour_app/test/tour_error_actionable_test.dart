// [LOCAL-581] Widget tests for the actionable tour-generation error flow.
//
// Drives the REAL TourGeneratorScreen through its real submit → poll → error
// path, with http intercepted by a MockClient (via package:http runWithClient)
// and the app put in local server mode so no attestation / live server is
// touched. Each test asserts a defect fix:
//   • the server's own message is shown (defect #1), generic only as fallback;
//   • the LOCAL-580 suggestion button starts a NEW job with the suggested
//     request (same stop count);
//   • "Try again" re-submits the IDENTICAL request (defect #2);
//   • venue_no_verifiable_content shows "Edit request" (not "Try again") and
//     keeps the user's text.

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
    // Local mode => apiHeaders adds only Content-Type (no attestation, no
    // cloud key) and base() resolves to the local IP. All traffic flows
    // through http.post/http.get, which the MockClient intercepts.
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local581_test',
      'narrative_tone': 'general',
    });
  });

  /// Pumps the screen on a surface tall enough that the Generate button and
  /// the error dialog are on-screen and tappable.
  Future<void> pumpScreen(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 2600));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const MaterialApp(home: TourGeneratorScreen()));
    await tester.pump();
  }

  /// Records every POST to /generate-complete-tour and serves a scripted
  /// status response so the poll loop ends on the first error poll.
  ///
  /// [statusBody] is the JSON returned by GET /status/<id> (status 'error').
  late List<Map<String, dynamic>> generateBodies;

  MockClient buildClient(Map<String, dynamic> statusBody) {
    generateBodies = [];
    var jobCount = 0;
    return MockClient((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path.endsWith('/generate-complete-tour')) {
        generateBodies.add(
            jsonDecode(request.body) as Map<String, dynamic>);
        jobCount++;
        return http.Response(
          jsonEncode({'job_id': 'job_$jobCount'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      if (request.method == 'GET' && path.contains('/status/')) {
        return http.Response(
          jsonEncode(statusBody),
          200,
          headers: {'content-type': 'application/json'},
        );
      }
      // Any other call (e.g. user tracking PUT, tour-status POST) — succeed
      // quietly so the flow is not derailed by unrelated endpoints.
      return http.Response(jsonEncode({'ok': true, 'rows_affected': 1}), 200,
          headers: {'content-type': 'application/json'});
    });
  }

  /// Pumps the screen, enters [request] with [stops], taps Generate, and lets
  /// the submit+poll complete so the error dialog is shown.
  // The stop-count field is a bare numeric TextField; to set it reliably we
  // find it by its keyboardType. Helper used by tests.
  Future<void> setStops(WidgetTester tester, String value) async {
    final numeric = find.byWidgetPredicate((w) =>
        w is TextField && w.keyboardType == TextInputType.number);
    await tester.enterText(numeric, value);
  }

  testWidgets(
      'shows the server error verbatim and offers "Try again" (defects #1,#2)',
      (tester) async {
    const griffin =
        'We could not find enough verified material about "Griffin Museum of '
        'Photography" to build a tour. Try a broader request.';
    final client = buildClient({
      'status': 'error',
      'error': griffin,
    });

    await http.runWithClient(() async {
      await pumpScreen(tester);

      await tester.enterText(
          find.byType(TextField).first, 'Griffin Museum of Photography');
      await setStops(tester, '10');

      await tester.runAsync(() async {
        await tester.tap(find.text('🎯 Generate Now'));
        // Let submit + first poll resolve.
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      // Defect #1: the server's words are shown, not the generic string.
      expect(find.text(griffin), findsOneWidget);
      expect(find.textContaining('Unable to generate tour'), findsNothing);

      // Defect #2: a working "Try again" action exists (not "Try Again" that
      // only clears the box).
      expect(find.widgetWithText(TextButton, 'Try again'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Edit request'), findsNothing);
    }, () => client);
  });

  testWidgets('generic fallback only when the server sent no message',
      (tester) async {
    final client = buildClient({'status': 'failed'});

    await http.runWithClient(() async {
      await pumpScreen(tester);
      await tester.enterText(find.byType(TextField).first, 'Nowhere at all');
      await setStops(tester, '10');

      await tester.runAsync(() async {
        await tester.tap(find.text('🎯 Generate Now'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      expect(find.text('Unable to generate tour. Please try again.'),
          findsOneWidget);
    }, () => client);
  });

  testWidgets('"Try again" re-submits the IDENTICAL request (defect #2)',
      (tester) async {
    final client = buildClient({
      'status': 'error',
      'error': 'Transient failure, please retry.',
    });

    await http.runWithClient(() async {
      await pumpScreen(tester);
      await tester.enterText(
          find.byType(TextField).first, 'walking tour of Newton MA');
      await setStops(tester, '7');

      await tester.runAsync(() async {
        await tester.tap(find.text('🎯 Generate Now'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      expect(generateBodies.length, 1);
      final first = generateBodies.first;

      // Tap "Try again".
      await tester.runAsync(() async {
        await tester.tap(find.widgetWithText(TextButton, 'Try again'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      // A SECOND job was started with the identical request body.
      expect(generateBodies.length, 2);
      expect(generateBodies[1], equals(first));
      expect(generateBodies[1]['total_stops'], 7);
      expect(generateBodies[1]['location'], first['location']);
    }, () => client);
  });

  testWidgets(
      'suggestion button starts a NEW job with the suggested request, same stops',
      (tester) async {
    final client = buildClient({
      'status': 'error',
      'error': 'No verified material for that venue.',
      'suggestion': {
        'label': 'Walking tour of the neighbourhood',
        'request': 'walking tour of Winchester MA',
        'tour_type': 'walking',
      },
    });

    await http.runWithClient(() async {
      await pumpScreen(tester);
      await tester.enterText(
          find.byType(TextField).first, 'Griffin Museum of Photography');
      await setStops(tester, '12');

      await tester.runAsync(() async {
        await tester.tap(find.text('🎯 Generate Now'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      // The suggestion button is shown with the server's label.
      expect(find.text('Walking tour of the neighbourhood'), findsOneWidget);
      expect(generateBodies.length, 1);
      expect(generateBodies.first['total_stops'], 12);

      await tester.runAsync(() async {
        await tester.tap(find.text('Walking tour of the neighbourhood'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      // A new job started from the suggested request, keeping the stop count.
      expect(generateBodies.length, 2);
      expect(generateBodies[1]['location'], 'walking tour of Winchester MA');
      expect(generateBodies[1]['total_stops'], 12);
    }, () => client);
  });

  testWidgets(
      'venue_no_verifiable_content shows "Edit request", keeps text, no new job',
      (tester) async {
    final client = buildClient({
      'status': 'error',
      'error': 'We could not find enough verified material about that venue.',
      'error_code': 'venue_no_verifiable_content',
    });

    await http.runWithClient(() async {
      await pumpScreen(tester);
      await tester.enterText(
          find.byType(TextField).first, 'Griffin Museum of Photography');
      await setStops(tester, '10');

      await tester.runAsync(() async {
        await tester.tap(find.text('🎯 Generate Now'));
        await Future<void>.delayed(const Duration(milliseconds: 200));
      });
      await tester.pumpAndSettle();

      // Non-retryable: the action is "Edit request", not "Try again".
      expect(find.widgetWithText(TextButton, 'Edit request'), findsOneWidget);
      expect(find.widgetWithText(TextButton, 'Try again'), findsNothing);

      await tester.runAsync(() async {
        await tester.tap(find.widgetWithText(TextButton, 'Edit request'));
        await Future<void>.delayed(const Duration(milliseconds: 100));
      });
      await tester.pumpAndSettle();

      // No second job was started, and the user's text is still there to edit.
      expect(generateBodies.length, 1);
      expect(find.text('Griffin Museum of Photography'), findsOneWidget);
    }, () => client);
  });
}
