import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/services/fillings_model.dart';
import 'package:audio_tour_app_dev/services/on_the_way_controller.dart';
import 'package:audio_tour_app_dev/widgets/on_the_way_panel.dart';

import 'otw_test_support.dart';

Widget host(Rig r, {List<String>? opened, List<String>? links}) => MaterialApp(
      home: Scaffold(
        body: Column(children: [
          OnTheWayPanel(
            controller: r.c,
            onOpenMenu: () => opened?.add('menu'),
            onOpenSources: (u) => links?.add(u),
          ),
        ]),
      ),
    );

String headline(WidgetTester t) =>
    (t.widget(find.byKey(kOtwHeadlineKey)) as Text).data!;

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('STATE 1 — at a stop: "Stop 3 of 8 · <title>"', (t) async {
    final r = Rig(totalStops: 8);
    addTearDown(r.dispose);
    r.c.onStopStarted(2);
    await t.pumpWidget(host(r));
    expect(headline(t), 'Stop 3 of 8 · Market');
    expect(find.byKey(kOtwOptionalBadgeKey), findsNothing);
    expect(find.byKey(kOtwNowKey), findsNothing);
  });

  testWidgets('STATE 2 — on the way, topic playing: headline, Now line, Optional badge, credit',
      (t) async {
    final links = <String>[];
    final r = Rig();
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r, links: links));
    await t.pump(const Duration(seconds: 5));
    expect(headline(t), 'On the way to Stop 2 · ~40 min');
    expect((t.widget(find.byKey(kOtwNowKey)) as Text).data,
        'Now: The harbour that built the town · 13 min · History');
    expect(find.byKey(kOtwOptionalBadgeKey), findsOneWidget);
    expect(find.text('Optional'), findsOneWidget);
    // The credit line is shown under the title (907's payload carries no URL, so
    // there is no Sources link to show for it).
    expect(find.byKey(kOtwCreditKey), findsOneWidget);
    expect(find.textContaining('Wikipedia'), findsOneWidget);
    expect(find.byKey(kOtwSourcesKey), findsNothing);
    // Visually distinct from the stop state.
    final bg = (t.widget(find.byKey(kOtwPanelKey)) as Material).color;
    expect(bg, kOtwWayColor);
    expect(bg, isNot(kOtwStopColor));
  });

  testWidgets('credit line with a URL gets a Sources link that opens it',
      (t) async {
    final links = <String>[];
    final plan = FillingsPlan.parse([
      {
        'leg': 0, 'after_stop': 1, 'minutes': 30,
        'items': [
          {
            'segment_id': 9, 'title': 'T', 'theme': 'history', 'minutes': 12,
            'audio_url': 'http://x/a.mp3',
            'credit_line': 'Based on Wikipedia, CC BY-SA.',
            'sources': [
              {'title': 'Boston', 'url': 'https://en.wikipedia.org/wiki/Boston'}
            ],
          }
        ]
      }
    ]);
    final r = Rig(plan: plan);
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r, links: links));
    await t.pump(const Duration(seconds: 5));
    await t.tap(find.byKey(kOtwSourcesKey));
    expect(links, ['https://en.wikipedia.org/wiki/Boston']);
  });

  testWidgets('countdown: "Next: <title> — Skip", Skip works', (t) async {
    final r = Rig();
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r));
    expect((t.widget(find.byKey(kOtwNowKey)) as Text).data,
        'Next: The harbour that built the town — Skip');
    expect(find.text('Starts in 5 s'), findsOneWidget);
    await t.tap(find.byKey(kOtwSkipKey));
    await t.pump();
    expect((t.widget(find.byKey(kOtwNowKey)) as Text).data,
        startsWith('Next: Marsh, tide and shore birds'));
    r.dispose();
  });

  testWidgets('STATE 3 — silence: "…· quiet" and a one-tap "Play a topic"',
      (t) async {
    final r = Rig(autoPlay: false);
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r));
    expect(headline(t), 'On the way to Stop 2 · quiet');
    expect(find.byKey(kOtwNowKey), findsNothing);
    expect(find.byKey(kOtwPlayTopicKey), findsOneWidget);
    // Large target for driving.
    expect(t.getSize(find.byKey(kOtwPlayTopicKey)).height, greaterThanOrEqualTo(56));
    await t.tap(find.byKey(kOtwPlayTopicKey));
    await t.pump();
    expect(r.c.mode, OtwMode.topic);
    expect(find.byKey(kOtwOptionalBadgeKey), findsOneWidget);
  });

  testWidgets('STATE 4 — menu: items with title, minutes, theme, ▶ each, Quiet',
      (t) async {
    final r = Rig(autoPlay: false);
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(MaterialApp(
        home: Scaffold(body: OnTheWaySheet(controller: r.c))));
    expect(find.text('On the way to Stop 2 · ~40 min'), findsOneWidget);
    for (var i = 0; i < 4; i++) {
      expect(find.byKey(ValueKey('otw_row_$i')), findsOneWidget);
      expect(find.byKey(ValueKey('otw_play_$i')), findsOneWidget);
    }
    expect(find.text('Marsh, tide and shore birds'), findsOneWidget);
    expect(find.text('9 min · Nature'), findsOneWidget);
    expect(find.byKey(kOtwQuietKey), findsOneWidget);
    // ▶ on the third item plays it and reports choose + start.
    await t.tap(find.byKey(const ValueKey('otw_play_2')));
    await t.pump();
    expect(r.c.item!.segmentId, 2);
    expect(r.events, ['choose:2@0', 'start:2@0']);
    // Quiet.
    await t.tap(find.byKey(kOtwQuietKey));
    await t.pump();
    expect(r.c.mode, OtwMode.quiet);
  });

  testWidgets('menu settings: auto-play and always-quiet switches', (t) async {
    final r = Rig();
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    await t.pumpWidget(MaterialApp(
        home: Scaffold(body: OnTheWaySheet(controller: r.c))));
    expect(r.settings.autoPlay, isTrue);
    await t.tap(find.byKey(kOtwAutoPlayKey));
    await t.pump();
    expect(r.settings.autoPlay, isFalse);
    await t.tap(find.byKey(kOtwAlwaysQuietKey));
    await t.pump();
    expect(r.settings.alwaysQuiet, isTrue);
    // At a stop the sheet only previews the next leg: no ▶ yet.
    expect(find.byKey(const ValueKey('otw_play_0')), findsNothing);
  });

  testWidgets('arrival interruption: "Arriving…" while the sentence ends, then the stop',
      (t) async {
    final plan = FillingsPlan.parse([
      {
        'leg': 0, 'after_stop': 1, 'minutes': 30,
        'items': [
          {
            'segment_id': 9, 'title': 'Long topic', 'theme': 'history',
            'minutes': 12, 'audio_url': 'http://x/a.mp3', 'credit_line': 'c',
            'sentence_ends': [30.0],
          }
        ]
      }
    ]);
    final r = Rig(plan: plan);
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r));
    await t.pump(const Duration(seconds: 5));
    r.c.onTopicPosition(26);
    r.c.onArrival(1);
    await t.pump();
    expect(find.byKey(kOtwArrivingKey), findsOneWidget);
    await t.pump(const Duration(seconds: 5));
    await t.pump(const Duration(seconds: 1));
    expect(headline(t), 'Stop 2 of 4 · Harbour');
    expect(r.stopsPlayed, [1]);
    expect(find.byKey(kOtwOptionalBadgeKey), findsNothing);
  });

  testWidgets('resume: "Resume <topic> later" shows on the next leg and works',
      (t) async {
    final r = Rig();
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r));
    await t.pump(const Duration(seconds: 5));
    r.c.onTopicPosition(95);
    r.c.onArrival(1);
    await t.pump();
    // At the stop: not shown yet.
    expect(find.byKey(kOtwResumeKey), findsNothing);
    r.c.onStopStarted(2);
    r.c.onStopFinished(2);
    await t.pump();
    expect(headline(t), 'On the way to Stop 4 · ~35 min');
    expect(find.text('Resume The harbour that built the town later'),
        findsOneWidget);
    await t.tap(find.byKey(kOtwResumeKey));
    await t.pump();
    expect(r.c.mode, OtwMode.topic);
    expect(r.audio.lastStart, 95);
    expect(find.byKey(kOtwResumeKey), findsNothing);
  });

  testWidgets('OLD PAYLOAD: a tour without fillings shows no change',
      (t) async {
    final r = Rig(plan: FillingsPlan.parse({'job_id': 'j', 'status': 'completed'}));
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    r.c.onStopFinished(0);
    await t.pumpWidget(host(r));
    expect(find.byKey(kOtwPanelKey), findsNothing);
    expect(find.byType(Text), findsNothing);
    expect(r.c.mode, OtwMode.stop);
    expect(r.c.mediaNext, MediaNextAction.nextStop);
    expect(r.c.holdAfterStops, isEmpty);
  });

  testWidgets('"always quiet" renders nothing, even with fillings', (t) async {
    final r = Rig(alwaysQuiet: true);
    addTearDown(r.dispose);
    await t.pumpWidget(host(r));
    expect(find.byKey(kOtwPanelKey), findsNothing);
  });

  testWidgets('translations: English-only topics hidden by default, noticed when kept',
      (t) async {
    final raw = [
      {
        'leg': 0, 'after_stop': 1, 'minutes': 30,
        'items': [
          {
            'segment_id': 9, 'title': 'English topic', 'theme': 'history',
            'minutes': 12, 'audio_url': 'http://x/a.mp3', 'credit_line': 'c',
            'language': 'en',
          }
        ]
      }
    ];
    // Default (hide): a Russian tour gets no topic section at all.
    final hidden = FillingsPlan.parse(raw).forLanguage('ru', keepForeign: false);
    expect(hidden.isEmpty, isTrue);
    final rh = Rig(plan: hidden, tourLanguage: 'ru');
    addTearDown(rh.dispose);
    await t.pumpWidget(host(rh));
    expect(find.byKey(kOtwPanelKey), findsNothing);

    // Setting on: kept, playable, with the notice.
    final kept = FillingsPlan.parse(raw).forLanguage('ru', keepForeign: true);
    final rk = Rig(plan: kept, tourLanguage: 'ru', showEnglishNotice: true, autoPlay: false);
    addTearDown(rk.dispose);
    rk.c.onStopStarted(0);
    rk.c.onStopFinished(0);
    await t.pumpWidget(host(rk));
    expect(find.text('Topics available in English'), findsOneWidget);
    // An English tour never shows the notice.
    final re = Rig(plan: kept, tourLanguage: 'en', showEnglishNotice: true, autoPlay: false);
    addTearDown(re.dispose);
    re.c.onStopStarted(0);
    re.c.onStopFinished(0);
    await t.pumpWidget(host(re));
    expect(find.text('Topics available in English'), findsNothing);
  });
}
