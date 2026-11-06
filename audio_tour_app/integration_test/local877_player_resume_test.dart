// [LOCAL-877] On-device proof (iOS simulator AND Android emulator):
//   start a tour, play stop 1, background the app (a REAL background driven by
//   the shell while this test waits), resume -> same screen, same stop, still
//   playing; tap NEXT on the persistent bar -> stop 2.
//
// No server and no paid API: the tour is a local fixture (3 looping tone
// stops, a real MP3) written into the app's Documents dir.
//
// Run (driven by tools/local877_device_run.sh, which performs the background):
//   flutter test integration_test/local877_player_resume_test.dart -d <device>
//
// The test prints `L877_MARKER:<name>` lines; the driver script reacts to
// `READY_FOR_BACKGROUND` by backgrounding + re-foregrounding the app, and to
// the other markers by taking screenshots. With no driver the test still runs:
// it falls back to simulated lifecycle events after BACKGROUND_WAIT_SECS.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_player_screen.dart';
import 'package:audio_tour_app_dev/services/player_session.dart';
import 'package:audio_tour_app_dev/widgets/persistent_player_bar.dart';

import 'mp3_fixture.dart';

const int _backgroundWaitSecs =
    int.fromEnvironment('BACKGROUND_WAIT_SECS', defaultValue: 14);

void marker(String name) {
  debugPrint('L877_MARKER:$name');
  // `flutter test` buffers stdout, so the driver cannot react in time. On the
  // iOS simulator the app shares the host filesystem: also append to a file the
  // driver tails (Android uses logcat, which is immediate).
  if (Platform.isIOS) {
    try {
      File('/tmp/l877_markers.txt')
          .writeAsStringSync('L877_MARKER:$name\n', mode: FileMode.append, flush: true);
    } catch (_) {}
  } else if (Platform.isAndroid) {
    // The emulator reaches the host at 10.0.2.2; the driver runs a tiny
    // listener there that appends the marker to its feed file.
    final c = HttpClient()..connectionTimeout = const Duration(seconds: 2);
    c
        .getUrl(Uri.parse('http://10.0.2.2:8877/L877_MARKER:$name'))
        .then((r) => r.close())
        .then((r) => r.drain<void>())
        .catchError((_) {})
        .whenComplete(() => c.close(force: true));
  }
}

