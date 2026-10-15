// [LOCAL-693 / D660] Delete-confirmation copy — unit tests.
//
// Proves the ticket's rule "the delete-confirmation is shown for PAID tours
// only": a paid tour gets "Delete and lose it?" with the SAME warning sentence
// the Buy dialog used; a free tour keeps the plain "Delete Tour" confirmation.
// Pure model (DeleteTourPrompt) — no widget tree, no server.

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/widgets/delete_tour_prompt.dart';

void main() {
  group('DeleteTourPrompt.decide (D660)', () {
    test('a PAID tour gets the warning title + the shared D660 sentence', () {
      final p = DeleteTourPrompt.decide(tourTitle: 'Old Nice', isPaid: true);
      expect(p.isPaidWarning, isTrue);
      expect(p.title, 'Delete and lose it?');
      expect(p.body, contains('Old Nice'));
      // The exact sentence shared with the Buy dialog.
      expect(p.body, contains(DeleteTourPrompt.warningSentence));
      expect(DeleteTourPrompt.warningSentence,
          'Deleting it or changing phones means buying again.');
    });

    test('a FREE tour gets the plain confirmation, no warning sentence', () {
      final p = DeleteTourPrompt.decide(tourTitle: 'Free Walk', isPaid: false);
      expect(p.isPaidWarning, isFalse);
      expect(p.title, 'Delete Tour');
      expect(p.body, contains('Free Walk'));
      expect(p.body.contains(DeleteTourPrompt.warningSentence), isFalse);
    });
  });

  group('DeleteTourPrompt.isPaidTour', () {
    test('is_paid flag true → paid', () {
      expect(DeleteTourPrompt.isPaidTour({'is_paid': true}), isTrue);
    });
    test('price_tier > 0 → paid', () {
      expect(DeleteTourPrompt.isPaidTour({'price_tier': 3}), isTrue);
    });
    test('price_tier 0 or null → free', () {
      expect(DeleteTourPrompt.isPaidTour({'price_tier': 0}), isFalse);
      expect(DeleteTourPrompt.isPaidTour({'price_tier': null}), isFalse);
      expect(DeleteTourPrompt.isPaidTour({}), isFalse);
    });
    test('is_paid false + no tier → free', () {
      expect(DeleteTourPrompt.isPaidTour({'is_paid': false}), isFalse);
    });
  });
}
