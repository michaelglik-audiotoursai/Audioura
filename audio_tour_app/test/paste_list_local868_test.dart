// LOCAL-868 (D762, app side) — "Paste a list of places" + Share → Audioura.
//
// Covers, offline:
//   1. the /preview-stops request payload ({text, city}) and its error mapping;
//   2. parsing the preview (resolved + unresolved stops);
//   3. delete and drag-reorder, in the pure helpers and in the real widget
//      (list order AND numbered pins follow);
//   4. the generate payload shape: user_stops OBJECTS {name, lat, lng,
//      resolved_name}, total_stops == count, driven through the REAL
//      TourGeneratorScreen; a hand-built list stays plain strings;
//   5. shared text reaching the paste box (the Share → Audioura hand-off).

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/screens/paste_list_screen.dart';
import 'package:audio_tour_app_dev/screens/tour_generator_screen.dart';
import 'package:audio_tour_app_dev/services/preview_stops_service.dart';
import 'package:audio_tour_app_dev/services/shared_text_service.dart';
import 'package:audio_tour_app_dev/utils/pasted_list.dart';
import 'package:audio_tour_app_dev/utils/user_stops.dart';

const String kMichael = 'Cathedral → Post Office → Book Street → '
    'Independence Palace → War Remnants Museum → Opera House/Đồng Khởi → '
    'City Hall & Nguyễn Huệ → Café Apartments 42 → '
    'Bạch Đằng Pier (tour-bus + waterbus) → Thi Bar';

/// The shape `/preview-stops` returns for Michael's list (names as in
/// SUBMISSION_LOCAL-867.md; coordinates are fixtures near each place).
Map<String, dynamic> previewFixture({int unresolvedIndex = -1}) {
  const rows = <List<Object?>>[
    ['Cathedral', 'Notre-Dame Cathedral Basilica of Saigon', 10.7798, 106.6990, 'high', null],
    ['Post Office', 'Saigon Central Post Office', 10.7799, 106.6999, 'high', null],
    ['Book Street', 'Nguyễn Văn Bình Book Street', 10.7803, 106.6997, 'medium', null],
    ['Independence Palace', 'Independence Palace', 10.7770, 106.6953, 'high', null],
    ['War Remnants Museum', 'War Remnants Museum', 10.7794, 106.6922, 'high', null],
    ['Opera House', 'Saigon Opera House', 10.7766, 106.7032, 'high', null],
    ['City Hall', 'Ho Chi Minh City Hall', 10.7765, 106.7020, 'high', null],
    ['Café Apartments 42', 'Café Apartments, 42 Nguyễn Huệ', 10.7742, 106.7046, 'medium', null],
    ['Bạch Đằng Pier', 'Bạch Đằng Pier', 10.7728, 106.7067, 'medium', 'tour-bus + waterbus'],
    ['Thi Bar', 'Thi Bar Saigon', 10.7716, 106.7040, 'medium', null],
  ];
  final stops = <Map<String, dynamic>>[];
  for (var i = 0; i < rows.length; i++) {
    final r = rows[i];
    if (i == unresolvedIndex) {
      stops.add({
        'index': i,
        'name': r[0],
        'stop_name': r[0],
        'alt_names': [],
        'note': r[5],
        'url': null,
        'resolved_name': null,
        'matched_name': null,
        'lat': null,
        'lng': null,
        'source': null,
        'confidence': null,
        'unresolved': true,
        'reason': 'no match in the city',
      });
      continue;
    }
    stops.add({
      'index': i,
      'name': r[0],
      'stop_name': r[0],
      'alt_names': [],
      'note': r[5],
      'url': null,
      'resolved_name': r[1],
      'matched_name': r[1],
      'lat': r[2],
      'lng': r[3],
      'source': 'wikidata',
      'confidence': r[4],
      'unresolved': false,
    });
  }
  return {
    'ok': true,
    'city': {'name': 'Ho Chi Minh City', 'lat': 10.7769, 'lng': 106.7009},
    'count': stops.length,
    'unresolved_count': unresolvedIndex >= 0 ? 1 : 0,
    'stops': stops,
    'cost': {'llm_calls': 0, 'usd': 0.004},
  };
}

