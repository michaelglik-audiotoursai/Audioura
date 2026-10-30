// [LOCAL-841] LIVE simulator screenshot test — a tour that finished while the
// app was backgrounded reaches the phone (Michael's coffee-tour 503).
//
// The generation + wait is driven by the shell (see SUBMISSION_LOCAL-841.md):
// it POSTs /generate-complete-tour and polls /status until completed, then runs
// this test with the completed job id in --dart-define=LOCAL841_JOB_ID=<id>.
// In-Dart poll loops stall on this iOS+Flutter integration binding, so the test
// itself does only single-shot async work (the pattern proven reliable):
//
//   1. Persist the real job as a PendingTourRequest — what _generateTourInner
//      does the moment the POST returns.
//   2. Render the REAL Listen page EMPTY and photograph it (the 503 state:
//      tour done on the server, nothing on the phone).
//   3. Fire AppLifecycleState.paused → resumed (the suspend/foreground the fix
//      hooks) and run the REAL PendingTourResumeHandler ONCE.
//   4. Assert it downloaded the completed tour from the LIVE /download endpoint,
//      cleared the pending entry, saved it, and that it now shows on Listen —
//      within 30 s. Photograph the populated Listen.
//
// Run (after the shell has a completed job id):
//   flutter drive \
//     --driver=test_driver/local841_screenshot_driver.dart \
//     --target=integration_test/local841_resume_live_test.dart \
//     -d <booted-sim-id> \
//     --dart-define=DEBUG_SERVER_IP=127.0.0.1 \
//     --dart-define=LOCAL841_JOB_ID=<completed-job-id>
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/my_tours_screen.dart';
import 'package:audio_tour_app_dev/services/pending_tour_requests_store.dart';
import 'package:audio_tour_app_dev/services/pending_tour_resume_handler.dart';

const String _userId = 'sim-live807';
const String _jobId = String.fromEnvironment('LOCAL841_JOB_ID');

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 150));
    }
  }

  Future<void> shot(WidgetTester tester, String name) async {
    await settle(tester);
    await binding.convertFlutterSurfaceToImage();
    await settle(tester);
    await binding.takeScreenshot(name);
  }

  testWidgets(
      'a tour generated while backgrounded is resumed and shows on Listen',
      (tester) async {
    expect(_jobId, isNotEmpty,
        reason: 'pass --dart-define=LOCAL841_JOB_ID=<completed job id>');

    SharedPreferences.setMockInitialValues({
      'user_id': _userId,
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'saved_tours': <String>[],
      PendingTourRequestsStore.key: <String>[],
    });
    final prefs = await SharedPreferences.getInstance();

    // 1. Persist the in-flight request exactly as _generateTourInner does the
    //    moment /generate-complete-tour returns a job id.
    await PendingTourRequestsStore.add(
      prefs,
      PendingTourRequest(
        jobId: _jobId,
        title: 'A short coffee walk near Union Square San Francisco',
        startedAt: DateTime.now().toUtc(),
        clientRequestId: 'cli-local841-live',
        languages: const ['en'],
        stopCount: '1',
      ),
    );
    expect(await PendingTourRequestsStore.load(prefs), hasLength(1));

    // 2. The REAL Listen page is EMPTY — the tour finished on the server while
    //    the app was suspended, but nothing has been downloaded yet (the 503).
    await tester.pumpWidget(const MaterialApp(home: MyToursScreen()));
    await settle(tester);
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsOneWidget,
        reason: 'Listen is empty until the pending download is resumed');
    await shot(tester, '01_listen_empty_tour_stuck_on_server');
    // Unmount so the resume handler's single runAsync is not blocked by the
    // screen's live refresh listener.
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SizedBox())));
    await settle(tester);

    // 3. Suspend → foreground, then run the REAL resume handler ONCE, exactly
    //    as AppSyncCoordinator does on resume.
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await settle(tester);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await settle(tester);

    final sw = Stopwatch()..start();
    final result = (await binding.runAsync(
        () => PendingTourResumeHandler.instance.run(prefs: prefs)))!;
    sw.stop();
    debugPrint('LOCAL841TEST downloaded=${result.downloaded} '
        'elapsed=${sw.elapsed.inSeconds}s');

    // 4. The completed tour was downloaded from the LIVE server, saved, and the
    //    pending entry cleared — all within 30 s of foregrounding.
    expect(result.downloaded, 1,
        reason: 'resume must download the completed tour from the live server');
    expect(sw.elapsed.inSeconds, lessThan(30),
        reason: 'tour must reach Listen within 30 s of foregrounding');
    expect(await PendingTourRequestsStore.load(prefs), isEmpty);
    expect(prefs.getStringList('saved_tours'), isNotEmpty);

    // Listen now shows the resumed tour — photograph it.
    await tester
        .pumpWidget(const MaterialApp(home: MyToursScreen(key: Key('listen2'))));
    await settle(tester);
    await shot(tester, '02_listen_tour_appeared_after_resume');
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsNothing);
  }, timeout: const Timeout(Duration(minutes: 6)));
}
