// [LOCAL-717 / D677 §2] Tests for the generation-completion message: a
// regeneration that REPLACED an existing tour must say "Updated your tour
// '<title>' — now version N", not announce a brand-new tour (Michael looked for
// a second tour that never existed).
//
// NOTE: these can FAIL — drop the `replaced`/`version_no` read and the
// "updated to version 2" golden goes red; let a version-1 insert produce the
// "Updated…" text and the new-tour golden goes red.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/generation_completion_message.dart';

void main() {
  group('generationCompletionMessage — updated-to-version-N (D677)', () {
    test('replaced + version 2 → "Updated your tour \'<title>\' — now version 2"',
        () {
      final msg = generationCompletionMessage(
        {
          'status': 'completed',
          'final_tour_id': 370,
          'replaced': true,
          'version_no': 2,
          'tour_title': 'Boston — Restaurant Tour',
        },
        fallbackTitle: 'restaurant tour, Boston, MA',
      );
      expect(msg, "Updated your tour 'Boston — Restaurant Tour' — now version 2");
    });

    test('replaced + version 3 → version 3 in the message', () {
      final msg = generationCompletionMessage({
        'replaced': true,
        'version_no': 3,
        'tour_title': 'Freedom Trail',
      });
      expect(msg, "Updated your tour 'Freedom Trail' — now version 3");
    });

    test('no tour_title → falls back to the location the user typed', () {
      final msg = generationCompletionMessage(
        {'replaced': true, 'version_no': 2},
        fallbackTitle: 'restaurant tour, Boston, MA',
      );
      expect(msg,
          "Updated your tour 'restaurant tour, Boston, MA' — now version 2");
    });

    test('version_no may arrive as a String (JSON leniency)', () {
      final msg = generationCompletionMessage({
        'replaced': true,
        'version_no': '2',
        'tour_title': 'X',
      });
      expect(msg, "Updated your tour 'X' — now version 2");
    });

    test('brand-new tour (inserted, version 1) → the default "Tour ready!"', () {
      final msg = generationCompletionMessage({
        'replaced': false,
        'version_no': 1,
        'tour_title': 'A New Tour',
      });
      expect(msg, 'Tour ready! Opening now...');
    });

    test('replaced true but version 1 → still a new tour (never "version 1")',
        () {
      // Defensive: an "update" only makes sense at version >= 2.
      final msg = generationCompletionMessage({
        'replaced': true,
        'version_no': 1,
      });
      expect(msg, 'Tour ready! Opening now...');
    });

    test('a payload with no version info → the default message', () {
      final msg = generationCompletionMessage({'final_tour_id': 5});
      expect(msg, 'Tour ready! Opening now...');
    });
  });
}
