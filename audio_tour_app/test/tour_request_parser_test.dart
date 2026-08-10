import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_request_parser.dart';

/// [LOCAL-358 + LOCAL-363] Unit tests for tour request parser.
///
/// LOCAL-358 moved transport checks before place-name keywords (park/museum).
/// LOCAL-363 adds an activity-context guard so transport words inside proper
/// place names ("Horse Guards Parade", "Safari Park") don't hijack the type.
void main() {
  // ====================================================================
  // LOCAL-363 acceptance table — every row verbatim from the task spec
  // ====================================================================
  group('parseTourRequest - LOCAL-363 acceptance table', () {
    test('biking tour in Norwood MA → biking', () {
      final result = parseTourRequest('biking tour in Norwood MA');
      expect(result['tour_type'], equals('biking'));
    });

    test('biking tour in Central Park → biking', () {
      final result = parseTourRequest('biking tour in Central Park');
      expect(result['tour_type'], equals('biking'));
    });

    test('cycling tour of Hyde Park → biking', () {
      final result = parseTourRequest('cycling tour of Hyde Park');
      expect(result['tour_type'], equals('biking'));
    });

    test('bike tour along the boardwalk → biking', () {
      final result = parseTourRequest('bike tour along the boardwalk');
      expect(result['tour_type'], equals('biking'));
    });

    test('dog sledding tour in Big Lake AK → dog sledding', () {
      final result = parseTourRequest('dog sledding tour in Big Lake AK');
      expect(result['tour_type'], equals('dog sledding'));
    });

    test('camel tour in Abu Dhabi → camel', () {
      final result = parseTourRequest('camel tour in Abu Dhabi');
      expect(result['tour_type'], equals('camel'));
    });

    test('walking tour of Camelback Mountain, Phoenix → walking', () {
      final result =
          parseTourRequest('walking tour of Camelback Mountain, Phoenix');
      expect(result['tour_type'], equals('walking'));
    });

    test('tour of Horse Guards Parade, London → empty', () {
      final result =
          parseTourRequest('tour of Horse Guards Parade, London');
      expect(result['tour_type'], equals(''));
    });

    test('walking tour of the White Horse Tavern → walking', () {
      final result =
          parseTourRequest('walking tour of the White Horse Tavern');
      expect(result['tour_type'], equals('walking'));
    });

    test('tour of San Diego Safari Park → empty', () {
      final result = parseTourRequest('tour of San Diego Safari Park');
      expect(result['tour_type'], equals(''));
    });

    test('walking tour of Scooter Alley → walking', () {
      final result = parseTourRequest('walking tour of Scooter Alley');
      expect(result['tour_type'], equals('walking'));
    });

    test('museum tour of the Horse Museum → museum', () {
      final result = parseTourRequest('museum tour of the Horse Museum');
      expect(result['tour_type'], equals('museum'));
    });

    test('walking tour of Carmel-by-the-Sea → walking', () {
      final result = parseTourRequest('walking tour of Carmel-by-the-Sea');
      expect(result['tour_type'], equals('walking'));
    });

    test('tour of the Louvre → empty', () {
      final result = parseTourRequest('tour of the Louvre');
      expect(result['tour_type'], equals(''));
    });

    test('tour of downtown Boston → empty', () {
      final result = parseTourRequest('tour of downtown Boston');
      expect(result['tour_type'], equals(''));
    });
  });

  // ====================================================================
  // LOCAL-358 preserved behavior — transport modes with explicit activity
  // ====================================================================
  group('parseTourRequest - transport modes (activity context)', () {
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
      final result =
          parseTourRequest('motorcycle tour of Pacific Coast Highway');
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
  // Bare transport words (no "tour") — activity position still works
  // ====================================================================
  group('parseTourRequest - bare transport (no activity noun)', () {
    test('biking in Norwood MA → biking (leading activity word)', () {
      final result = parseTourRequest('biking in Norwood MA');
      expect(result['tour_type'], equals('biking'));
    });

    test('cycling around Paris → biking (leading activity word)', () {
      final result = parseTourRequest('cycling around Paris');
      expect(result['tour_type'], equals('biking'));
    });
  });

  // ====================================================================
  // Category keywords — weaker signal, checked after transport
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
    test('tour of Walkerville → empty (walk is substring)', () {
      final result = parseTourRequest('tour of Walkerville');
      expect(result['tour_type'], equals(''));
    });

    test('tour along the boardwalk → empty (walk is suffix)', () {
      final result = parseTourRequest('tour along the boardwalk');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the sidewalk district → empty (walk inside sidewalk)', () {
      final result = parseTourRequest('tour of the sidewalk district');
      expect(result['tour_type'], equals(''));
    });

    test('walking tour of Carmel-by-the-Sea → walking (not camel)', () {
      // \bcamel\b does not match inside "Carmel"
      final result = parseTourRequest('walking tour of Carmel-by-the-Sea');
      expect(result['tour_type'], equals('walking'));
    });

    test('walking tour of Bikeman Street → walking (not biking)', () {
      // \bbike\b does not match inside "Bikeman"
      final result = parseTourRequest('walking tour of Bikeman Street');
      expect(result['tour_type'], equals('walking'));
    });
  });

  // ====================================================================
  // Default behavior — no signal → empty string
  // ====================================================================
  group('parseTourRequest - default (no signal)', () {
    test('tour of downtown Boston → empty', () {
      final result = parseTourRequest('tour of downtown Boston');
      expect(result['tour_type'], equals(''));
    });

    test('Norwood MA → empty', () {
      final result = parseTourRequest('Norwood MA');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the Louvre → empty', () {
      final result = parseTourRequest('tour of the Louvre');
      expect(result['tour_type'], equals(''));
    });

    test('tour of the Uffizi → empty', () {
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