Future<String> writeFixtureTour() async {
  final docs = await getApplicationDocumentsDirectory();
  final dir = Directory('${docs.path}/tours/local877_fixture');
  await dir.create(recursive: true);
  final mp3 = base64Decode(realMp3Base64);
  for (var i = 1; i <= 3; i++) {
    await File('${dir.path}/stop$i.mp3').writeAsBytes(mp3);
  }
  final stops = StringBuffer();
  for (var i = 1; i <= 3; i++) {
    stops.writeln('<h2 id="stopTitle$i">Stop $i: Fixture Place $i</h2>'
        '<audio id="audio$i" controls loop src="stop$i.mp3"></audio>');
  }
  await File('${dir.path}/index.html').writeAsString(
      '<!doctype html><html><head><meta name="viewport" '
      'content="width=device-width,initial-scale=1"><title>L877 fixture</title>'
      '</head><body><h1>LOCAL-877 fixture tour</h1>$stops</body></html>');
  return dir.path;
}

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> sleep(WidgetTester tester, int ms) async {
    await tester.runAsync(() => Future<void>.delayed(Duration(milliseconds: ms)));
    await tester.pump();
  }

  Future<void> until(WidgetTester tester, bool Function() cond, String what,
      {int secs = 45}) async {
    final end = DateTime.now().add(Duration(seconds: secs));
    while (!cond()) {
      if (DateTime.now().isAfter(end)) fail('timed out waiting for: $what');
      await sleep(tester, 250);
    }
  }

  PlayerSnapshot? snap() => PlayerSession.instance.snapshot.value;

  testWidgets('play stop 1, background, resume: same stop still playing; '
      'bar NEXT goes to stop 2', (tester) async {
    final tourPath = await writeFixtureTour();
    SharedPreferences.setMockInitialValues({
      'user_id': 'sim-l877',
      'app_mode': 'Tours',
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
    });
    await PlayerSession.instance.clear();

    await tester.pumpWidget(
        const MaterialApp(home: MainScreen(initialTab: kListenTab)));
    await sleep(tester, 1500);

    final state = tester.state<MainScreenState>(find.byType(MainScreen));
    final nav = state.tabNavigatorKeyForTest(kListenTab).currentState!;
    nav.push(MaterialPageRoute(
      builder: (_) => TourPlayerScreen(
        tourPath: tourPath,
        tourTitle: 'LOCAL-877 fixture tour',
        tourId: 'local877_fixture',
      ),
    ));
    await sleep(tester, 1000);
    expect(find.byKey(kPlayerBarKey), findsNothing,
        reason: 'bar hidden before any audio plays (idle)');

    // 1. Stop 1 plays (the player auto-starts it).
    await until(tester, () => snap()?.playing == true && snap()?.stopIndex == 0,
        'stop 1 playing');
    await sleep(tester, 800);
    expect(find.byKey(kPlayerBarKey), findsOneWidget,
        reason: 'bar visible while playing');
    final playSize = tester.getSize(find
        .ancestor(
            of: find.byKey(kPlayerBarPlayPauseKey),
            matching: find.byType(SizedBox))
        .first);
    expect(playSize.shortestSide, greaterThanOrEqualTo(64));
    marker('PLAYING_STOP1');
    await sleep(tester, 1500);

    final before = snap()!;
    final attachesBefore = PlayerSession.instance.attachCount;

    // 2. Background -> foreground. The driver does a REAL background of the
    //    app now; if no driver acts, simulate the lifecycle after the wait.
    marker('READY_FOR_BACKGROUND');
    var sawPaused = false;
    final observer = _LifecycleSpy((s) {
      if (s == AppLifecycleState.paused || s == AppLifecycleState.hidden) {
        sawPaused = true;
      }
    });
    binding.addObserver(observer);
    final waitEnd = DateTime.now().add(const Duration(seconds: _backgroundWaitSecs));
    while (DateTime.now().isBefore(waitEnd)) {
      await sleep(tester, 500);
    }
    if (!sawPaused) {
      marker('SIMULATED_LIFECYCLE');
      for (final s in [
        AppLifecycleState.inactive,
        AppLifecycleState.hidden,
        AppLifecycleState.paused,
        AppLifecycleState.hidden,
        AppLifecycleState.inactive,
        AppLifecycleState.resumed,
      ]) {
        binding.handleAppLifecycleStateChanged(s);
      }
    }
    binding.removeObserver(observer);
    await sleep(tester, 2500);
    marker('RESUMED');

    // 3. Same screen, same stop, still playing, audio not restarted.
    expect(nav.canPop(), isTrue, reason: 'still inside the tour, not thrown out');
    expect(find.byType(TourPlayerScreen), findsOneWidget);
    await until(tester, () => snap()?.playing == true, 'still playing after resume',
        secs: 20);
    expect(snap()!.stopIndex, 0, reason: 'same stop after resume');
    expect(snap()!.live, isTrue);
    // The fixture audio is a 1 s looping tone, so position wraps; prove "no
    // player re-init" instead: the same player stayed attached (no new attach).
    expect(PlayerSession.instance.attachCount, attachesBefore,
        reason: 'the player was not rebuilt on resume');
    marker('SAME_STOP_STILL_PLAYING');

    // 4. NEXT on the bar -> stop 2, playing.
    await tester.tap(find.byKey(kPlayerBarNextKey));
    await until(tester, () => snap()?.stopIndex == 1 && snap()?.playing == true,
        'stop 2 playing after bar NEXT');
    marker('NEXT_STOP2_PLAYING');
    await sleep(tester, 1200);

    // 5. Pause from the bar, then play again.
    await tester.tap(find.byKey(kPlayerBarPlayPauseKey));
    await until(tester, () => snap()?.playing == false, 'paused from bar');
    expect(find.byKey(kPlayerBarKey), findsOneWidget,
        reason: 'bar stays while paused mid-stop');
    marker('PAUSED_FROM_BAR');
    await tester.tap(find.byKey(kPlayerBarPlayPauseKey));
    await until(tester, () => snap()?.playing == true, 'playing again');
    await sleep(tester, 800);
    marker('DONE');
  });
}

class _LifecycleSpy with WidgetsBindingObserver {
  final void Function(AppLifecycleState) onState;
  _LifecycleSpy(this.onState);
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => onState(state);
}
