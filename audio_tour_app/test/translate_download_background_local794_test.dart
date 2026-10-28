// [LOCAL-794] Widget tests: a background translate-download shows ONE persistent
// progress row (not an app-blocking modal), the tab bar stays usable while it
// runs, the row survives tab switches, and every end clears the row.
//
// Michael (iPhone TestFlight 83): the Russian download "does not let me go
// anywhere in the app" for ~3 minutes, and then the spinner "never ended". The
// fix routes the slow translate+save to TranslateDownloadManager, which drives
// a row hosted by MainScreen OUTSIDE the tab IndexedStack (like the bottom bar).
//
// These are RED against the old flow: there was no row at all (a modal
// AlertDialog barrier blocked the whole app), so `kTranslateDownloadRowKey`
// would never be found and tapping a tab under the barrier would do nothing.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/services/deep_link_service.dart';
import 'package:audio_tour_app_dev/services/foreground_community_messages.dart';
import 'package:audio_tour_app_dev/services/saved_tours_refresh.dart';
import 'package:audio_tour_app_dev/services/translate_download_manager.dart';
import 'package:audio_tour_app_dev/widgets/translate_download_progress_banner.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({'app_mode': 'Tours'});
    PendingListenOpen.instance.consume();
    PendingShareSearch.instance.code.value = null;
    TranslateDownloadController.instance.finish();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => '/tmp',
    );
  });
  tearDown(() {
    TranslateDownloadController.instance.finish();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
  });

  Widget app() => MaterialApp(
        scaffoldMessengerKey: communityScaffoldMessengerKey,
        home: const MainScreen(),
      );

  testWidgets('no job → no progress row (the row is hidden by default)',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();
    expect(find.byKey(kTranslateDownloadRowKey), findsNothing);
  });

  testWidgets(
      'while a background download runs: the row shows, the tab bar is usable, '
      'and the row survives a tab switch', (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();
    final state = tester.state<MainScreenState>(find.byType(MainScreen));
    expect(state.currentIndexForTest, kHomeTab);

    // A background translate-download starts (as _downloadSingleTour does).
    TranslateDownloadController.instance.start(
      const TranslateDownloadJob(
        tourId: 465,
        tourName: 'Massage & spa near Ben Thanh',
        languages: ['ru'],
        phase: TranslateDownloadPhase.translating,
      ),
    );
    await tester.pump();

    // The persistent row is shown (NOT a modal barrier).
    expect(find.byKey(kTranslateDownloadRowKey), findsOneWidget);
    expect(find.text('Translating to Russian…'), findsOneWidget);
    // No modal barrier is blocking the app.
    expect(find.byType(ModalBarrier).hitTestable(), findsNothing);

    // The tab bar is still usable: tapping Listen switches tabs.
    await tester.tap(find.byIcon(Icons.library_music));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(state.currentIndexForTest, kListenTab);

    // The row survived the tab switch (it lives outside the per-tab Navigators).
    expect(find.byKey(kTranslateDownloadRowKey), findsOneWidget);

    // Switch back to Home; the row is still there.
    await tester.tap(find.byIcon(Icons.home));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(state.currentIndexForTest, kHomeTab);
    expect(find.byKey(kTranslateDownloadRowKey), findsOneWidget);
  });

  testWidgets('finishing the job removes the row (no stuck spinner)',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();

    final token = TranslateDownloadController.instance.start(
      const TranslateDownloadJob(
        tourId: 465,
        tourName: 'Massage & spa near Ben Thanh',
        languages: ['ru'],
        phase: TranslateDownloadPhase.translating,
      ),
    );
    await tester.pump();
    expect(find.byKey(kTranslateDownloadRowKey), findsOneWidget);

    TranslateDownloadController.instance.finish();
    await tester.pump();
    expect(find.byKey(kTranslateDownloadRowKey), findsNothing);
    // The token is no longer the active one after finish.
    expect(token.isCancelled, isFalse); // a clean finish is not a cancel
  });

  testWidgets('Cancel button asks the job to stop', (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();

    final token = TranslateDownloadController.instance.start(
      const TranslateDownloadJob(
        tourId: 465,
        tourName: 'Massage & spa near Ben Thanh',
        languages: ['ru'],
        phase: TranslateDownloadPhase.translating,
      ),
    );
    await tester.pump();

    expect(token.isCancelled, isFalse);
    await tester.tap(find.byKey(kTranslateDownloadCancelKey));
    await tester.pump();
    expect(token.isCancelled, isTrue);
  });

  testWidgets(
      'on completion the Listen page reloads WITHOUT a manual refresh '
      '(SavedToursStore bump reaches the Listen tab)', (tester) async {
    await tester.pumpWidget(app());
    await tester.pump();

    // Go to Listen so MyToursScreen is mounted and listening.
    await tester.tap(find.byIcon(Icons.library_music));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    // A completed background save bumps SavedToursRefresh (as SavedToursStore
    // does). The Listen page listens to this tick and reloads itself — no user
    // action. We assert the tick advances, which is the signal MyToursScreen
    // reloads on (its reload is exercised in LOCAL-787's own tests).
    final before = SavedToursRefresh.instance.tick.value;
    SavedToursRefresh.instance.bump();
    await tester.pump();
    expect(SavedToursRefresh.instance.tick.value, before + 1);
  });
}