http.Response jsonResp(Object body, [int code = 200]) => http.Response(
    jsonEncode(body), code,
    headers: {'content-type': 'application/json; charset=utf-8'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'server_mode': 'local',
      'server_ip': '127.0.0.1',
      'app_mode': 'Tours',
      'user_id': 'local868_test',
      'narrative_tone': 'general',
    });
    PendingSharedText.instance.consume();
  });

  group('preview request + parsing', () {
    test('the preview call sends {text, city} and nothing else', () async {
      Map<String, dynamic>? sent;
      final r = await PreviewStopsService.preview(
        '  $kMichael  ',
        ' Ho Chi Minh City ',
        post: (body) async {
          sent = body;
          return jsonResp(previewFixture());
        },
      );
      expect(sent, {'text': kMichael, 'city': 'Ho Chi Minh City'});
      expect(r.stops.length, 10);
      expect(r.cityName, 'Ho Chi Minh City');
    });

    test('parses resolved and unresolved stops in order', () {
      final r = parsePreviewResponse(previewFixture(unresolvedIndex: 8));
      expect(r.stops.map((s) => s.stopName).first, 'Cathedral');
      expect(r.stops[2].resolvedName, 'Nguyễn Văn Bình Book Street');
      expect(r.stops[2].confidence, 'medium');
      expect(r.stops[8].hasPin, isFalse);
      expect(r.stops[8].unresolved, isTrue);
      expect(r.stops[8].lat, isNull);
      expect(r.unresolvedCount, 1);
      expect(confidenceLabel(r.stops[0]), 'high confidence');
      expect(confidenceLabel(r.stops[8]), 'no pin');
    });

    test('blank text / too long are refused before any request', () async {
      var calls = 0;
      Future<http.Response> post(Map<String, dynamic> b) async {
        calls++;
        return jsonResp({});
      }

      await expectLater(PreviewStopsService.preview('   ', 'HCMC', post: post),
          throwsA(isA<PreviewStopsException>()));
      await expectLater(
          PreviewStopsService.preview('x' * (kMaxPasteChars + 1), 'HCMC',
              post: post),
          throwsA(isA<PreviewStopsException>()));
      expect(calls, 0);
    });

    test('server 400 (no city) and 404 (feature off) become plain messages',
        () async {
      await expectLater(
        PreviewStopsService.preview('A → B', '',
            post: (_) async => jsonResp(
                {'error': "no city: pass 'city' or name it in the text"}, 400)),
        throwsA(isA<PreviewStopsException>()
            .having((e) => e.message, 'message', contains('city'))),
      );
      await expectLater(
        PreviewStopsService.preview('A → B', 'Hue',
            post: (_) async => jsonResp(
                {'error': 'itinerary import is not enabled on this deploy'},
                404)),
        throwsA(isA<PreviewStopsException>()
            .having((e) => e.message, 'message', contains('not available'))),
      );
    });

    test('city helpers: request text and Nominatim reverse', () {
      expect(cityFromRequestText('walking tour for Ho Chi Minh City'),
          'Ho Chi Minh City');
      expect(cityFromRequestText('Hue'), 'Hue');
      expect(cityFromRequestText('  '), '');
      expect(
          cityFromNominatimReverse({
            'address': {'city': 'Ho Chi Minh City', 'country': 'Vietnam'}
          }),
          'Ho Chi Minh City');
      expect(cityFromNominatimReverse({'address': {'country': 'Vietnam'}}),
          isNull);
    });
  });

  group('delete + reorder (pure)', () {
    test('delete removes, reorder moves with the onReorder index rule', () {
      final stops = parsePreviewResponse(previewFixture()).stops;
      removePreviewStopAt(stops, 1); // Post Office
      expect(stops.length, 9);
      expect(stops[1].stopName, 'Book Street');
      // Drag Cathedral (0) below Book Street: onReorder(0, 2) -> index 1.
      reorderPreviewStops(stops, 0, 2);
      expect(stops.map((s) => s.stopName).take(3).toList(),
          ['Book Street', 'Cathedral', 'Independence Palace']);
      // Out of range is a no-op.
      removePreviewStopAt(stops, 99);
      expect(stops.length, 9);
    });
  });

  group('generate payload shape', () {
    test('pasted list -> OBJECTS {name, lat, lng, resolved_name}, in order', () {
      final stops = previewStopsToUserStops(
          parsePreviewResponse(previewFixture(unresolvedIndex: 8)).stops);
      final out = userStopsForGeneration(stops);
      expect(out.length, 10);
      expect(out.every((e) => e is Map), isTrue);
      final first = out.first as Map<String, dynamic>;
      expect(first['name'], 'Cathedral');
      expect(first['lat'], 10.7798);
      expect(first['lng'], 106.6990);
      expect(first['resolved_name'], 'Notre-Dame Cathedral Basilica of Saigon');
      // Unresolved: just the name — the server finds it by name.
      final pier = out[8] as Map<String, dynamic>;
      expect(pier['name'], 'Bạch Đằng Pier');
      expect(pier.containsKey('lat'), isFalse);
      expect(pier.containsKey('lng'), isFalse);
      // The same list is valid for the existing review/generate checks.
      expect(isStopListReady(stops), isTrue);
      expect(stops.last['stop_number'], 10);
    });

    test('a hand-built list is still the plain string list', () {
      final stops = <Map<String, dynamic>>[];
      addStop(stops, 'The harbour');
      addStop(stops, 'The lighthouse');
      expect(userStopsForGeneration(stops), ['The harbour', 'The lighthouse']);
    });

    test('a pasted list in ONE own-stop field stays supported (workaround)', () {
      // The old path: the whole list typed into "Stop name or description".
      final stops = <Map<String, dynamic>>[];
      addStop(stops, kMichael);
      expect(userStopsForGeneration(stops), [kMichael]);
    });
  });

  group('paste box widget', () {
    Future<void> pumpBox(
      WidgetTester tester, {
      String? initialText,
      String? initialCity,
      required PreviewPoster post,
      CityLocator? locate,
      void Function(PastedListResult?)? onResult,
    }) async {
      await tester.binding.setSurfaceSize(const Size(900, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: ElevatedButton(
              onPressed: () async {
                final r = await Navigator.push<PastedListResult>(
                  context,
                  MaterialPageRoute(
                    builder: (_) => PasteListScreen(
                      initialText: initialText,
                      initialCity: initialCity,
                      previewPost: post,
                      locateCity: locate ?? () async => null,
                      showTiles: false,
                    ),
                  ),
                );
                onResult?.call(r);
              },
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
    }

    testWidgets('shows the example hint and pre-fills the city', (tester) async {
      await pumpBox(tester,
          initialCity: 'Ho Chi Minh City', post: (_) async => jsonResp({}));
      expect(find.text('e.g. Cathedral → Post Office → Book Street'),
          findsOneWidget);
      final city = tester.widget<TextField>(find.byKey(kPasteCityKey));
      expect(city.controller!.text, 'Ho Chi Minh City');
    });

    testWidgets('city falls back to the current-location lookup', (tester) async {
      await pumpBox(tester,
          post: (_) async => jsonResp({}), locate: () async => 'Da Nang');
      final city = tester.widget<TextField>(find.byKey(kPasteCityKey));
      expect(city.controller!.text, 'Da Nang');
    });

    testWidgets(
        'preview lists 10 stops with chips + pins; unresolved is marked; '
        'delete and drag reorder update list and pins; Use pops the result',
        (tester) async {
      Map<String, dynamic>? sent;
      PastedListResult? result;
      await pumpBox(
        tester,
        initialText: kMichael,
        initialCity: 'Ho Chi Minh City',
        onResult: (r) => result = r,
        post: (b) async {
          sent = b;
          return jsonResp(previewFixture(unresolvedIndex: 8));
        },
      );
      await tester.tap(find.byKey(kPastePreviewButtonKey));
      await tester.pumpAndSettle();

      expect(sent, {'text': kMichael, 'city': 'Ho Chi Minh City'});
      expect(find.textContaining('visit these 10 stops'), findsOneWidget);
      // 9 pins on the map (one unresolved), numbered by list position.
      expect(find.byKey(const ValueKey('paste-pin-1')), findsOneWidget);
      expect(find.byKey(const ValueKey('paste-pin-9')), findsNothing);
      expect(find.byKey(const ValueKey('paste-pin-10')), findsOneWidget);
      // Chips, resolved names, the note, the unresolved marker.
      expect(find.text('high confidence'), findsWidgets);
      expect(find.text('medium confidence'), findsWidgets);
      expect(find.text('no pin'), findsOneWidget);
      expect(find.text("no pin, we'll find it by name"), findsOneWidget);
      expect(find.text('Found: Saigon Central Post Office'), findsOneWidget);
      expect(find.text('tour-bus + waterbus'), findsOneWidget);

      // Delete "Post Office" (stop 2).
      await tester.tap(find.byTooltip('Delete stop').at(1));
      await tester.pumpAndSettle();
      expect(find.textContaining('visit these 9 stops'), findsOneWidget);
      expect(find.text('Post Office'), findsNothing);
      expect(find.byKey(const ValueKey('paste-pin-10')), findsNothing);

      // Drag the first handle (Cathedral) below Book Street.
      final handle = find.byIcon(Icons.drag_handle).first;
      final g = await tester.startGesture(tester.getCenter(handle));
      await tester.pump(const Duration(milliseconds: 100));
      await g.moveBy(const Offset(0, 160));
      await tester.pump(const Duration(milliseconds: 100));
      await g.moveBy(const Offset(0, 20));
      await tester.pump(const Duration(milliseconds: 100));
      await g.up();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(kPasteUseButtonKey));
      await tester.pumpAndSettle();
      expect(result, isNotNull);
      final names = result!.stops.map((s) => s.stopName).toList();
      expect(names.length, 9);
      expect(names.contains('Post Office'), isFalse);
      expect(names.first, isNot('Cathedral')); // the drag moved it
      expect(names.indexOf('Cathedral'), greaterThan(0));
      expect(result!.city, 'Ho Chi Minh City');
      expect(result!.text, kMichael);
    });

    testWidgets('a failed preview keeps the text and shows the message',
        (tester) async {
      await pumpBox(
        tester,
        initialText: 'A → B',
        initialCity: '',
        post: (_) async =>
            jsonResp({'error': "no city: pass 'city' or name it"}, 400),
      );
      await tester.tap(find.byKey(kPastePreviewButtonKey));
      await tester.pumpAndSettle();
      expect(find.textContaining('Which city'), findsOneWidget);
      final t = tester.widget<TextField>(find.byKey(kPasteTextKey));
      expect(t.controller!.text, 'A → B');
    });
  });

  group('Create Tour screen end to end', () {
    late List<Map<String, dynamic>> generateBodies;
    late List<Map<String, dynamic>> previewBodies;

    MockClient buildClient() {
      generateBodies = [];
      previewBodies = [];
      return MockClient((request) async {
        final path = request.url.path;
        if (request.method == 'POST' && path.endsWith('/generate-complete-tour')) {
          generateBodies.add(jsonDecode(request.body) as Map<String, dynamic>);
          return jsonResp({'job_id': 'job_1'});
        }
        if (request.method == 'GET' && path.contains('/status/')) {
          return jsonResp({'status': 'error', 'error': 'stop here'});
        }
        return jsonResp({'ok': true, 'rows_affected': 1});
      });
    }

    Future<void> pumpScreen(WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(1200, 2600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(MaterialApp(
        home: TourGeneratorScreen(
          pastePreviewPost: (b) async {
            previewBodies.add(b);
            return jsonResp(previewFixture());
          },
          pasteLocateCity: () async => null,
          pasteShowTiles: false,
        ),
      ));
      await tester.pump();
      await tester.pump();
    }

    Future<void> pasteAndUse(WidgetTester tester) async {
      await tester.tap(find.byKey(kPastePreviewButtonKey));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(kPasteUseButtonKey));
      await tester.pumpAndSettle();
    }

    testWidgets(
        'Paste a list -> preview -> use -> Generate sends user_stops objects '
        'and total_stops = 10', (tester) async {
      final client = buildClient();
      await http.runWithClient(() async {
        await pumpScreen(tester);
        await tester.tap(find.byKey(const Key('paste_list_entry')));
        await tester.pumpAndSettle();
        await tester.enterText(find.byKey(kPasteTextKey), kMichael);
        await tester.enterText(find.byKey(kPasteCityKey), 'Ho Chi Minh City');
        await pasteAndUse(tester);

        // Back on Create Tour: stops chosen, request defaulted to the city.
        expect(find.text('Tour will be generated from your 10 stops, in order.'),
            findsOneWidget);
        expect(previewBodies.single['city'], 'Ho Chi Minh City');

        await tester.runAsync(() async {
          await tester.tap(find.text('🎯 Generate Now'));
          await Future<void>.delayed(const Duration(milliseconds: 200));
        });
        await tester.pumpAndSettle();

        expect(generateBodies.length, 1);
        final body = generateBodies.single;
        expect(body['total_stops'], 10);
        final us = body['user_stops'] as List;
        expect(us.length, 10);
        expect(us.every((e) => e is Map), isTrue);
        final first = us.first as Map<String, dynamic>;
        expect(first.keys.toSet(),
            containsAll(['name', 'lat', 'lng', 'resolved_name']));
        expect(first['name'], 'Cathedral');
        expect((us.last as Map)['name'], 'Thi Bar');
        expect(body['location'], 'Ho Chi Minh City');
      }, () => client);
    });

    testWidgets('Share → Audioura text opens the paste box pre-filled',
        (tester) async {
      final client = buildClient();
      await http.runWithClient(() async {
        await pumpScreen(tester);
        expect(find.byKey(kPasteTextKey), findsNothing);

        PendingSharedText.instance.offer(kMichael);
        await tester.pumpAndSettle();

        final t = tester.widget<TextField>(find.byKey(kPasteTextKey));
        expect(t.controller!.text, kMichael);
        // Consumed: it is not re-opened later.
        expect(PendingSharedText.instance.text.value, isNull);
      }, () => client);
    });

    testWidgets('shared text already waiting at launch opens the box',
        (tester) async {
      final client = buildClient();
      PendingSharedText.instance.offer('Cathedral → Post Office');
      await http.runWithClient(() async {
        await pumpScreen(tester);
        await tester.pumpAndSettle();
        final t = tester.widget<TextField>(find.byKey(kPasteTextKey));
        expect(t.controller!.text, 'Cathedral → Post Office');
      }, () => client);
    });
  });

  group('share hand-off plumbing', () {
    test('audioura://paste?text= carries the text; other URIs do not', () {
      final uri = Uri(
          scheme: 'audioura',
          host: 'paste',
          queryParameters: {'text': 'Cathedral → Post Office'});
      expect(textFromPasteUri(Uri.parse(uri.toString())),
          'Cathedral → Post Office');
      expect(textFromPasteUri(Uri.parse('https://audioura.com/t/ABCD1234')),
          isNull);
      expect(textFromPasteUri(Uri.parse('audioura://paste?text=')), isNull);
      expect(textFromPasteUri(Uri.parse('audioura://other?text=x')), isNull);
    });

    test('offer ignores blanks and cuts at the server limit', () {
      PendingSharedText.instance.offer('   ');
      expect(PendingSharedText.instance.text.value, isNull);
      PendingSharedText.instance.offer('x' * (kMaxPasteChars + 50));
      expect(PendingSharedText.instance.text.value!.length, kMaxPasteChars);
      PendingSharedText.instance.consume();
    });
  });
}
