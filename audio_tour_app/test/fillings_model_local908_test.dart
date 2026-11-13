import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:audio_tour_app_dev/services/fillings_model.dart';
import 'package:audio_tour_app_dev/services/on_the_way_js.dart';
import 'package:audio_tour_app_dev/services/stop_proximity.dart';
import 'package:audio_tour_app_dev/services/webview_topic_audio.dart';

import 'otw_test_support.dart';

void main() {
  group('907 payload fixture', () {
    test('parses legs, items and the 0-/1-based leg numbering', () {
      final p = loadFixturePlan();
      expect(p.legs.map((l) => [l.leg, l.afterStop]), [
        [0, 1],
        [2, 3]
      ]);
      expect(p.legAfterStop(1)!.items.length, 4);
      expect(p.legAfterStop(2), isNull);
      expect(p.legAfterStop(1)!.items.first.segmentId, 1); // default first
      expect(p.legAfterStop(1)!.minutesLabel, '~40 min');
      expect(p.legAfterStop(1)!.items.first.minutesLabel, 13);
      expect(p.legAfterStop(1)!.items.first.themeLabel, 'History');
      expect(p.legAfterStop(3)!.items.last.themeLabel, 'Legends');
    });

    test('an item without audio (audio_url null) is not offered', () {
      final p = FillingsPlan.parse([
        {
          'leg': 0, 'after_stop': 1, 'minutes': 30,
          'items': [
            {'segment_id': 1, 'title': 'A', 'theme': 'x', 'minutes': 5, 'audio_url': null, 'credit_line': ''},
            {'segment_id': 2, 'title': 'B', 'theme': 'x', 'minutes': 5, 'audio_url': '/t/b.mp3', 'credit_line': ''},
          ]
        }
      ]);
      expect(p.legs.single.items.map((i) => i.segmentId), [2]);
    });

    test('garbage never throws', () {
      for (final j in [null, 5, 'x', [], {}, {'fillings': 'no'}, [1, 2], [{'items': 3}]]) {
        expect(FillingsPlan.parse(j).isEmpty, isTrue, reason: '$j');
      }
    });
  });

  group('old payloads (item 8)', () {
    test('a payload with no fillings key parses to an empty plan', () {
      expect(
          FillingsPlan.parse({'job_id': 'j', 'status': 'completed', 'total_stops': 2})
              .isEmpty,
          isTrue);
    });

    test('loadFromTourDir: no file / old tour.json => empty; with fillings => plan',
        () async {
      final d = await Directory.systemTemp.createTemp('otw908');
      addTearDown(() => d.delete(recursive: true));
      expect((await FillingsPlan.loadFromTourDir(d.path)).isEmpty, isTrue);
      File('${d.path}/tour.json').writeAsStringSync(jsonEncode({'stops': [{}, {}]}));
      expect((await FillingsPlan.loadFromTourDir(d.path)).isEmpty, isTrue);
      File('${d.path}/fillings.json').writeAsStringSync(
          File('test/fixtures/fillings_local907.json').readAsStringSync());
      expect((await FillingsPlan.loadFromTourDir(d.path)).legs.length, 2);
      File('${d.path}/fillings.json').writeAsStringSync('{not json');
      expect((await FillingsPlan.loadFromTourDir(d.path)).isEmpty, isTrue);
    });
  });

  group('credits / sources (item 6)', () {
    test('sourcesUrl: explicit source > URL in the credit line > none', () {
      FillingItem it(Map<String, dynamic> extra) => FillingItem.tryParse({
            'segment_id': 1, 'title': 'T', 'theme': 'h', 'minutes': 5,
            'audio_url': '/a.mp3', 'credit_line': 'Based on Wikipedia.',
            ...extra
          })!;
      expect(it({}).sourcesUrl, isNull); // 907 sends no URL today
      expect(it({'credit_line': 'See https://en.wikipedia.org/wiki/X (CC BY-SA)'}).sourcesUrl,
          'https://en.wikipedia.org/wiki/X');
      expect(it({'source_url': 'https://example.org/s'}).sourcesUrl,
          'https://example.org/s');
      expect(
          it({'sources': [{'title': 'x', 'url': 'https://a.b/c'}], 'source_url': 'https://z'})
              .sourcesUrl,
          'https://a.b/c');
    });
  });

  group('audio url', () {
    test('relative 907 urls join the base; absolute urls pass through', () {
      expect(joinTopicAudioUrl('https://api.x', '/topic-audio/a1.mp3'),
          'https://api.x/topic-audio/a1.mp3');
      expect(joinTopicAudioUrl('https://api.x/', 'topic-audio/a1.mp3'),
          'https://api.x/topic-audio/a1.mp3');
      expect(joinTopicAudioUrl('https://api.x', 'https://cdn/y.mp3'),
          'https://cdn/y.mp3');
    });
  });

  group('page bridge', () {
    test('holds only listed stops, re-emits the listened event, and registers '
        'media next only on request', () {
      expect(kOnTheWayJs, contains("document.addEventListener('ended'"));
      expect(kOnTheWayJs, contains('stopImmediatePropagation'));
      expect(kOnTheWayJs, contains("'onPlaybackEvent'"));
      expect(kOnTheWayJs, contains("'onStopEnded'"));
      expect(kOnTheWayJs, contains("setActionHandler('nexttrack'"));
      expect(kOnTheWayJs, contains('on ? function () { cb(\'onMediaNext\'); } : null'));
      expect(kOnTheWayJs, contains('new Audio()')); // detached: stop indexes untouched
      expect(kOnTheWayJs, contains('fadeOut'));
    });
  });

  group('proximity', () {
    test('fires once per approach, re-arms only after leaving', () {
      final d = StopProximityDetector(const [
        StopCoord(0, 42.3601, -71.0589),
        StopCoord(1, 42.3700, -71.0589),
      ]);
      expect(d.onPosition(42.3650, -71.0589), isEmpty); // far from both
      expect(d.onPosition(42.37005, -71.0589), [1]); // ~5 m from stop 2
      expect(d.onPosition(42.37010, -71.0589), isEmpty); // jitter: no repeat
      expect(d.onPosition(42.3705, -71.0589), isEmpty); // ~55 m: still inside exit ring
      expect(d.onPosition(42.3650, -71.0589), isEmpty); // left
      expect(d.onPosition(42.37005, -71.0589), [1]); // approached again
    });

    test('haversine is about right', () {
      expect(haversineMetres(42.0, -71.0, 42.001, -71.0), closeTo(111.2, 1));
    });

    test('stop coordinates are read from audio_N.txt (1-based) like the map',
        () async {
      final d = await Directory.systemTemp.createTemp('otw908c');
      addTearDown(() => d.delete(recursive: true));
      File('${d.path}/audio_1.txt').writeAsStringSync('Old Fort\nCoordinates: 42.3601, -71.0589\n');
      File('${d.path}/audio_2.txt').writeAsStringSync('Harbour\nCoordinates: 42.37, -71.05\n');
      final c = await StopProximityDetector.loadFromTourDir(d.path);
      expect(c.map((s) => s.index), [0, 1]);
      expect(c.last.lat, 42.37);
    });
  });
}
