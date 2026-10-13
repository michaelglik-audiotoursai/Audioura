// [LOCAL-677B] Tests for two found-tour-dialog / download decisions:
//   * the "Distance" line is hidden when distance_km is null (share-code and
//     search-results entries carry none — "Distance: null km" was the bug);
//   * only the SELECTED languages are downloaded (D653) — if English is
//     deselected it is not pulled to the phone, and the non-English set is the
//     translations to fetch.
//
// Both exercise the exact pure helpers the UI uses (shouldShowDistance,
// TourTranslationHelper.shouldDownloadEnglish / translationLanguages), so a
// green test proves the real code path.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/tour_display.dart';
import 'package:audio_tour_app_dev/services/tour_translation_helper.dart';

void main() {
  group('Distance line visibility (hide "Distance: null km")', () {
    test('shown when distance_km is a real number', () {
      expect(shouldShowDistance({'distance_km': 1.2}), isTrue);
      expect(shouldShowDistance({'distance_km': 0}), isTrue);
    });

    test('hidden when distance_km is null (share code / search result)', () {
      expect(shouldShowDistance({'distance_km': null}), isFalse);
      expect(shouldShowDistance({'name': 'x'}), isFalse); // key absent
    });
  });

  group('Download only the selected languages (D653)', () {
    test('null selection ⇒ default English only, no translations', () {
      expect(TourTranslationHelper.shouldDownloadEnglish(null), isTrue);
      expect(TourTranslationHelper.translationLanguages(null), isEmpty);
    });

    test('English selected with translations ⇒ English + the translations', () {
      final langs = ['en', 'ru', 'fr'];
      expect(TourTranslationHelper.shouldDownloadEnglish(langs), isTrue);
      expect(TourTranslationHelper.translationLanguages(langs), ['ru', 'fr']);
    });

    test('English DESELECTED ⇒ do NOT download English, only the translations', () {
      final langs = ['ru', 'fr'];
      expect(TourTranslationHelper.shouldDownloadEnglish(langs), isFalse);
      expect(TourTranslationHelper.translationLanguages(langs), ['ru', 'fr']);
    });

    test('only a single non-English language ⇒ English not pulled', () {
      expect(TourTranslationHelper.shouldDownloadEnglish(['ru']), isFalse);
      expect(TourTranslationHelper.translationLanguages(['ru']), ['ru']);
    });
  });
}
