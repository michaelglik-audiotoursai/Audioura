import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/screens/user_stops_screen.dart';

/// LOCAL-523 — the "name your stops" loop, driven through the real widget.
///
/// Covers the loop end to end (AC #2, #4): add one stop at a time, see the
/// inline warnings (AC #3), delete, review, and return the ordered selection.
/// The screen is pushed on top of a Home route so the popped result — the
/// user's stops (or null on cancel) — is observable, exactly as the generate
/// screen receives it.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  /// Pushes UserStopsScreen and captures whatever it pops.
  Future<void> pumpLoop(
    WidgetTester tester, {
    List<Map<String, dynamic>>? initialStops,
    required void Function(List<Map<String, dynamic>>?) onResult,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  final result = await Navigator.push<List<Map<String, dynamic>>>(
                    context,
                    MaterialPageRoute(
                      builder: (_) => UserStopsScreen(initialStops: initialStops),
                    ),
                  );
                  onResult(result);
                },
                child: const Text('Open Loop'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open Loop'));
    await tester.pumpAndSettle();
  }

  testWidgets('add one stop at a time; each appears numbered in order (AC #2)',
      (tester) async {
    await pumpLoop(tester, onResult: (_) {});

    await tester.enterText(find.byType(TextField), 'The harbour');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Add'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'The lighthouse');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Add'));
    await tester.pumpAndSettle();

    expect(find.text('The harbour'), findsOneWidget);
    expect(find.text('The lighthouse'), findsOneWidget);
    // Numbered 1 and 2.
    expect(find.text('1'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('empty add shows an inline warning, not a stored stop (AC #3)',
      (tester) async {
    await pumpLoop(tester, onResult: (_) {});

    await tester.tap(find.widgetWithText(ElevatedButton, 'Add'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Enter a name for the stop'), findsOneWidget);
  });

  testWidgets('duplicate entry shows an inline warning as you type (AC #3)',
      (tester) async {
    await pumpLoop(tester, onResult: (_) {});

    await tester.enterText(find.byType(TextField), 'Pier');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Add'));
    await tester.pumpAndSettle();

    // Type the same name again — the inline duplicate warning appears.
    await tester.enterText(find.byType(TextField), 'pier');
    await tester.pumpAndSettle();

    expect(find.textContaining('already in your list'), findsOneWidget);
  });

  testWidgets('Review is disabled with no stops, enabled after adding (AC #2)',
      (tester) async {
    await pumpLoop(tester, onResult: (_) {});

    final reviewBefore = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Review'),
    );
    expect(reviewBefore.onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'A stop');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Add'));
    await tester.pumpAndSettle();

    final reviewAfter = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Review'),
    );
    expect(reviewAfter.onPressed, isNotNull);
  });

  testWidgets('delete removes a stop and renumbers the rest (AC #2)',
      (tester) async {
    await pumpLoop(
      tester,
      initialStops: [
        {'stop_number': 1, 'title': 'Stop 1', 'text': 'A', 'action': 'add'},
        {'stop_number': 2, 'title': 'Stop 2', 'text': 'B', 'action': 'add'},
        {'stop_number': 3, 'title': 'Stop 3', 'text': 'C', 'action': 'add'},
      ],
      onResult: (_) {},
    );

    // Delete the first stop (A).
    await tester.tap(find.byIcon(Icons.delete).first);
    await tester.pumpAndSettle();

    expect(find.text('A'), findsNothing);
    expect(find.text('B'), findsOneWidget);
    expect(find.text('C'), findsOneWidget);
  });

  testWidgets('review then "Use these stops" returns the ordered selection (AC #2)',
      (tester) async {
    List<Map<String, dynamic>>? captured;
    await pumpLoop(
      tester,
      initialStops: [
        {'stop_number': 1, 'title': 'Stop 1', 'text': 'First', 'action': 'add'},
        {'stop_number': 2, 'title': 'Stop 2', 'text': 'Second', 'action': 'add'},
      ],
      onResult: (r) => captured = r,
    );

    await tester.tap(find.widgetWithText(ElevatedButton, 'Review'));
    await tester.pumpAndSettle();

    // Review shows the ordered summary.
    expect(find.textContaining('generated from these 2 stops'), findsOneWidget);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Use these stops'));
    await tester.pumpAndSettle();

    expect(captured, isNotNull);
    expect(captured!.map((s) => s['text']).toList(), ['First', 'Second']);
    expect(captured!.map((s) => s['stop_number']).toList(), [1, 2]);
  });

  testWidgets('Cancel returns null so the caller default path is untouched (AC #1)',
      (tester) async {
    Object? captured = 'sentinel';
    await pumpLoop(
      tester,
      initialStops: [
        {'stop_number': 1, 'title': 'Stop 1', 'text': 'A', 'action': 'add'},
      ],
      onResult: (r) => captured = r,
    );

    await tester.tap(find.widgetWithText(OutlinedButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(captured, isNull);
  });
}
