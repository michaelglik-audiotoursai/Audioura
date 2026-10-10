import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/search_dispatch.dart';

/// [LOCAL-665] Tests for the single Home search box's dispatcher.
///
/// Michael: merge the two search buttons; "by the format we can understand what
/// the listener is looking for." These tests pin the format-detection rules and
/// the fixed priority order (share code → coordinates → text), plus the
/// concurrent text-search outcome table (tours+place / tours / place / nothing).
///
/// NOTE: these can FAIL — e.g. drop the share-code-first rule and
/// `classifySearchInput('FFush25U')` stops being a shareCode; widen
/// parseCoordinates to accept a lone number and "Route 66" turns into
/// coordinates and the text group goes red.
void main() {
  group('classifySearchInput — a) share code wins first', () {
    test('bare 8-char code is a share code', () {
      final d = classifySearchInput('FFush25U');
      expect(d.kind, SearchKind.shareCode);
      expect(d.shareCode, 'FFush25U');
    });

    test('the full share message is a share code', () {
      const code = 'AzuwQYnf';
      const msg =
          'Listen to my Audioura tour "Harvard Yard". Open Audioura, tap '
          'Search on the Home page and paste this code: $code';
      final d = classifySearchInput(msg);
      expect(d.kind, SearchKind.shareCode);
      expect(d.shareCode, code);
    });

    test('a share link is a share code', () {
      final d = classifySearchInput('https://audioura.io/tour/FFush25U');
      expect(d.kind, SearchKind.shareCode);
      expect(d.shareCode, 'FFush25U');
    });

    test('whitespace around a bare code still classifies as share code', () {
      final d = classifySearchInput('   FFush25U  \n');
      expect(d.kind, SearchKind.shareCode);
      expect(d.shareCode, 'FFush25U');
    });
  });

  group('classifySearchInput — b) coordinates', () {
    test('"42.36, -71.06" is coordinates', () {
      final d = classifySearchInput('42.36, -71.06');
      expect(d.kind, SearchKind.coordinates);
      expect(d.latitude, closeTo(42.36, 1e-9));
      expect(d.longitude, closeTo(-71.06, 1e-9));
    });

    test('no space after the comma still parses', () {
      final d = classifySearchInput('42.36,-71.06');
      expect(d.kind, SearchKind.coordinates);
      expect(d.latitude, closeTo(42.36, 1e-9));
      expect(d.longitude, closeTo(-71.06, 1e-9));
    });

    test('integer pair with extra whitespace parses', () {
      final d = classifySearchInput('  48 ,  2 ');
      expect(d.kind, SearchKind.coordinates);
      expect(d.latitude, closeTo(48, 1e-9));
      expect(d.longitude, closeTo(2, 1e-9));
    });

    test('positive-signed pair parses', () {
      final d = classifySearchInput('+51.5, +0.12');
      expect(d.kind, SearchKind.coordinates);
      expect(d.latitude, closeTo(51.5, 1e-9));
      expect(d.longitude, closeTo(0.12, 1e-9));
    });
  });

  group('classifySearchInput — c) everything else is text', () {
    test('a plain tour / place name is text', () {
      final d = classifySearchInput('Boston');
      expect(d.kind, SearchKind.text);
      expect(d.query, 'Boston');
    });

    test('a multi-word place query is text', () {
      final d = classifySearchInput('San Francisco California');
      expect(d.kind, SearchKind.text);
    });

    test('a wildcard tour-name search is text', () {
      final d = classifySearchInput('walking*tour');
      expect(d.kind, SearchKind.text);
      expect(d.query, 'walking*tour');
    });

    test('a single number is NOT coordinates (no comma) → text', () {
      final d = classifySearchInput('66');
      expect(d.kind, SearchKind.text);
    });

    test('"Route 66" is text, not coordinates', () {
      final d = classifySearchInput('Route 66');
      expect(d.kind, SearchKind.text);
    });

    test('an 8-letter capitalised place (Brooklyn) is text, not a code', () {
      final d = classifySearchInput('Brooklyn');
      expect(d.kind, SearchKind.text);
    });
  });

  group('parseCoordinates range + shape guards', () {
    test('out-of-range latitude rejected', () {
      expect(parseCoordinates('91, 10'), isNull);
    });

    test('out-of-range longitude rejected', () {
      expect(parseCoordinates('10, 181'), isNull);
    });

    test('three numbers rejected', () {
      expect(parseCoordinates('1, 2, 3'), isNull);
    });

    test('a bare number rejected (needs the comma)', () {
      expect(parseCoordinates('42.36'), isNull);
    });

    test('a well-formed in-range pair accepted', () {
      final c = parseCoordinates('-33.8688, 151.2093');
      expect(c, isNotNull);
      expect(c!.lat, closeTo(-33.8688, 1e-9));
      expect(c.lng, closeTo(151.2093, 1e-9));
    });
  });

  group('resolveTextSearch — concurrent outcome table (Deliver §2c)', () {
    test('tours found AND place found → toursAndPlace', () {
      expect(
        resolveTextSearch(tourCount: 3, placeFound: true),
        TextSearchOutcome.toursAndPlace,
      );
    });

    test('only tours → toursOnly', () {
      expect(
        resolveTextSearch(tourCount: 2, placeFound: false),
        TextSearchOutcome.toursOnly,
      );
    });

    test('only a place → placeOnly', () {
      expect(
        resolveTextSearch(tourCount: 0, placeFound: true),
        TextSearchOutcome.placeOnly,
      );
    });

    test('neither → nothing', () {
      expect(
        resolveTextSearch(tourCount: 0, placeFound: false),
        TextSearchOutcome.nothing,
      );
    });
  });
}
