import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/services/fillings_model.dart';
import 'package:audio_tour_app_dev/services/on_the_way_controller.dart';

import 'otw_test_support.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  group('auto-play after a stop (LOCAL-908 item 2)', () {
    testWidgets('default topic starts after a 5 s countdown', (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      expect(r.c.mode, OtwMode.countdown);
      expect(r.c.item!.segmentId, 1); // the leg's FIRST item = the default
      expect(r.c.countdownLeft, 5);
      await t.pump(const Duration(seconds: 4));
      expect(r.c.mode, OtwMode.countdown);
      expect(r.audio.calls, isEmpty);
      await t.pump(const Duration(seconds: 1));
      expect(r.c.mode, OtwMode.topic);
      expect(r.audio.calls, ['play:1@0.0']);
      expect(r.events, ['start:1@0']);
    });

    testWidgets('auto-play off: the leg starts quiet, nothing plays', (t) async {
      final r = Rig(autoPlay: false);
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      expect(r.c.mode, OtwMode.quiet);
      await t.pump(const Duration(seconds: 10));
      expect(r.audio.calls, isEmpty);
      expect(r.events, isEmpty);
    });

    test('"always quiet" turns topics off entirely: no state change at all', () {
      final r = Rig(alwaysQuiet: true);
      addTearDown(r.dispose);
      expect(r.c.active, isFalse);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      expect(r.c.mode, OtwMode.stop);
      expect(r.c.leg, isNull);
      expect(r.c.holdAfterStops, isEmpty);
      expect(r.c.mediaNext, MediaNextAction.nextStop);
    });

    test('a leg with no topics, and the last stop, change nothing', () {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(1); // leg after stop 2 has no items in the fixture
      r.c.onStopFinished(1);
      expect(r.c.mode, OtwMode.stop);
      r.c.onStopStarted(3);
      r.c.onStopFinished(3);
      expect(r.c.mode, OtwMode.stop);
    });

    testWidgets('turning "always quiet" on mid-topic stops it', (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      expect(r.c.mode, OtwMode.topic);
      unawaited(r.settings.setAlwaysQuiet(true)); // applies synchronously
      expect(r.c.mode, OtwMode.stop);
      expect(r.audio.calls.last, startsWith('fade'));
    });
  });

  group('hands-free skip (item 3)', () {
    test('mapMediaNext: stop keeps today, topic/countdown skip, quiet ignored', () {
      expect(mapMediaNext(OtwMode.stop), MediaNextAction.nextStop);
      expect(mapMediaNext(OtwMode.countdown), MediaNextAction.skipTopic);
      expect(mapMediaNext(OtwMode.topic), MediaNextAction.skipTopic);
      expect(mapMediaNext(OtwMode.quiet), MediaNextAction.ignore);
      // Topics off or no fillings: always today's behaviour.
      for (final m in OtwMode.values) {
        expect(mapMediaNext(m, topicsActive: false), MediaNextAction.nextStop);
      }
    });

    testWidgets('skip walks the menu in order, then silence', (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5)); // item 1 (segment 1)
      await t.pump(const Duration(seconds: 20));
      r.c.onTopicPosition(20);
      r.c.skip(); // -> segment 3, immediately
      expect(r.c.mode, OtwMode.topic);
      expect(r.c.item!.segmentId, 3);
      r.c.skip(); // -> segment 2
      expect(r.c.item!.segmentId, 2);
      r.c.skip(); // -> segment 4
      expect(r.c.item!.segmentId, 4);
      r.c.skip(); // after the last item: silence
      expect(r.c.mode, OtwMode.quiet);
      expect(r.c.mediaNext, MediaNextAction.ignore);
      expect(r.events.where((e) => e.startsWith('skip')).length, 4);
      expect(r.events.first, 'start:1@0');
      expect(r.events[1], 'skip:1@20'); // at_sec carried
    });

    testWidgets('skipping the countdown offers the next topic, no event',
        (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      r.c.skip();
      expect(r.c.mode, OtwMode.countdown);
      expect(r.c.item!.segmentId, 3);
      expect(r.c.countdownLeft, 5);
      expect(r.events, isEmpty); // nothing was heard, nothing to report
      await t.pump(const Duration(seconds: 5));
      expect(r.c.mode, OtwMode.topic);
      expect(r.c.item!.segmentId, 3);
    });

    test('during a stop, skip() does nothing', () {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.skip();
      expect(r.c.mode, OtwMode.stop);
      expect(r.events, isEmpty);
    });
  });

  group('topic ends / finish', () {
    testWidgets('finish event, then the next item counts down', (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      r.c.onTopicPosition(760);
      r.c.onTopicEnded();
      expect(r.events, ['start:1@0', 'finish:1@760']);
      expect(r.c.mode, OtwMode.countdown);
      expect(r.c.item!.segmentId, 3);
      r.dispose(); // a live countdown timer must not outlive the test
    });

    testWidgets('after the last item finishes: silence', (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      for (final seg in [1, 3, 2, 4]) {
        await t.pump(const Duration(seconds: 5));
        expect(r.c.item!.segmentId, seg);
        r.c.onTopicEnded();
      }
      expect(r.c.mode, OtwMode.quiet);
    });

    testWidgets('audio that cannot play falls to silence without an event',
        (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      r.c.onTopicFailed();
      expect(r.c.mode, OtwMode.quiet);
      expect(r.events, ['start:1@0']);
    });
  });

  group('menu (item 4)', () {
    testWidgets('choose plays that item and reports choose then start',
        (t) async {
      final r = Rig(autoPlay: false);
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      r.c.choose(2); // segment 2
      expect(r.c.mode, OtwMode.topic);
      expect(r.c.item!.segmentId, 2);
      expect(r.events, ['choose:2@0', 'start:2@0']);
    });

    test('Quiet stops the topic and stays quiet', () {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      r.c.choose(0);
      r.c.chooseQuiet();
      expect(r.c.mode, OtwMode.quiet);
      expect(r.audio.calls.last, startsWith('fade'));
    });

    test('"Play a topic" in silence starts the default, one tap', () {
      final r = Rig(autoPlay: false);
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      r.c.playTopic();
      expect(r.c.mode, OtwMode.topic);
      expect(r.c.item!.segmentId, 1);
      expect(r.events, ['start:1@0']);
    });

    test('choose during a stop is refused', () {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.choose(0);
      expect(r.c.mode, OtwMode.stop);
    });
  });

  group('arrival (item 5)', () {
    testWidgets('no sentence timestamps: fade at once, play the stop',
        (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      r.c.onTopicPosition(95);
      r.c.onArrival(1);
      await t.pump();
      expect(r.audio.calls.last, 'fade:600');
      expect(r.stopsPlayed, [1]);
      expect(r.c.mode, OtwMode.stop);
      expect(r.c.stopNumber, 2);
      // Interrupted, not skipped: no skip event is sent for it.
      expect(r.events.where((e) => e.startsWith('skip')), isEmpty);
    });

    testWidgets('with sentence timestamps: waits for the end of the sentence',
        (t) async {
      final plan = FillingsPlan.parse([
        {
          'leg': 0, 'after_stop': 1, 'minutes': 30,
          'items': [
            {
              'segment_id': 9, 'title': 'T', 'theme': 'history', 'minutes': 12,
              'audio_url': 'http://x/a.mp3', 'credit_line': 'c',
              'sentence_ends': [10.0, 19.5, 31.0],
            }
          ]
        }
      ]);
      final r = Rig(plan: plan);
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      r.c.onTopicPosition(12.0); // inside the 12.0..19.5 sentence
      r.c.onArrival(1);
      await t.pump(const Duration(seconds: 6));
      expect(r.c.arriving, isTrue);
      expect(r.stopsPlayed, isEmpty); // still finishing the sentence
      await t.pump(const Duration(milliseconds: 1600));
      expect(r.stopsPlayed, [1]);
      expect(r.c.mode, OtwMode.stop);
    });

    testWidgets('resume is offered on the NEXT leg, and plays from where it stopped',
        (t) async {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      await t.pump(const Duration(seconds: 5));
      r.c.onTopicPosition(95);
      r.c.onArrival(1);
      await t.pump();
      expect(r.c.resume!.item.segmentId, 1);
      expect(r.c.resume!.positionSec, 95);
      // Stop 2 plays; the next leg (after stop 3) is a different leg.
      r.c.onStopStarted(1);
      r.c.onStopStarted(2);
      r.c.onStopFinished(2);
      expect(r.c.mode, OtwMode.countdown);
      expect(r.c.resume, isNotNull); // "Resume <topic> later" visible here
      r.c.resumeLater();
      expect(r.c.mode, OtwMode.topic);
      expect(r.c.item!.segmentId, 1);
      expect(r.audio.lastStart, 95);
      expect(r.c.resume, isNull);
    });

    test('arrival during countdown or quiet just plays the stop', () {
      final r = Rig(autoPlay: false);
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onStopFinished(0);
      r.c.onArrival(1);
      expect(r.stopsPlayed, [1]);
      expect(r.c.mode, OtwMode.stop);
      expect(r.c.resume, isNull);
    });

    test('arrival while at a stop is ignored (the page owns it)', () {
      final r = Rig();
      addTearDown(r.dispose);
      r.c.onStopStarted(0);
      r.c.onArrival(1);
      expect(r.stopsPlayed, isEmpty);
    });
  });

  group('page hold list', () {
    test('only stops that are followed by a leg of topics are held', () {
      final r = Rig();
      addTearDown(r.dispose);
      expect(r.c.holdAfterStops, [0, 2]);
    });
  });
}
