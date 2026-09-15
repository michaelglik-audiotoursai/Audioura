import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/edit_tour_screen.dart';

/// LOCAL-477 — Add Stop must NOT pop the screen it is editing.
///
/// The reported defect: pressing "+ Add Stop" ran a stray
/// `Navigator.pop(context)` inside `_addNewStop`, tearing down
/// `EditTourScreen` itself (there is no dialog to dismiss — the button is
/// wired straight to `_addNewStop`). The user was thrown back to the Listen
/// page and every unsaved edit in `_stops` was discarded, followed by a
/// `setState` on the disposed widget.
///
/// The existing `edit_stop_return_contract_test.dart` pins the *merge*
/// contract but nothing covered *navigation*. These tests pump the real
/// screen, tap the real button, and fail if the route is ever popped — i.e.
/// they go red the moment the stray pop is reinstated (AC #5).
///
/// The screen is rendered via the `debugInitialStops` seam so the loaded list
/// appears synchronously. The real `_loadTourStops` path does disk I/O and
/// awaits SharedPreferences at `initState` time; those awaits are bound to the
/// fake-async test zone and never resolve, so a full-load widget test would
/// hang. The seam only bypasses loading — the button, `_addNewStop`, the
/// Navigator wiring and Save-All gating under test are all the real code.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _PopCountingObserver popObserver;

  final seededStops = <Map<String, dynamic>>[
    {
      'stop_number': 1,
      'title': 'Stop 1',
      'text': 'Original text for stop one.',
      'original_text': 'Original text for stop one.',
      'audio_file': 'audio_1.mp3',
      'editable': true,
      'modified': false,
    },
    {
      'stop_number': 2,
      'title': 'Stop 2',
      'text': 'Original text for stop two.',
      'original_text': 'Original text for stop two.',
      'audio_file': 'audio_2.mp3',
      'editable': true,
      'modified': false,
    },
  ];

  setUp(() {
    // The screen fires unawaited DebugLogHelper calls that hit
    // SharedPreferences via a platform channel. Provide an in-memory fake so
    // those futures resolve instead of leaving anything pending.
    SharedPreferences.setMockInitialValues({});
    popObserver = _PopCountingObserver();
  });

  /// Pumps EditTourScreen pushed on top of a Home route, so a stray
  /// `Navigator.pop` inside the screen is both possible and observable.
  Future<void> pumpEditScreen(
    WidgetTester tester, {
    List<Map<String, dynamic>>? stops,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorObservers: [popObserver],
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => EditTourScreen(
                      tourData: const {'title': 'Test Tour', 'path': '/unused'},
                      debugInitialStops: stops ?? seededStops,
                    ),
                  ),
                ),
                child: const Text('Open Editor'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Open Editor'));
    await tester.pumpAndSettle();
  }

  testWidgets(
    'pressing "+ Add Stop" keeps the user on the edit screen (AC #1, #5)',
    (tester) async {
      await pumpEditScreen(tester);

      // We are on the editor, two stops loaded.
      expect(find.byType(EditTourScreen), findsOneWidget);
      expect(find.text('Stop 1'), findsOneWidget);
      expect(find.text('Stop 2'), findsOneWidget);

      final popsBefore = popObserver.popCount;

      await tester.tap(find.text('Add Stop'));
      await tester.pumpAndSettle();

      // AC #5: NO pop happened — the edit screen was NOT torn down.
      // With the stray `Navigator.pop(context)` reinstated this fails:
      // popCount increments and EditTourScreen is gone.
      expect(popObserver.popCount, popsBefore,
          reason: 'Add Stop must not pop the edit screen (LOCAL-477)');

      // AC #1: still on the edit screen, and a new "Stop 3" row appeared.
      expect(find.byType(EditTourScreen), findsOneWidget);
      expect(find.text('Stop 3'), findsOneWidget);
      expect(find.text('New'), findsOneWidget);
    },
  );

  testWidgets(
    'unsaved edits to other stops survive an add (AC #2)',
    (tester) async {
      // Simulate the user having edited stop 2 (modified: true, new text)
      // before pressing Add Stop.
      final editedStops = <Map<String, dynamic>>[
        Map<String, dynamic>.from(seededStops[0]),
        {
          ...seededStops[1],
          'text': 'EDITED text for stop two.',
          'modified': true,
          'action': 'modify',
        },
      ];

      await pumpEditScreen(tester, stops: editedStops);

      // Stop 2's edit is on screen before the add.
      expect(find.text('EDITED text for stop two.'), findsOneWidget);
      expect(find.text('Modified'), findsOneWidget);

      await tester.tap(find.text('Add Stop'));
      await tester.pumpAndSettle();

      // AC #2: stop 2 still reads its edited text and is still Modified —
      // `_addNewStop` only appends + sorts, it never drops or mutates the
      // rows the user already edited. With the old pop, the whole screen
      // (and every unsaved edit) vanished instead.
      expect(find.text('EDITED text for stop two.'), findsOneWidget);
      expect(find.text('Modified'), findsOneWidget);
      expect(find.text('Stop 3'), findsOneWidget);
    },
  );

  testWidgets(
    'Save All becomes enabled after an add (AC #3)',
    (tester) async {
      await pumpEditScreen(tester);

      // Before any change, Save All is disabled (no changes yet).
      final saveAllBefore = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Save All'),
      );
      expect(saveAllBefore.onPressed, isNull,
          reason: 'Save All should start disabled with no changes');

      await tester.tap(find.text('Add Stop'));
      await tester.pumpAndSettle();

      // After adding a stop (action: 'add'), _hasAnyChanges() is true and
      // Save All is enabled.
      final saveAllAfter = tester.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Save All'),
      );
      expect(saveAllAfter.onPressed, isNotNull,
          reason: 'Save All must be enabled after an add (LOCAL-477 AC #3)');
    },
  );

  testWidgets(
    'no "setState on disposed widget" flake after add (AC #4)',
    (tester) async {
      await pumpEditScreen(tester);

      await tester.tap(find.text('Add Stop'));
      await tester.pumpAndSettle();

      // If _addNewStop popped and then called setState on the disposed
      // State, the framework records an exception. Assert none occurred.
      expect(tester.takeException(), isNull,
          reason:
              'setState must not run on a disposed widget (LOCAL-477 AC #4)');
    },
  );
}

/// A NavigatorObserver that counts pops so a screen teardown is observable.
class _PopCountingObserver extends NavigatorObserver {
  int popCount = 0;

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    popCount++;
    super.didPop(route, previousRoute);
  }
}
