// [LOCAL-841] Screenshot-hold live test. Renders the REAL Listen page in its
// two states and HOLDS each long enough for `xcrun simctl io screenshot` to
// capture from the host (convertFlutterSurfaceToImage is flaky on this combo,
// so we photograph the live simulator surface instead):
//   * EMPTY  — the 503 state (tour done on the server, nothing on the phone),
//   * then the REAL resume downloads the completed tour from the LIVE stack,
//   * POPULATED — the resumed tour on Listen.
//
// Shell drives generation + waiting and passes the completed job id via
// --dart-define=LOCAL841_JOB_ID. Watch the host for the HOLD markers and shoot.
//
// Run:
//   flutter test integration_test/local841_screenshot_hold_test.dart \
//     -d <sim-id> --dart-define=DEBUG_SERVER_IP=127.0.0.1 \
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

  Future<void> hold(WidgetTester tester, int seconds) async {
    // Real wall-clock hold so a host-side `simctl io screenshot` can capture the
    // live surface. Pump periodically to keep the frame fresh during the wait.
    final end = DateTime.now().add(Duration(seconds: seconds));
    while (DateTime.now().isBefore(end)) {
      await tester.pump(const Duration(milliseconds: 100));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }

  testWidgets('screenshot hold: empty then resumed Listen', (tester) async {
    expect(_jobId, isNotEmpty);
    SharedPreferences.setMockInitialValues({
      'user_id': _userId,
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'saved_tours': <String>[],
      PendingTourRequestsStore.key: <String>[],
    });
    final prefs = await SharedPreferences.getInstance();
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

    // EMPTY Listen — hold for the shot.
    await tester.pumpWidget(const MaterialApp(home: MyToursScreen()));
    await hold(tester, 2);
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsOneWidget);
    debugPrint('LOCAL841SHOT HOLD_EMPTY_BEGIN');
    await hold(tester, 15);
    debugPrint('LOCAL841SHOT HOLD_EMPTY_END');

    // Unmount, run the REAL resume (single runAsync), remount populated.
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SizedBox())));
    await hold(tester, 1);
    final result = (await binding.runAsync(
        () => PendingTourResumeHandler.instance.run(prefs: prefs)))!;
    debugPrint('LOCAL841SHOT downloaded=${result.downloaded}');
    expect(result.downloaded, 1);

    await tester.pumpWidget(const MaterialApp(home: MyToursScreen(key: Key('l2'))));
    await hold(tester, 2);
    expect(find.text('No tours yet.\nGenerate your first tour!'), findsNothing);
    debugPrint('LOCAL841SHOT HOLD_POPULATED_BEGIN');
    await hold(tester, 20);
    debugPrint('LOCAL841SHOT HOLD_POPULATED_END');
  }, timeout: const Timeout(Duration(minutes: 3)));
}
