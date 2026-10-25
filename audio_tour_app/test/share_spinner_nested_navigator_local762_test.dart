// [LOCAL-762] Red-first tests for the Share spinner that never closes.
//
// Regression from LOCAL-761: that task put every bottom-nav tab inside its own
// nested Navigator (an IndexedStack of Navigators). `showDialog` /
// `showModalBottomSheet` default to `useRootNavigator: true`, so the progress
// dialog they push lives on the ROOT navigator. Dismissing it later with a
// plain `Navigator.of(context).pop()` / `Navigator.pop(context)` from a SCREEN
// that now sits inside a tab Navigator pops the TAB's nested navigator instead
// — the dialog stays up forever ("Creating share code…" spinning) and a tab
// route is popped out from under the user.
//
// The fix is to dismiss with `Navigator.of(context, rootNavigator: true).pop()`.
//
// Test 1 pins the generic contract against a faithful reproduction of the
// LOCAL-761 structure (a screen inside a nested Navigator, below a root route):
// the ROOT-pushed progress dialog closes and the tab route underneath is NOT
// popped. It is RED against a bare `Navigator.of(context).pop()`.
//
// Test 2 drives the real `shareTour` through its progress-dialog path using a
// non-numeric tour id, which `TourShareService.share` rejects locally (no
// network): the "Creating share code…" dialog must be gone afterwards and the
// screen beneath it must still be there.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:audio_tour_app_dev/widgets/share_tour_sheet.dart';

/// Mimics a screen that lives inside a tab's nested Navigator: it opens a
/// progress dialog on the ROOT navigator, awaits a (fake) async op, then
/// dismisses it with [popWithRootNavigator] controlling which navigator is
/// targeted — exactly the choice LOCAL-762 fixes.
class _ProgressOpener extends StatelessWidget {
  final bool popWithRootNavigator;
  const _ProgressOpener({required this.popWithRootNavigator});

  Future<void> _run(BuildContext context) async {
    showDialog<void>(
      context: context, // default useRootNavigator: true → dialog on ROOT
      barrierDismissible: false,
      builder: (_) => const AlertDialog(content: Text('Creating share code…')),
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));
    if (!context.mounted) return;
    if (popWithRootNavigator) {
      Navigator.of(context, rootNavigator: true).pop(); // the fix
    } else {
      Navigator.of(context).pop(); // the bug: pops the tab's nested navigator
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ElevatedButton(
          onPressed: () => _run(context),
          child: const Text('GO'),
        ),
      ),
    );
  }
}

/// A root-level MaterialApp whose home hosts a nested Navigator (the tab), with
/// the given screen as that tab's first route — the LOCAL-761 shape in minimum.
Widget _appWithNestedTab(Widget tabFirstScreen) {
  final nestedKey = GlobalKey<NavigatorState>();
  return MaterialApp(
    home: Scaffold(
      body: Navigator(
        key: nestedKey,
        onGenerateRoute: (_) => MaterialPageRoute(
          builder: (_) => tabFirstScreen,
        ),
      ),
      bottomNavigationBar: const SizedBox(
        key: Key('persistent-bar'),
        height: 56,
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('[LOCAL-762] progress dialog inside a nested tab Navigator', () {
    testWidgets(
        'root-pushed progress dialog CLOSES and the tab route is NOT popped',
        (tester) async {
      await tester.pumpWidget(
        _appWithNestedTab(
          const _ProgressOpener(popWithRootNavigator: true),
        ),
      );
      await tester.pump();

      // The tab's first screen and the persistent bar are present.
      expect(find.text('GO'), findsOneWidget);
      expect(find.byKey(const Key('persistent-bar')), findsOneWidget);

      await tester.tap(find.text('GO'));
      await tester.pump(); // show dialog
      expect(find.text('Creating share code…'), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 20)); // finish async
      await tester.pump(); // settle pop

      // The dialog is gone …
      expect(find.text('Creating share code…'), findsNothing);
      // … and the tab's own screen is still underneath (NOT popped away).
      expect(find.text('GO'), findsOneWidget);
      expect(find.byKey(const Key('persistent-bar')), findsOneWidget);
    });

    testWidgets(
        'the BUG reproduction: popping the nested navigator leaves the dialog '
        'up and pops the tab screen', (tester) async {
      await tester.pumpWidget(
        _appWithNestedTab(
          const _ProgressOpener(popWithRootNavigator: false),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('GO'));
      await tester.pump();
      expect(find.text('Creating share code…'), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 20));
      await tester.pump();

      // With the buggy pop: the root dialog is STILL up (never dismissed).
      expect(find.text('Creating share code…'), findsOneWidget);
    });
  });

  group('[LOCAL-762] shareTour dismisses its own progress dialog', () {
    testWidgets(
        'inside a nested tab Navigator, a non-numeric id path closes the '
        '"Creating share code…" dialog and keeps the screen', (tester) async {
      // Capture a BuildContext that lives INSIDE the nested Navigator.
      late BuildContext tabContext;
      final screen = Builder(builder: (ctx) {
        tabContext = ctx;
        return const Scaffold(body: Center(child: Text('LISTEN')));
      });

      await tester.pumpWidget(_appWithNestedTab(screen));
      await tester.pump();
      expect(find.text('LISTEN'), findsOneWidget);

      // A non-numeric id is rejected locally by TourShareService.share (no
      // network), so this deterministically runs the showDialog + pop path.
      // (The dialog's mid-flight visibility is pinned by the generic tests
      // above; the local-failure path can resolve within one microtask turn,
      // so here we assert the END state: the spinner is gone and the screen
      // underneath survived.)
      await shareTour(
        tabContext,
        audioTourId: 'job-abc', // not a numeric row id → local failure
        tourName: 'Test Tour',
      );
      await tester.pump();
      await tester.pump();

      // The progress dialog is dismissed and the Listen screen is still here.
      expect(find.text('Creating share code…'), findsNothing);
      expect(find.text('LISTEN'), findsOneWidget);
    });
  });
}
