// [LOCAL-841] LIVE headless proof — a tour that finished while the app was
// backgrounded reaches the phone (Michael's 503). Asserts the REAL end-to-end
// resume against the LIVE Mac stack. No screenshots (convertFlutterSurfaceToImage
// is flaky on this iOS+Flutter combo); the real-app screenshots are captured
// separately with `xcrun simctl io screenshot`.
//
// The generation + wait is shell-driven; this test receives the completed job
// id via --dart-define=LOCAL841_JOB_ID and does only single-shot async work
// (in-Dart poll loops stall on this integration binding).
//
// Run (after the shell has a completed job id):
//   flutter test integration_test/local841_resume_live_headless_test.dart \
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

  testWidgets(
      'LIVE: a backgrounded generation is resumed and shows on Listen < 30 s',
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
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SizedBox())));
    await settle(tester);

    // 1. Persist the in-flight request exactly as _generateTourInner does the
    //    moment /generate-complete-tour returns a job id. Listen is empty now
    //    (saved_tours is empty) — the 503 state.
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
    expect(prefs.getStringList('saved_tours'), isEmpty,
        reason: 'nothing on the phone yet — the 503 state');

    // 2. Suspend → foreground, then run the REAL resume handler ONCE (single
    //    runAsync — the pattern proven reliable on this binding).
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    final sw = Stopwatch()..start();
    final result = (await binding.runAsync(
        () => PendingTourResumeHandler.instance.run(prefs: prefs)))!;
    sw.stop();
    debugPrint('LOCAL841TEST downloaded=${result.downloaded} '
        'elapsed=${sw.elapsed.inSeconds}s');

    // 3. Downloaded from the LIVE server, saved, pending cleared — within 30 s.
    expect(result.downloaded, 1,
        reason: 'resume must download the completed tour from the live server');
    expect(sw.elapsed.inSeconds, lessThan(30),
        reason: 'tour must reach Listen within 30 s of foregrounding');
    expect(await PendingTourRequestsStore.load(prefs), isEmpty);
    expect(prefs.getStringList('saved_tours'), isNotEmpty);

    // 4. The REAL Listen page now shows the resumed tour.
    await tester.pumpWidget(const MaterialApp(home: MyToursScreen()));
    await settle(tester);
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsNothing);
    debugPrint('LOCAL841TEST PASS: tour on Listen after resume');
  }, timeout: const Timeout(Duration(minutes: 6)));
}
