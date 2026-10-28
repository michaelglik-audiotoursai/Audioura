// [LOCAL-789 ADDENDUM / LOCAL-793] Unit test for the client-side historic
// place-name alias map applied BEFORE geocoding.
//
// Michael's live run: with the server /geocode not deployed, "Saigon Vietnam"
// ends at "Nothing found" — Nominatim returns only POIs literally named
// "Saigon", never Ho Chi Minh City. applyPlaceAliases rewrites the historic
// name to the modern one the index knows, whole-word and
// case/diacritic-insensitive, leaving the rest of the query (", Vietnam")
// intact. These tests pin that contract and the no-false-positive rule.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/place_geocoder.dart';

void main() {
  group('applyPlaceAliases — the LEAD list', () {
    test('"Saigon Vietnam" → "Ho Chi Minh City Vietnam"', () {
      expect(applyPlaceAliases('Saigon Vietnam'), 'Ho Chi Minh City Vietnam');
    });

    test('each historic name maps to its modern name', () {
      expect(applyPlaceAliases('Bombay'), 'Mumbai');
      expect(applyPlaceAliases('Peking'), 'Beijing');
      expect(applyPlaceAliases('Calcutta'), 'Kolkata');
      expect(applyPlaceAliases('Madras'), 'Chennai');
      expect(applyPlaceAliases('Rangoon'), 'Yangon');
      expect(applyPlaceAliases('Canton'), 'Guangzhou');
    });
  });

  group('applyPlaceAliases — case & diacritic insensitive', () {
    test('lower-case matches', () {
      expect(applyPlaceAliases('saigon vietnam'), 'Ho Chi Minh City vietnam');
    });

    test('upper-case matches', () {
      expect(applyPlaceAliases('SAIGON'), 'Ho Chi Minh City');
    });

    test('diacritic form "Sài Gòn" folds and matches as one token', () {
      // "Sài" and "Gòn" fold to "sai"/"gon"; the whole-token key is "saigon",
      // so a spaced diacritic form is NOT a single token. The common one-word
      // "Sàigòn" IS, so verify that form resolves.
      expect(applyPlaceAliases('Sàigòn'), 'Ho Chi Minh City');
    });
  });

  group('applyPlaceAliases — whole word only (no false positives)', () {
    test('a word that merely CONTAINS a historic name is left alone', () {
      expect(applyPlaceAliases('Saigons'), 'Saigons');
      expect(applyPlaceAliases('New Bombayville'), 'New Bombayville');
    });

    test('surrounding punctuation and spacing are preserved', () {
      expect(applyPlaceAliases('Saigon, Vietnam'), 'Ho Chi Minh City, Vietnam');
    });

    test('a query with no historic token is returned unchanged', () {
      expect(applyPlaceAliases('Boston, MA'), 'Boston, MA');
      expect(applyPlaceAliases('Eiffel Tower'), 'Eiffel Tower');
    });

    test('empty string is returned unchanged', () {
      expect(applyPlaceAliases(''), '');
    });

    test('a historic name mid-query is still replaced whole-word', () {
      expect(applyPlaceAliases('tours near Bombay please'),
          'tours near Mumbai please');
    });
  });
}
