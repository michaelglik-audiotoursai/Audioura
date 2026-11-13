// [LOCAL-907E] Topic audio on the phone: downloaded with the tour, failed items hidden, local file
// preferred, and the bottom bar says "Topic · <title>" while a topic plays.
import 'dart:convert';
import 'dart:io';

import 'package:audio_tour_app_dev/services/fillings_model.dart';
import 'package:audio_tour_app_dev/services/on_the_way_controller.dart';
import 'package:audio_tour_app_dev/services/topic_audio_downloader.dart';
import 'package:audio_tour_app_dev/widgets/swipe_feedback_widget.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'otw_test_support.dart';

Map<String, dynamic> item(int id) => {
      'segment_id': id,
      'title': 'Topic $id',
      'theme': 'history',
      'minutes': 10.0,
      'audio_url': '/topic-audio/r/en/segment_$id.mp3',
      'credit_line': 'CC BY-SA',
      'language': 'en',
      'sources': [
        {'title': 'Boston', 'url': 'https://en.wikipedia.org/wiki/Boston'}
      ],
      'source_url': 'https://en.wikipedia.org/wiki/Boston',
      'sentence_ends': [2.5, 6.0],
    };

Directory tourDir() {
  final d = Directory.systemTemp.createTempSync('local907e');
  File('${d.path}/fillings.json').writeAsStringSync(jsonEncode({
    'fillings': [
      {
        'leg': 0,
        'after_stop': 1,
        'minutes': 30,
        'items': [item(1), item(2)]
      }
    ]
  }));
  return d;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('every fillings item is downloaded into the tour folder', () async {
    final d = tourDir();
    addTearDown(() => d.deleteSync(recursive: true));
    final urls = <String>[];
    final failed = await TopicAudioDownloader.downloadForTour(d.path,
        baseUrl: () async => 'http://host:5005',
        fetch: (u) async {
          urls.add(u);
          return [1, 2, 3];
        });
    expect(failed, isEmpty);
    expect(urls, [
      'http://host:5005/topic-audio/r/en/segment_1.mp3',
      'http://host:5005/topic-audio/r/en/segment_2.mp3',
    ]);
    expect(File('${d.path}/topic_1.mp3').readAsBytesSync(), [1, 2, 3]);
    expect(File('${d.path}/topic_2.mp3').existsSync(), isTrue);
    final plan = await TopicAudioDownloader.applyLocal(
        await FillingsPlan.loadFromTourDir(d.path), d.path);
    final it = plan.legs.single.items.first;
    expect(it.audioUrl, startsWith('file://'));
    expect(it.audioUrl, endsWith('/topic_1.mp3'));
    expect(it.sentenceEnds, [2.5, 6.0]);
    expect(it.sourcesUrl, 'https://en.wikipedia.org/wiki/Boston');
  });

  test('a failed item is hidden; the other still plays; nothing throws', () async {
    final d = tourDir();
    addTearDown(() => d.deleteSync(recursive: true));
    final failed = await TopicAudioDownloader.downloadForTour(d.path,
        baseUrl: () async => 'http://host',
        fetch: (u) async => u.contains('segment_1') ? null : [9]);
    expect(failed, [1]);
    expect(File('${d.path}/topic_1.mp3').existsSync(), isFalse);
    final plan = await TopicAudioDownloader.applyLocal(
        await FillingsPlan.loadFromTourDir(d.path), d.path);
    expect(plan.legs.single.items.map((i) => i.segmentId), [2]);
  });

  test('all items failing leaves an empty plan (player behaves as before)', () async {
    final d = tourDir();
    addTearDown(() => d.deleteSync(recursive: true));
    await TopicAudioDownloader.downloadForTour(d.path,
        baseUrl: () async => 'http://host', fetch: (u) async => throw Exception('offline'));
    final plan = await TopicAudioDownloader.applyLocal(
        await FillingsPlan.loadFromTourDir(d.path), d.path);
    expect(plan.isEmpty, isTrue);
  });

  test('no fillings.json: nothing downloaded, no status file', () async {
    final d = Directory.systemTemp.createTempSync('local907e_none');
    addTearDown(() => d.deleteSync(recursive: true));
    var calls = 0;
    final failed = await TopicAudioDownloader.downloadForTour(d.path,
        baseUrl: () async => 'http://host',
        fetch: (u) async {
          calls++;
          return [1];
        });
    expect(failed, isEmpty);
    expect(calls, 0);
    expect(File('${d.path}/${TopicAudioDownloader.statusFile}').existsSync(), isFalse);
  });

  test('before any download the item keeps its server URL', () async {
    final d = tourDir();
    addTearDown(() => d.deleteSync(recursive: true));
    final plan = await TopicAudioDownloader.applyLocal(
        await FillingsPlan.loadFromTourDir(d.path), d.path);
    expect(plan.legs.single.items.first.audioUrl, '/topic-audio/r/en/segment_1.mp3');
  });

  testWidgets('bottom bar: "Topic · <title>" during a topic, the stop again after', (t) async {
    final r = Rig();
    addTearDown(r.dispose);
    r.c.onStopStarted(0);
    Widget bar() => MaterialApp(
          home: Scaffold(
            body: ListenableBuilder(
              listenable: r.c,
              builder: (_, __) => SwipeFeedbackWidget(
                currentStopIndex: 0,
                tourId: '1',
                tourPath: '/nonexistent',
                stopName: 'Old Fort',
                topicTitle: r.c.mode == OtwMode.topic ? r.c.item?.title : null,
              ),
            ),
          ),
        );
    String label() => (t.widget(find.byKey(const ValueKey('swipe_label'))) as Text).data!;

    await t.pumpWidget(bar());
    expect(label(), 'This stop: Old Fort');

    r.c.onStopFinished(0);
    await t.pump(const Duration(seconds: 5));
    expect(r.c.mode, OtwMode.topic);
    expect(label(), 'Topic · ${r.c.item!.title}');
    expect(find.textContaining('This stop'), findsNothing);

    r.c.onStopStarted(1);
    await t.pump();
    expect(r.c.mode, OtwMode.stop);
    expect(label(), 'This stop: Old Fort');
  });

  test('label helper', () {
    expect(SwipeFeedbackWidget.labelFor(topicTitle: 'X'), 'Topic · X');
    expect(SwipeFeedbackWidget.labelFor(stopName: ' '), 'This stop:');
    expect(SwipeFeedbackWidget.labelFor(topicTitle: '  ', stopName: 'A'), 'This stop: A');
  });
}
