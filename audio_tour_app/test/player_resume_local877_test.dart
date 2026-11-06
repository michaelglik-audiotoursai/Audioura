// [LOCAL-877] Sophia: reopening the app threw her out of the tour and stopped
// the audio; she wanted a big play/pause at the bottom; the thumbs could not be
// dismissed or changed.
//
//   1. Resume keeps the route (and the player widget is NOT disposed/rebuilt).
//   2. The persistent bar is visible while playing / paused mid-stop, hidden
//      when idle, with a >= 64 dp play/pause, prev/next, title and progress.
//   3. Thumbs: collapse to "thanks · change", dismiss with x, change by tapping
//      the other thumb (an update in the outbox, not a duplicate).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/main_screen.dart';
import 'package:audio_tour_app_dev/services/outbox_service.dart';
import 'package:audio_tour_app_dev/services/player_session.dart';
import 'package:audio_tour_app_dev/services/stop_feedback_service.dart';
import 'package:audio_tour_app_dev/widgets/persistent_player_bar.dart';
import 'package:audio_tour_app_dev/widgets/swipe_feedback_widget.dart';
import 'package:flutter/services.dart';

/// A stand-in for the tour player screen: counts initState/dispose so a test
/// can prove the widget survived a resume.
class _FakePlayer extends StatefulWidget {
  static int inits = 0;
  static int disposes = 0;
  const _FakePlayer();
  @override
  State<_FakePlayer> createState() => _FakePlayerState();
}

class _FakePlayerState extends State<_FakePlayer> {
  @override
  void initState() {
    super.initState();
    _FakePlayer.inits++;
  }

  @override
  void dispose() {
    _FakePlayer.disposes++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('FAKE PLAYER STOP 1')));
}

Future<void> _backgroundAndResume(WidgetTester tester) async {
  final b = tester.binding;
  b.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
  b.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
  b.handleAppLifecycleStateChanged(AppLifecycleState.paused);
  await tester.pump();
  b.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
  b.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
  b.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
}

