// [LOCAL-787] The Listen page must show a newly-saved tour AT ONCE, not ~30 s
// later (Michael, Pixel-7, 2026-10-27: "Tour downloaded successfully" then an
// empty Listen page for ~30 s).
//
// The fix funnels every saved_tours write through SavedToursStore.save, which
// bumps SavedToursRefresh. MyToursScreen listens to that tick and reloads in
// place. This test pins the promise end-to-end: render MyToursScreen on an
// empty list, call the helper to add a tour, and assert the row appears after a
// single reload cycle — no 30 s timer, no leaving and coming back.
//
// It can FAIL on purpose: drop the bump() inside SavedToursStore.save (or stop
// MyToursScreen listening) and the new row never appears → the final
// expectation goes red.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';
import 'package:audio_tour_app_dev/services/saved_tours_store.dart';
import 'package:audio_tour_app_dev/services/saved_tours_refresh.dart';

String _tour(String title) =>
    '{"title":"$title","path":"/tmp/does-not-exist",'
    '"created":"2026-10-27T10:00:00Z","tour_id":"555"}';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // _loadTours → _healTourPaths calls getApplicationDocumentsDirectory()
  // (path_provider), which has no implementation in the test VM. Mock it so the
  // reload completes and the list rebuilds.
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => '/tmp',
    );
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    // Leave the global tick where it is between tests (it only ever increases);
    // nothing to reset.
  });

  testWidgets(
      'SavedToursStore.save makes a new tour appear on the Listen page '
      'within one reload cycle (no 30 s wait)', (tester) async {
    // Start with an EMPTY Listen page.
    SharedPreferences.setMockInitialValues({
      'saved_tours': <String>[],
      'app_mode': 'Tours',
    });

    await tester.pumpWidget(const MaterialApp(home: MyToursScreen()));
    // Let the initial _loadTours settle.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // The empty state is shown; the tour is not there yet.
    expect(find.text('No tours yet.\nGenerate your first tour!'),
        findsOneWidget);
    expect(find.text('Freedom Trail'), findsNothing);

    // A writer (here, the download path's single helper) saves a tour. This is
    // the ONLY action — no tab switch, no resume, no 30 s timer.
    final prefs = await SharedPreferences.getInstance();
    final before = SavedToursRefresh.instance.tick.value;
    await SavedToursStore.save(prefs, [_tour('Freedom Trail')]);

    // The helper bumped the refresh tick (so the Listen page was told to
    // reload).
    expect(SavedToursRefresh.instance.tick.value, before + 1);

    // One reload cycle — pump the listener's _loadTours through its awaits.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // The row is there now.
    expect(find.text('Freedom Trail'), findsOneWidget);
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsNothing);
  });

  testWidgets(
      'SavedToursStore.save with bumpRefresh:false does NOT bump the tick '
      '(the background-isolate path)', (tester) async {
    SharedPreferences.setMockInitialValues({'saved_tours': <String>[]});
    final prefs = await SharedPreferences.getInstance();

    final before = SavedToursRefresh.instance.tick.value;
    await SavedToursStore.save(prefs, [_tour('Quiet Save')],
        bumpRefresh: false);

    // The write happened...
    expect(prefs.getStringList('saved_tours'), hasLength(1));
    // ...but no cross-isolate bump was attempted (the UI reloads on resume /
    // tab-select / prefs.reload instead).
    expect(SavedToursRefresh.instance.tick.value, before);
  });
}
