// [LOCAL-780] The creator's own priced tour — the translated copy's download
// was sent WITHOUT the device user_id, so map-delivery's pay-before-download
// gate (`_download_gate`) refused it 402 even though the creator is exempt.
// "Russian only" then ended on English with nothing playing and no message.
//
// The fix routes EVERY app `/download-tour/` call through ONE helper,
// `Endpoints.downloadTourUrl(tourId)`, which appends the device user_id (the
// same SharedPreferences `user_id` key tour_download_service / home_screen
// already used). These tests pin:
//   1. the helper appends user_id when present, and omits it (bare URL) when
//      absent — matching the anonymous device's behaviour;
//   2. a mocked map-delivery that 402s WITHOUT user_id and 200s WITH it is
//      satisfied by a request built from the helper (the exact live gate);
//   3. a source-level guard that every `/download-tour` URL in lib/ is built
//      by the helper — no hand-built URL may re-introduce the bug;
//   4. the Generate-screen failure fallback message names the language and
//      says it is showing English.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:audio_tour_app_dev/config/endpoints.dart';
import 'package:audio_tour_app_dev/services/tour_translation_helper.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Endpoints.downloadTourUrl appends the device user_id (LOCAL-780)', () {
    test('appends user_id as a query parameter when one is stored', () async {
      SharedPreferences.setMockInitialValues({
        'server_mode': 'local',
        'server_ip': '192.168.0.187',
        'user_id': 'USER-41659366',
      });

      final uri = await Endpoints.downloadTourUrl(453);

      expect(uri.path, endsWith('/download-tour/453'));
      expect(uri.queryParameters['user_id'], 'USER-41659366',
          reason: 'the gate reads ?user_id= to apply the creator exemption');
    });

    test('omits user_id (bare URL) when none is stored — anonymous device',
        () async {
      SharedPreferences.setMockInitialValues({
        'server_mode': 'local',
        'server_ip': '192.168.0.187',
      });

      final uri = await Endpoints.downloadTourUrl(453);

      expect(uri.path, endsWith('/download-tour/453'));
      expect(uri.queryParameters.containsKey('user_id'), isFalse);
    });
  });

  group('a request built from the helper clears the live 402 gate (LOCAL-780)',
      () {
    // A stand-in for map-delivery's creator-exemption gate: 402 unless the
    // request carries ?user_id=, 200 when it does. This is the exact behaviour
    // Michael's curl showed (with user_id 200, without it 402).
    MockClient gatedMapDelivery() => MockClient((request) async {
          final hasUser = (request.url.queryParameters['user_id'] ?? '').isNotEmpty;
          if (!hasUser) {
            return http.Response('{"error":"purchase_required"}', 402);
          }
          return http.Response('zip-bytes', 200);
        });

    test('WITHOUT user_id the gate returns 402', () async {
      SharedPreferences.setMockInitialValues({
        'server_mode': 'local',
        'server_ip': '192.168.0.187',
        // no user_id stored
      });
      final client = gatedMapDelivery();
      final uri = await Endpoints.downloadTourUrl(453);
      final resp = await client.get(uri);
      expect(resp.statusCode, 402);
    });

    test('WITH user_id the translated download sends it and gets 200', () async {
      SharedPreferences.setMockInitialValues({
        'server_mode': 'local',
        'server_ip': '192.168.0.187',
        'user_id': 'USER-41659366',
      });
      final client = gatedMapDelivery();
      final uri = await Endpoints.downloadTourUrl(453);
      final resp = await client.get(uri);
      expect(resp.statusCode, 200);
      expect(resp.body, 'zip-bytes');
    });
  });

  group('every /download-tour call site goes through the helper (LOCAL-780)',
      () {
    test('no lib/ file hand-builds a /download-tour URL via Endpoints.url',
        () async {
      final libDir = Directory('lib');
      expect(libDir.existsSync(), isTrue,
          reason: 'run from the package root (audio_tour_app)');

      final offenders = <String>[];
      final endpointsPath =
          'lib${Platform.pathSeparator}config${Platform.pathSeparator}endpoints.dart';

      for (final entity in libDir.listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        // The helper itself legitimately builds the URL from Endpoints.url;
        // it is the ONE allowed place.
        if (entity.path.endsWith(endpointsPath)) continue;

        final lines = entity.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          // A hand-built download URL is Endpoints.url(..., '/download-tour/...').
          if (line.contains("Endpoints.url(") &&
              line.contains('/download-tour/')) {
            offenders.add('${entity.path}:${i + 1}: ${line.trim()}');
          }
        }
      }

      expect(offenders, isEmpty,
          reason: 'These call sites must use Endpoints.downloadTourUrl(tourId) '
              'so the device user_id is always attached:\n'
              '${offenders.join('\n')}');
    });

    test('the helper is actually referenced by the known call-site files',
        () async {
      // Guard against the opposite failure: the grep above passes vacuously if
      // the download code was deleted. Pin that the real callers reference the
      // helper by name.
      final callers = <String>[
        'lib/services/tour_download_service.dart',
        'lib/screens/home_screen.dart',
        'lib/screens/tour_generator_screen.dart',
        'lib/services/tour_translation_helper.dart',
      ];
      for (final path in callers) {
        final f = File(path.replaceAll('/', Platform.pathSeparator));
        expect(f.existsSync(), isTrue, reason: '$path should exist');
        expect(f.readAsStringSync(), contains('downloadTourUrl'),
            reason: '$path must build its download URL via the helper');
      }
    });
  });

  group('Generate-screen failure fallback message (LOCAL-780)', () {
    test('names the language and says it is showing English', () {
      expect(TourTranslationHelper.translationFallbackMessage('ru'),
          "Couldn't download the Russian version — showing English.");
    });

    test('falls back to the upper-cased code for an unknown language', () {
      expect(TourTranslationHelper.translationFallbackMessage('xx'),
          "Couldn't download the XX version — showing English.");
    });
  });
}
