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

  // [LOCAL-697 / LEAD D662] A found PLACE always wins: the widget relocates the
  // map to it immediately (normal Home view of that area), with NO tours dialog
  // and NO "relocate?" confirmation. The tours dialog appears ONLY when no place
  // is found but tour names match. The outcome enum encodes exactly that:
  //   place + tours → toursAndPlace (relocate + 'N tours named "<q>" — Show')
  //   place only    → placeOnly     (relocate)
  //   tours only    → toursOnly      (tours dialog)
  //   neither       → nothing        ('nothing found')
  group('resolveTextSearch — concurrent outcome table (D662)', () {
    test('place + tours → toursAndPlace (relocate, then offer tours)', () {
      expect(
        resolveTextSearch(tourCount: 3, placeFound: true),
        TextSearchOutcome.toursAndPlace,
      );
    });

    test('place + a single tour → still toursAndPlace (relocate wins)', () {
      expect(
        resolveTextSearch(tourCount: 1, placeFound: true),
        TextSearchOutcome.toursAndPlace,
      );
    });

    test('tours only → toursOnly (the tours dialog)', () {
      expect(
        resolveTextSearch(tourCount: 2, placeFound: false),
        TextSearchOutcome.toursOnly,
      );
    });

    test('place only → placeOnly (relocate)', () {
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

  // [LOCAL-717 / D677 §3] A trailing `*` is the explicit "tour NAMES, not a
  // place" signal. Michael's "restaurant*" moved the map to a far-away place
  // called "Restaurant"; the fix is that an input ENDING in `*` never geocodes
  // and matches tour names only (starts-with), so no place can win.
  group('classifySearchInput — d) trailing * is tour-name-only (D677)', () {
    test('"restaurant*" → text, tourNameOnly', () {
      final d = classifySearchInput('restaurant*');
      expect(d.kind, SearchKind.text);
      expect(d.tourNameOnly, isTrue);
      expect(d.query, 'restaurant*');
    });

    test('"Boston*" → text, tourNameOnly', () {
      final d = classifySearchInput('Boston*');
      expect(d.kind, SearchKind.text);
      expect(d.tourNameOnly, isTrue);
    });

    test('"restaurant tour*" (multi-word) → text, tourNameOnly', () {
      final d = classifySearchInput('restaurant tour*');
      expect(d.kind, SearchKind.text);
      expect(d.tourNameOnly, isTrue);
      expect(d.query, 'restaurant tour*');
    });

    test('"Boston" (no star) → text, NOT tourNameOnly (keeps D662)', () {
      final d = classifySearchInput('Boston');
      expect(d.kind, SearchKind.text);
      expect(d.tourNameOnly, isFalse);
    });

    test('a `*` in the MIDDLE is not the signal ("walking*tour")', () {
      final d = classifySearchInput('walking*tour');
      expect(d.kind, SearchKind.text);
      // Only a trailing `*` means name-only; a mid-string `*` does not.
      expect(d.tourNameOnly, isFalse);
    });

    test('trailing whitespace after the star is trimmed, still name-only', () {
      final d = classifySearchInput('restaurant*  ');
      expect(d.tourNameOnly, isTrue);
      expect(d.query, 'restaurant*');
    });
  });

  // [LOCAL-717 / D677 §3] The outcome table for a name-only search: the place
  // can never win (geocoder is not called), and no tours → noNamedTours (the
  // widget says "No tours named '<text>…'"), NOT "nothing found".
  group('resolveTextSearch — name-only outcome table (D677)', () {
    test('name-only + tours → toursOnly', () {
      expect(
        resolveTextSearch(tourCount: 2, placeFound: false, nameOnly: true),
        TextSearchOutcome.toursOnly,
      );
    });

    test('name-only + no tours → noNamedTours (never "nothing")', () {
      expect(
        resolveTextSearch(tourCount: 0, placeFound: false, nameOnly: true),
        TextSearchOutcome.noNamedTours,
      );
    });

    test('name-only NEVER lets a place win, even if one was passed', () {
      // The geocoder is not called for a name-only search, but guard anyway:
      // a stray placeFound:true must not relocate the map.
      expect(
        resolveTextSearch(tourCount: 0, placeFound: true, nameOnly: true),
        TextSearchOutcome.noNamedTours,
      );
      expect(
        resolveTextSearch(tourCount: 3, placeFound: true, nameOnly: true),
        TextSearchOutcome.toursOnly,
      );
    });
  });
}
