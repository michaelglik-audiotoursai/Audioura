// [LOCAL-730 / D694, Privacy "Location and places"] Tests that Treats are
// sourced from the tour places in the policy's order — (a) current tour >
// (b) downloaded tours > (c) Home place > (d) nothing — and NEVER from the
// phone's GPS.
//
// The "zero Geolocator calls" guarantee is proven two ways:
//   1. Behaviourally: the resolver is driven with injected readers for every
//      source (a)–(d); it produces the right points with no Geolocator in the
//      picture at all (there is no GPS reader to call).
//   2. Structurally: neither the resolver nor the Treats screen imports
//      `geolocator` or names `Geolocator` — so the screen has no path to the
//      device position. THIS is the test the "Red test" below breaks: add a GPS
//      fallback and the structural assertion fails.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/treats_source_resolver.dart';

/// Build a resolver from in-memory data — no SharedPreferences, no files, and
/// (by construction) no Geolocator. Any source left null/empty is "absent".
TreatsSourceResolver _resolver({
  String? currentPath,
  List<String> downloaded = const [],
  Map<String, List<TreatPoint>> stops = const {},
  TreatPoint? home,
}) {
  return TreatsSourceResolver(
    currentTourPath: () async => currentPath,
    downloadedTourPaths: () async => downloaded,
    stopsForTour: (p) async => stops[p] ?? const [],
    homePlace: () async => home,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('source order (a) > (b) > (c) > (d)', () {
    test('(a) the current/playing tour wins over everything else', () async {
      final r = _resolver(
        currentPath: '/tours/current',
        downloaded: ['/tours/dl1'],
        stops: {
          '/tours/current': const [TreatPoint(40.0, -70.0)],
          '/tours/dl1': const [TreatPoint(41.0, -71.0)],
        },
        home: const TreatPoint(42.0, -72.0),
      );
      final res = await r.resolve();
      expect(res.source, TreatsSource.currentTour);
      expect(res.points, const [TreatPoint(40.0, -70.0)]);
    });

    test('(b) downloaded tours used when no current tour', () async {
      final r = _resolver(
        downloaded: ['/tours/dl1', '/tours/dl2'],
        stops: {
          '/tours/dl1': const [TreatPoint(1.0, 1.0)],
          '/tours/dl2': const [TreatPoint(2.0, 2.0)],
        },
        home: const TreatPoint(42.0, -72.0),
      );
      final res = await r.resolve();
      expect(res.source, TreatsSource.downloadedTours);
      expect(res.points, const [TreatPoint(1.0, 1.0), TreatPoint(2.0, 2.0)]);
    });

    test('(c) Home place used when no tours carry coordinates', () async {
      final r = _resolver(
        currentPath: '/tours/current', // present but has NO coordinates
        downloaded: ['/tours/dl1'], // present but has NO coordinates
        stops: const {},
        home: const TreatPoint(42.0, -72.0),
      );
      final res = await r.resolve();
      expect(res.source, TreatsSource.homePlace);
      expect(res.points, const [TreatPoint(42.0, -72.0)]);
    });

    test('(d) nothing ⇒ empty result, no request', () async {
      final r = _resolver();
      final res = await r.resolve();
      expect(res.source, TreatsSource.none);
      expect(res.isEmpty, isTrue);
    });

    test('a current tour with no coordinates falls through to (b)', () async {
      final r = _resolver(
        currentPath: '/tours/current',
        downloaded: ['/tours/dl1'],
        stops: {
          '/tours/dl1': const [TreatPoint(3.0, 3.0)],
        },
      );
      final res = await r.resolve();
      expect(res.source, TreatsSource.downloadedTours);
      expect(res.points, const [TreatPoint(3.0, 3.0)]);
    });
  });

  group('de-duplication and cap', () {
    test('downloaded tours de-duplicate overlapping stops (2 decimals)', () async {
      final r = _resolver(
        downloaded: ['/tours/dl1', '/tours/dl2'],
        stops: {
          '/tours/dl1': const [TreatPoint(40.123, -70.123)],
          // same place to 2 decimals ⇒ dropped as a duplicate
          '/tours/dl2': const [TreatPoint(40.124, -70.121), TreatPoint(50.0, -60.0)],
        },
      );
      final res = await r.resolve();
      expect(res.source, TreatsSource.downloadedTours);
      expect(res.points, const [TreatPoint(40.123, -70.123), TreatPoint(50.0, -60.0)]);
    });

    test('points are capped at maxPoints (10)', () async {
      final many = List<TreatPoint>.generate(
          25, (i) => TreatPoint(i.toDouble(), i.toDouble()));
      final r = _resolver(
        currentPath: '/tours/current',
        stops: {'/tours/current': many},
      );
      final res = await r.resolve();
      expect(res.points.length, TreatsSourceResolver.maxPoints);
      expect(res.points.first, const TreatPoint(0.0, 0.0));
    });
  });

  group('coordinate parsing (matches tour_map_screen _parsePoi format)', () {
    test('parses a "Coordinates: lat, lng" line', () {
      final pt = TreatsSourceResolver.parseCoordinates(
          'Old North Church\nType/Specialty: landmark\n'
          'Coordinates: 42.3663, -71.0544\nAddress: 193 Salem St');
      expect(pt, isNotNull);
      expect(pt!.lat, 42.3663);
      expect(pt.lng, -71.0544);
    });

    test('returns null when there is no coordinates line', () {
      expect(TreatsSourceResolver.parseCoordinates('no coords here'), isNull);
    });
  });

  // --- The zero-Geolocator guarantee (structural) + the Red test ----------
  group('zero Geolocator calls for sources (a)-(d)', () {
    // Resolve the lib/ paths relative to the package root.
    String libFile(String rel) {
      final root = Directory.current.path;
      return '$root/lib/$rel';
    }

    // Strip // line comments and /* */ block comments so a DOCUMENTED mention
    // of geolocator (explaining that we must NOT use it) doesn't trip the
    // guard — only real import/usage counts.
    String stripComments(String src) {
      final noBlock = src.replaceAll(RegExp(r'/\*.*?\*/', dotAll: true), '');
      return noBlock
          .split('\n')
          .map((l) {
            final i = l.indexOf('//');
            return i >= 0 ? l.substring(0, i) : l;
          })
          .join('\n');
    }

    void assertNoGeolocator(String relPath) {
      final code = stripComments(File(libFile(relPath)).readAsStringSync());
      expect(code.contains('package:geolocator'), isFalse,
          reason: '$relPath must not import package:geolocator');
      expect(RegExp(r'\bGeolocator\b').hasMatch(code), isFalse,
          reason: '$relPath must have no path to the device GPS');
    }

    test('the resolver never imports or names Geolocator', () {
      assertNoGeolocator('services/treats_source_resolver.dart');
    });

    test('RED TEST: the Treats screen never imports or names Geolocator', () {
      // Re-introducing the old GPS fallback (import geolocator +
      // Geolocator.getCurrentPosition) in treats_screen.dart makes THIS test
      // fail — that is the guard against regressing the Privacy promise.
      assertNoGeolocator('screens/treats_screen.dart');
    });
  });
}
