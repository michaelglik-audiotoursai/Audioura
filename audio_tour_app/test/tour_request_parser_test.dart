import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_request_parser.dart';

/// [LOCAL-358] Unit tests for tour request parser.
///
/// These verify the fix for the museum-default bug: when a user typed
/// "biking tour in Norwood MA", the app sent tour_type='museum' because
/// 'biking' wasn't recognized and the default was 'museum'.
///
/// After the fix:
/// - Transport modes (bike, camel, dog sled, horse, vehicle, safari) are
///   recognized and checked FIRST (before place-name nouns like 'park').
/// - Default is '' (empty string = no signal), not 'museum' or 'walking'.
/// - Word-boundary matching prevents 'walk' matching inside 'boardwalk'.
void main() {
  // ====================================================================
  // LEAD bounce round 2 — four inputs that failed in the previous commit.
  // These MUST fail against the previous parser (transport modes were after
  // park/walk in the else-if chain, and contains('walk') hit 'boardwalk').
  // ====================================================================
  group('parseTourRequest - LEAD bounce failures (transport vs place-name)', () {
    test('biking tour in Central Park → biking (not park)', () {
      final result = parseTourRequest('biking tour in Central Park');
      expect(result['tour_type'], equals('biking'));
    });

    test('cycling tour of Hyde Park → biking (not park)', () {
      final result = parseTourRequest('cycling tour of Hyde Park');
      expect(result['tour_type'], equals('biking'));
    });

    test('horseback tour of the park → horseback (not park)', () {
      final result = parseTourRequest('horseback tour of the park');
      expect(result['tour_type'], equals('horseback'));
    });

    test('bike tour along the boardwalk → biking (not walking)', () {
      // Pre-existing substring bug: contains('walk') matched inside 'boardwalk'
      final result = parseTourRequest('bike tour along the boardwalk');
      expect(result['tour_type'], equals('biking'));
    });
  });

  // ====================================================================
  // Original acceptance tests — the five inputs from the task.
  // ====================================================================
  group('parseTourRequest - task acceptance inputs', () {
    test('biking tour in Norwood MA → biking', () {
      final result = parseTourRequest('biking tour in Norwood MA');
      expect(result['tour_type'], equals('biking'));
    });

    test('dog sledding tour in Big Lake AK → dog sledding', () {
      final result = parseTourRequest('dog sledding tour in Big Lake AK');
      expect(result['tour_type'], equals('dog sledding'));
    });

    test('walking tour of Vieux Nice → walking', () {
      final result = parseTourRequest('walking tour of Vieux Nice');
      expect(result['tour_type'], equals('walking'));
    });

    test('museum tour of the Louvre → museum', () {
      final result = parseTourRequest('museum tour of the Louvre');
      expect(result['tour_type'], equals('museum'));
    });

    test('camel tour in Abu Dhabi → camel', () {
      final result = parseTourRequest('camel tour in Abu Dhabi');
      expect(result['tour_type'], equals('camel'));
    });
  });

  // ====================================================================
  // Transport modes — comprehensive coverage
  // ====================================================================
  group('parseTourRequest - transport modes', () {
    test('cycling tour of French Riviera → biking', () {
      final result = parseTourRequest('cycling tour of French Riviera');
      expect(result['tour_type'], equals('biking'));
    });

    test('bike tour in Portland → biking', () {
      final result = parseTourRequest('bike tour in Portland');
      expect(result['tour_type'], equals('biking'));
    });

    test('mushing tour in Fairbanks → dog sledding', () {
      final result = parseTourRequest('mushing tour in Fairbanks');
      expect(result['tour_type'], equals('dog sledding'));
    });

    test('husky tour in Alaska → dog sledding', () {
      final result = parseTourRequest('husky tour in Alaska');
      expect(result['tour_type'], equals('dog sledding'));
    });

    test('dogsled tour in Anchorage → dog sledding', () {
      final result = parseTourRequest('dogsled tour in Anchorage');
      expect(result['tour_type'], equals('dog sledding'));
    });

    test('camelback tour in Morocco → camel', () {
      final result = parseTourRequest('camelback tour in Morocco');
      expect(result['tour_type'], equals('camel'));
    });

    test('horseback tour in Montana → horseback', () {
      final result = parseTourRequest('horseback tour in Montana');
      expect(result['tour_type'], equals('horseback'));
    });

    test('horse tour in Lexington → horseback', () {
      final result = parseTourRequest('horse tour in Lexington');
      expect(result['tour_type'], equals('horseback'));
    });

    test('driving tour of Route 66 → driving', () {
      final result = parseTourRequest('driving tour of Route 66');
      expect(result['tour_type'], equals('driving'));
    });

    test('jeep tour in Sedona → driving', () {
      final result = parseTourRequest('jeep tour in Sedona');
      expect(result['tour_type'], equals('driving'));
    });

    test('motorcycle tour of Pacific Coast Highway → driving', () {
      final result = parseTourRequest('motorcycle tour of Pacific Coast Highway');
      expect(result['tour_type'], equals('driving'));
    });

    test('scooter tour of Rome → driving', () {
      final result = parseTourRequest('scooter tour of Rome');
      expect(result['tour_type'], equals('driving'));
    });

    test('car tour of the countryside → driving', () {
      final result = parseTourRequest('car tour of the countryside');
      expect(result['tour_type'], equals('driving'));
    });

    test('road trip across Nevada → safari', () {
      final result = parseTourRequest('road trip across Nevada');
      expect(result['tour_type'], equals('safari'));
    });

    test('safari tour in Kenya → safari', () {
      final result = parseTourRequest('safari tour in Kenya');
      expect(result['tour_type'], equals('safari'));
    });

    test('cross-country tour of the US → safari', () {
      final result = parseTourRequest('cross-country tour of the US');
      expect(result['tour_type'], equals('safari'));
    });
  });

  // ====================================================================
  // Category keywords with word-boundary protection
  // ====================================================================
  group('parseTourRequest - categories (word-boundary)', () {
    test('walking tour of Boston → walking', () {
      final result = parseTourRequest('walking tour of Boston');
      expect(result['tour_type'], equals('walking'));
    });

    test('walk through the French Quarter → walking', () {
      final result = parseTourRequest('walk through the French Quarter');
      expect(result['tour_type'], equals('walking'));
    });

    test('hiking tour in Yosemite → walking', () {
      final result = parseTourRequest('hiking tour in Yosemite');
      expect(result['tour_type'], equals('walking'));
    });

    test('museum tour in DC → museum', () {
      final result = parseTourRequest('museum tour in DC');
      expect(result['tour_type'], equals('museum'));
    });

    test('park tour in Yellowstone → park', () {
      final result = parseTourRequest('park tour in Yellowstone');
      expect(result['tour_type'], equals('park'));
    });

    test('exhibit tour at the Met → exhibit', () {
      final result = parseTourRequest('exhibit tour at the Met');
      expect(result['tour_type'], equals('exhibit'));
    });
  });

  // ====================================================================
  // Word-boundary prevents substring false positives
  // ====================================================================
  group('parseTourRequest - substring protection', () {
    test('tour of Walkerville → empty (walk is substring, not word)', () {
      // 'Walkerville' contains 'walk' but not as a word boundary
      // However, \bwalk\b does NOT match inside 'Walkerville' since 'walker' != 'walk'
      // Actually \bwalk\b would match at start of 'Walkerville' — let me check
      // RegExp r'\b(walking|walk|hike|hiking)\b' — 'walk' in 'Walkerville':
      // \bwalk\b matches 'walk' at position 0 because 'e' follows at pos 4.
      // Wait no: 'Walkerville' lowercased = 'walkerville'. \bwalk\b matches
      // 'walk' at the start since 'e' is a word char, NOT a boundary after 'k'.
      // Actually \b is between 'k' and 'e'? No — \b is at position where one
      // side is \w and other is \W. In 'walkerville', all chars are \w, so
      // \bwalk\b matches at start (boundary before 'w') but needs boundary
      // after 'k' — 'e' is \w so no boundary. Hence \bwalk\b does NOT match.
      final result = parseTourRequest('tour of Walkerville');
      expect(result['tour_type'], equals(''));
    });

    test('tour along the boardwalk → empty (walk is suffix, not word)', () {
      // 'boardwalk' — \bwalk\b: boundary before 'w'? 'd' is \w, so no boundary.
      final result = parseTourRequest('tour along the boardwalk');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the sidewalk district → empty (walk inside sidewalk)', () {
      final result = parseTourRequest('tour of the sidewalk district');
      expect(result['tour_type'], equals(''));
    });
  });

  // ====================================================================
  // Default behavior — no signal → empty string
  // ====================================================================
  group('parseTourRequest - default (no signal)', () {
    test('tour of downtown Boston → empty (server decides)', () {
      final result = parseTourRequest('tour of downtown Boston');
      expect(result['tour_type'], equals(''));
    });

    test('Norwood MA → empty (server decides)', () {
      final result = parseTourRequest('Norwood MA');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the Louvre → empty (no keyword, server intent handles)', () {
      // The server's LLM intent analysis extracts venue_name='Louvre' and the
      // S15 block forces tour_category=museum. The app should not guess.
      final result = parseTourRequest('tour of the Louvre');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the Uffizi → empty (server decides)', () {
      final result = parseTourRequest('tour of the Uffizi');
      expect(result['tour_type'], equals(''));
    });
  });

  // ====================================================================
  // Location extraction
  // ====================================================================
  group('parseTourRequest - location extraction', () {
    test('preserves full text as location by default', () {
      final result = parseTourRequest('biking tour in Norwood MA');
      expect(result['location'], equals('biking tour in Norwood MA'));
    });

    test('"for" keyword extracts location', () {
      final result = parseTourRequest('walking tour for Vieux Nice France');
      expect(result['location'], equals('Vieux Nice France'));
    });
  });
}