PlayerSnapshot _snap({
  bool playing = true,
  bool started = true,
  bool live = true,
  int stop = 0,
  int? total = 3,
}) =>
    PlayerSnapshot(
      tourPath: '/tmp/tour',
      tourTitle: 'Beacon Hill',
      stopIndex: stop,
      totalStops: total,
      stopName: 'Stop title $stop',
      playing: playing,
      started: started,
      live: live,
      positionSeconds: 30,
      durationSeconds: 120,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'app_mode': 'Tours',
      'user_id': 'u877',
    });
    await PlayerSession.instance.resetForTest();
    _FakePlayer.inits = 0;
    _FakePlayer.disposes = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => '/tmp',
    );
    StopFeedbackService.enableTestMode();
    await OutboxService.instance.resetForTest();
  });

  group('[LOCAL-877] resume keeps the listener in the tour', () {
    testWidgets('resume does not pop a screen open on the Listen tab',
        (tester) async {
      await tester.pumpWidget(
          const MaterialApp(home: MainScreen(initialTab: kListenTab)));
      await tester.pump();
      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      final nav = state.tabNavigatorKeyForTest(kListenTab).currentState!;

      nav.push(MaterialPageRoute(builder: (_) => const _FakePlayer()));
      await tester.pumpAndSettle();
      expect(find.text('FAKE PLAYER STOP 1'), findsOneWidget);
      expect(_FakePlayer.inits, 1);

      await _backgroundAndResume(tester);

      // Same screen, same State object: never disposed, never re-initialised.
      expect(find.text('FAKE PLAYER STOP 1'), findsOneWidget);
      expect(nav.canPop(), isTrue);
      expect(_FakePlayer.inits, 1);
      expect(_FakePlayer.disposes, 0);
    });

    testWidgets('resume with a tour in progress never resets the root either',
        (tester) async {
      await tester.pumpWidget(
          const MaterialApp(home: MainScreen(initialTab: kListenTab)));
      await tester.pump();
      PlayerSession.instance.snapshot.value = _snap();

      // Even at the Listen root, a started tour blocks the reset: the key of the
      // root route is unchanged after the resume.
      final before = find.byKey(const ValueKey('listen_0'));
      expect(before, findsOneWidget);
      await _backgroundAndResume(tester);
      expect(find.byKey(const ValueKey('listen_0')), findsOneWidget);
    });

    testWidgets('a long absence (hours) still lands on the same screen',
        (tester) async {
      await tester.pumpWidget(
          const MaterialApp(home: MainScreen(initialTab: kListenTab)));
      await tester.pump();
      final state = tester.state<MainScreenState>(find.byType(MainScreen));
      final nav = state.tabNavigatorKeyForTest(kListenTab).currentState!;
      nav.push(MaterialPageRoute(builder: (_) => const _FakePlayer()));
      await tester.pumpAndSettle();

      await _backgroundAndResume(tester);
      await _backgroundAndResume(tester);
      expect(find.text('FAKE PLAYER STOP 1'), findsOneWidget);
      expect(_FakePlayer.disposes, 0);
    });

    testWidgets('an idle tab at its root is still refreshed on resume',
        (tester) async {
      await tester.pumpWidget(
          const MaterialApp(home: MainScreen(initialTab: kListenTab)));
      await tester.pump();
      expect(find.byKey(const ValueKey('listen_0')), findsOneWidget);
      await _backgroundAndResume(tester);
      // Old behaviour kept where it is harmless: root rebuilt with a new key.
      expect(find.byKey(const ValueKey('listen_1')), findsOneWidget);
    });
  });

  group('[LOCAL-877] persistent player bar', () {
    Widget host({void Function(PlayerSnapshot)? onOpen}) => MaterialApp(
          home: Scaffold(
            body: const SizedBox.expand(),
            bottomNavigationBar: PersistentPlayerBar(
              session: PlayerSession.instance,
              onOpen: onOpen ?? (_) {},
            ),
          ),
        );

    testWidgets('hidden when idle', (tester) async {
      await tester.pumpWidget(host());
      expect(find.byKey(kPlayerBarKey), findsNothing);
    });

    testWidgets('hidden for a tour that was opened but never played',
        (tester) async {
      PlayerSession.instance.snapshot.value = _snap(playing: false, started: false);
      await tester.pumpWidget(host());
      expect(find.byKey(kPlayerBarKey), findsNothing);
    });

    testWidgets('visible while playing, with a >= 64 dp play/pause',
        (tester) async {
      PlayerSession.instance.snapshot.value = _snap();
      await tester.pumpWidget(host());
      expect(find.byKey(kPlayerBarKey), findsOneWidget);
      expect(find.text('Stop title 0'), findsOneWidget);
      expect(find.byKey(kPlayerBarProgressKey), findsOneWidget);
      expect(find.byKey(kPlayerBarPrevKey), findsOneWidget);
      expect(find.byKey(kPlayerBarNextKey), findsOneWidget);
      final size = tester.getSize(find
          .ancestor(
              of: find.byKey(kPlayerBarPlayPauseKey),
              matching: find.byType(SizedBox))
          .first);
      expect(size.width, greaterThanOrEqualTo(64));
      expect(size.height, greaterThanOrEqualTo(64));
    });

    testWidgets('visible while paused mid-stop and appears/disappears live',
        (tester) async {
      await tester.pumpWidget(host());
      expect(find.byKey(kPlayerBarKey), findsNothing);
      PlayerSession.instance.snapshot.value = _snap(playing: false);
      await tester.pump();
      expect(find.byKey(kPlayerBarKey), findsOneWidget);
      expect(find.byIcon(Icons.play_arrow), findsOneWidget);
      PlayerSession.instance.snapshot.value = null;
      await tester.pump();
      expect(find.byKey(kPlayerBarKey), findsNothing);
    });

    testWidgets('play/pause, next and previous drive the live player',
        (tester) async {
      final calls = <String>[];
      final owner = Object();
      PlayerSession.instance.attach(
        owner: owner,
        initial: _snap(live: true, stop: 1),
        commands: PlayerCommands(
          play: () async => calls.add('play'),
          pause: () async => calls.add('pause'),
          next: () async => calls.add('next'),
          previous: () async => calls.add('previous'),
        ),
      );
      PlayerSession.instance.update(owner, playing: true);
      await tester.pumpWidget(host());

      await tester.tap(find.byKey(kPlayerBarPlayPauseKey));
      await tester.tap(find.byKey(kPlayerBarNextKey));
      await tester.tap(find.byKey(kPlayerBarPrevKey));
      expect(calls, ['pause', 'next', 'previous']);

      PlayerSession.instance.update(owner, playing: false);
      await tester.pump();
      await tester.tap(find.byKey(kPlayerBarPlayPauseKey));
      expect(calls.last, 'play');
    });

    testWidgets('tapping the bar opens the tour at the current stop',
        (tester) async {
      PlayerSnapshot? opened;
      PlayerSession.instance.snapshot.value = _snap(stop: 2);
      await tester.pumpWidget(host(onOpen: (s) => opened = s));
      await tester.tap(find.byKey(kPlayerBarOpenKey));
      expect(opened?.stopIndex, 2);
      expect(opened?.tourPath, '/tmp/tour');
    });

    testWidgets('cold start shows "Resume <tour>, stop N"', (tester) async {
      PlayerSnapshot? opened;
      PlayerSession.instance.snapshot.value = _snap(live: false, stop: 3, total: 8, playing: false);
      await tester.pumpWidget(host(onOpen: (s) => opened = s));
      expect(find.text('Resume Beacon Hill, stop 4'), findsOneWidget);
      await tester.tap(find.byKey(kPlayerBarPlayPauseKey));
      expect(opened?.stopIndex, 3);
    });

    test('session persists tour + stop and restores after a kill', () async {
      final owner = Object();
      PlayerSession.instance.attach(
        owner: owner,
        initial: _snap(live: true, stop: 0),
        commands: PlayerCommands(
          play: () async {},
          pause: () async {},
          next: () async {},
          previous: () async {},
        ),
      );
      PlayerSession.instance.update(owner, stopIndex: 2, playing: true);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      PlayerSession.instance.detach(owner);
      await Future<void>.delayed(const Duration(milliseconds: 50));

      // "Kill": drop the in-memory session, keep SharedPreferences.
      await PlayerSession.instance.resetForTest();
      expect(PlayerSession.instance.snapshot.value, isNull);
      final restored = await PlayerSession.instance.restore();
      expect(restored, isNotNull);
      expect(restored!.stopIndex, 2);
      expect(restored.tourTitle, 'Beacon Hill');
      expect(restored.live, isFalse);
      expect(PlayerSession.instance.barVisible, isTrue);
    });

    test('restore drops a tour whose files are gone', () async {
      SharedPreferences.setMockInitialValues({
        'player_last_session_v1':
            '{"tour_path":"/gone","tour_title":"X","stop_index":1}',
      });
      final r = await PlayerSession.instance.restore(pathExists: (_) => false);
      expect(r, isNull);
    });
  });

  group('[LOCAL-877] thumbs: collapse, dismiss, change', () {
    Future<void> pumpThumbs(WidgetTester tester, {int stop = 0}) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SwipeFeedbackWidget(
            currentStopIndex: stop,
            tourId: 'tour_877',
            tourPath: '/tmp/test_tour',
          ),
        ),
      ));
      await tester.pump();
    }

    Future<List<Map<String, dynamic>>> pending() =>
        StopFeedbackService().getPendingQueue();

    testWidgets('after a choice it collapses to a small thanks · change chip',
        (tester) async {
      await pumpThumbs(tester);
      await tester.tap(find.text('More like this'));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Undo'), findsOneWidget);

      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byKey(const ValueKey('answered_chip')), findsOneWidget);
      expect(find.textContaining('Thanks'), findsOneWidget);
      expect(find.text('change'), findsOneWidget);
      expect(find.text('More like this'), findsNothing); // big thumbs gone.
    });

    testWidgets('the x dismisses the thumbs entirely', (tester) async {
      await pumpThumbs(tester);
      await tester.tap(find.byKey(const ValueKey('feedback_dismiss')));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('More like this'), findsNothing);
      expect(find.text('Not for me'), findsNothing);
      expect(find.byKey(const ValueKey('feedback_dismissed')), findsOneWidget);
    });

    testWidgets('the chip can be dismissed too', (tester) async {
      await pumpThumbs(tester);
      await tester.tap(find.text('Not for me'));
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.byKey(const ValueKey('feedback_dismiss')));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byKey(const ValueKey('answered_chip')), findsNothing);
      expect(find.byKey(const ValueKey('feedback_dismissed')), findsOneWidget);
    });

    testWidgets('tapping the other thumb changes the answer: one update, no duplicate',
        (tester) async {
      await pumpThumbs(tester, stop: 4);
      await tester.tap(find.text('More like this'));
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 400));
      var q = await pending();
      expect(q.length, 1);
      expect(q.single['swipe'], 1);

      await tester.tap(find.text('change'));
      await tester.pumpAndSettle();
      // Thumbs are back, both tappable, the chosen one highlighted.
      expect(find.byIcon(Icons.thumb_up), findsOneWidget);
      await tester.tap(find.text('Not for me'));
      await tester.pump(const Duration(milliseconds: 300));

      q = await pending();
      expect(q.length, 1, reason: 'replaced, not duplicated');
      expect(q.single['swipe'], -1);
      expect(q.single['stop_index'], 4);
      expect(find.textContaining('Noted — less like this'), findsOneWidget);

      await tester.pump(const Duration(seconds: 5));
    });

    testWidgets('a different stop gets a fresh question, not the old chip',
        (tester) async {
      await pumpThumbs(tester, stop: 0);
      await tester.tap(find.text('More like this'));
      await tester.pump(const Duration(seconds: 5));
      await pumpThumbs(tester, stop: 1);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('More like this'), findsOneWidget);
    });
  });
}
